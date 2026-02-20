"""AI-powered exception analysis using llm library."""

import csv
import json
import re
from pathlib import Path
from typing import Any

import llm

from .config import settings
from .db import create_finding, get_run, update_run_status
from .models import Finding, Severity
from .output import print_error, print_info, print_success

# Separator used when emitting prompt-only output
PROMPT_SEPARATOR = "─" * 72

SYSTEM_PROMPT = """You are Argus, an expert exception analyst for software engineering teams.
Your job is to analyze exception data from observability platforms and provide actionable fix recommendations.

When analyzing exceptions, you must:
1. Identify the most likely root cause
2. Provide a specific fix suggestion with file and line context when available
3. Estimate severity: P0 (production down), P1 (major feature broken), P2 (degraded), P3 (minor/cosmetic)
4. Flag exceptions that look like background job / cache loader / reservation updater noise
5. Reference any matching lessons from institutional memory if relevant

You MUST respond with valid JSON in this exact format:
{
  "findings": [
    {
      "error_code": "string or null",
      "operation_id": "string or null",
      "severity": "P0|P1|P2|P3",
      "summary": "one-line description",
      "root_cause": "detailed root cause analysis",
      "fix_suggestion": "specific fix with file/line if available",
      "is_noise": true/false,
      "matched_lesson": "lesson filename or null"
    }
  ]
}

Be concise but thorough. Focus on actionable insights, not generic advice."""


def build_analysis_prompt(
    logs: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    sonarqube_issues: list[dict[str, Any]],
    lessons: list[tuple[str, str]],
    code_context: str | None = None,
) -> str:
    """
    Build the analysis prompt from collected data.

    Args:
        logs: Log entries from Loki
        traces: Trace summaries from Tempo
        sonarqube_issues: Issues from SonarQube
        lessons: List of (filename, content) tuples from lessons directory
        code_context: Optional code context from cloned repo

    Returns:
        Formatted prompt string
    """
    sections = []

    # Exception logs
    if logs:
        sections.append("## Exception Logs")
        sections.append(f"Found {len(logs)} log entries with errors/exceptions:")
        sections.append("")
        for i, log in enumerate(logs[:50], 1):  # Limit to 50 logs
            timestamp = log.get("timestamp", "unknown")
            line = log.get("line", "")
            labels = log.get("labels", {})
            service = labels.get("service_name", labels.get("job", "unknown"))
            sections.append(f"### Log {i} ({service} @ {timestamp})")
            sections.append("```")
            sections.append(line[:2000])  # Truncate very long lines
            sections.append("```")
            sections.append("")
        if len(logs) > 50:
            sections.append(f"... and {len(logs) - 50} more log entries")
        sections.append("")

    # Error traces
    if traces:
        sections.append("## Error Traces")
        sections.append(f"Found {len(traces)} traces with errors:")
        sections.append("")
        for trace in traces[:20]:  # Limit to 20 traces
            sections.append(f"- **{trace.get('rootServiceName', 'unknown')}**: {trace.get('rootTraceName', 'unknown')} ({trace.get('durationMs', 0)}ms) - ID: {trace.get('traceID', 'unknown')[:16]}...")
        if len(traces) > 20:
            sections.append(f"... and {len(traces) - 20} more traces")
        sections.append("")

    # SonarQube issues
    if sonarqube_issues:
        sections.append("## SonarQube Issues (Static Analysis)")
        sections.append(f"Found {len(sonarqube_issues)} relevant code quality issues:")
        sections.append("")
        for issue in sonarqube_issues[:30]:  # Limit to 30 issues
            severity = issue.get("severity", "UNKNOWN")
            component = issue.get("component", "").split(":")[-1]  # Get filename
            message = issue.get("message", "")[:100]
            sections.append(f"- **{severity}** in `{component}`: {message}")
        if len(sonarqube_issues) > 30:
            sections.append(f"... and {len(sonarqube_issues) - 30} more issues")
        sections.append("")

    # Lessons (institutional memory)
    if lessons:
        sections.append("## Institutional Memory (Lessons)")
        sections.append("Previous patterns that may be relevant:")
        sections.append("")
        for filename, content in lessons:
            sections.append(f"### {filename}")
            sections.append(content[:1000])  # Truncate long lessons
            sections.append("")

    # Code context
    if code_context:
        sections.append("## Code Context")
        sections.append(code_context[:5000])  # Truncate to 5000 chars
        sections.append("")

    # Final instruction
    sections.append("## Your Task")
    sections.append("Analyze the above exception data and provide findings in the required JSON format.")
    sections.append("Group related exceptions into single findings when they share the same root cause.")
    sections.append("Be specific about fix suggestions - include file names and line numbers when possible.")

    return "\n".join(sections)


def load_lessons() -> list[tuple[str, str]]:
    """Load all lesson files from the lessons directory."""
    lessons = []
    lessons_dir = settings.lessons_dir

    if not lessons_dir.exists():
        return lessons

    for path in sorted(lessons_dir.glob("*.md")):
        try:
            content = path.read_text()
            lessons.append((path.name, content))
        except Exception:
            continue

    return lessons


def load_logs_from_run(run_dir: Path) -> list[dict[str, Any]]:
    """Load log data from CSVs in a run's logs directory."""
    logs = []
    logs_dir = run_dir / "logs"

    if not logs_dir.exists():
        return logs

    for csv_path in logs_dir.glob("*.csv"):
        try:
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    logs.append(dict(row))
        except Exception:
            continue

    return logs


def load_traces_from_run(run_dir: Path) -> list[dict[str, Any]]:
    """Load trace data from CSVs in a run's traces directory."""
    traces = []
    traces_dir = run_dir / "traces"

    if not traces_dir.exists():
        return traces

    for csv_path in traces_dir.glob("*.csv"):
        try:
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    traces.append(dict(row))
        except Exception:
            continue

    return traces


def load_code_context(run_dir: Path) -> str | None:
    """Load code context from a run's code directory."""
    code_dir = run_dir / "code"

    if not code_dir.exists():
        return None

    # Look for a context.txt or similar
    context_file = code_dir / "context.txt"
    if context_file.exists():
        return context_file.read_text()

    return None


def parse_findings_response(response_text: str, run_id: str) -> list[Finding]:
    """
    Parse the LLM response into Finding objects.

    Args:
        response_text: Raw LLM response text
        run_id: Run ID to associate findings with

    Returns:
        List of Finding objects
    """
    findings = []

    # Try to extract JSON from the response
    # Handle cases where the model wraps JSON in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            print_error("Could not find JSON in model response")
            return findings

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print_error(f"Failed to parse JSON: {e}")
        return findings

    for item in data.get("findings", []):
        try:
            severity_str = item.get("severity", "P3")
            severity = Severity(severity_str) if severity_str in [s.value for s in Severity] else Severity.P3

            finding = Finding(
                run_id=run_id,
                error_code=item.get("error_code") or "",
                operation_id=item.get("operation_id") or "",
                severity=severity,
                summary=item.get("summary", "No summary provided"),
                root_cause=item.get("root_cause", ""),
                fix_suggestion=item.get("fix_suggestion", ""),
                is_noise=bool(item.get("is_noise", False)),
                matched_lesson=item.get("matched_lesson") or "",
                analysis=json.dumps(item, indent=2),  # Store full item as analysis
            )
            findings.append(finding)
        except Exception as e:
            print_error(f"Failed to parse finding: {e}")
            continue

    return findings


def save_finding_to_disk(finding: Finding, run_dir: Path) -> None:
    """Save a finding as a markdown file."""
    findings_dir = run_dir / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{finding.severity.value}_{finding.finding_id[:8]}.md"
    filepath = findings_dir / filename

    content = f"""# {finding.summary}

**Severity:** {finding.severity.value}
**Error Code:** {finding.error_code or "N/A"}
**Operation ID:** {finding.operation_id or "N/A"}
**Noise:** {"Yes" if finding.is_noise else "No"}
**Matched Lesson:** {finding.matched_lesson or "None"}

## Root Cause

{finding.root_cause or "Not determined"}

## Fix Suggestion

{finding.fix_suggestion or "No suggestion"}

## Full Analysis

```json
{finding.analysis}
```
"""

    filepath.write_text(content)


def build_prompt_for_run(
    run_id: str,
    sonarqube_issues: list[dict[str, Any]] | None = None,
) -> tuple[str, str] | None:
    """
    Build the full prompt for a run without calling the LLM.

    Args:
        run_id: The run ID to build a prompt for
        sonarqube_issues: Optional SonarQube issues

    Returns:
        Tuple of (system_prompt, user_prompt) or None if no data
    """
    run = get_run(run_id)
    if not run:
        print_error(f"Run not found: {run_id}")
        return None

    run_dir = Path(run.run_dir)
    if not run_dir.exists():
        print_error(f"Run directory not found: {run_dir}")
        return None

    logs = load_logs_from_run(run_dir)
    traces = load_traces_from_run(run_dir)
    lessons = load_lessons()
    code_context = load_code_context(run_dir)

    if not logs and not traces:
        print_error("No log or trace data found for this run")
        return None

    print_info(f"Found {len(logs)} logs, {len(traces)} traces, {len(lessons)} lessons")

    prompt = build_analysis_prompt(
        logs=logs,
        traces=traces,
        sonarqube_issues=sonarqube_issues or [],
        lessons=lessons,
        code_context=code_context,
    )

    return SYSTEM_PROMPT, prompt


def format_full_prompt(system_prompt: str, user_prompt: str) -> str:
    """Format system + user prompt for copy-paste into Claude Code."""
    return (
        f"{PROMPT_SEPARATOR}\n"
        f"SYSTEM PROMPT\n"
        f"{PROMPT_SEPARATOR}\n\n"
        f"{system_prompt}\n\n"
        f"{PROMPT_SEPARATOR}\n"
        f"ANALYSIS DATA\n"
        f"{PROMPT_SEPARATOR}\n\n"
        f"{user_prompt}\n"
    )


async def analyze_run(run_id: str, sonarqube_issues: list[dict[str, Any]] | None = None) -> list[Finding]:
    """
    Run AI analysis on collected data for a run.

    Args:
        run_id: The run ID to analyze
        sonarqube_issues: Optional SonarQube issues (if already fetched)

    Returns:
        List of Finding objects
    """
    # Get run from database
    run = get_run(run_id)
    if not run:
        print_error(f"Run not found: {run_id}")
        return []

    run_dir = Path(run.run_dir)
    if not run_dir.exists():
        print_error(f"Run directory not found: {run_dir}")
        return []

    print_info(f"Analyzing run {run_id[:8]}...")

    # Load data
    logs = load_logs_from_run(run_dir)
    traces = load_traces_from_run(run_dir)
    lessons = load_lessons()
    code_context = load_code_context(run_dir)

    if not logs and not traces:
        print_error("No log or trace data found for this run")
        return []

    print_info(f"Found {len(logs)} logs, {len(traces)} traces, {len(lessons)} lessons")

    # Build prompt
    prompt = build_analysis_prompt(
        logs=logs,
        traces=traces,
        sonarqube_issues=sonarqube_issues or [],
        lessons=lessons,
        code_context=code_context,
    )

    # Call LLM
    print_info(f"Calling model: {settings.argus_model}")

    try:
        model = llm.get_model(settings.argus_model)
        response = model.prompt(prompt, system=SYSTEM_PROMPT)
        response_text = response.text()
    except Exception as e:
        print_error(f"Model call failed: {e}")
        update_run_status(run_id, "failed", settings.argus_model)
        return []

    # Parse response
    findings = parse_findings_response(response_text, run_id)

    if not findings:
        print_error("No findings extracted from model response")
        update_run_status(run_id, "complete", settings.argus_model)
        return []

    # Save findings
    for finding in findings:
        create_finding(finding)
        save_finding_to_disk(finding, run_dir)

    # Update run status
    update_run_status(run_id, "complete", settings.argus_model)

    print_success(f"Analysis complete: {len(findings)} findings")

    return findings


def check_model_available() -> tuple[bool, str]:
    """
    Check if the configured model is available via llm.

    Returns:
        Tuple of (available, model_name)
    """
    model_name = settings.argus_model
    try:
        model = llm.get_model(model_name)
        # Try to get the model's actual name
        return True, getattr(model, "model_id", model_name)
    except Exception:
        return False, model_name
