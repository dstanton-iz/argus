"""Argus CLI - AI-assisted exception analysis."""

import asyncio
import sys
from datetime import datetime, timedelta

import click

from . import __version__
from .analysis import analyze_run, check_model_available
from .config import settings
from .db import (
    count_findings_for_run,
    create_eval,
    create_run,
    get_avg_score_for_run,
    get_finding,
    get_findings_for_run,
    get_run,
    init_db,
    list_runs,
)
from .models import EvalScore, Run, Sentiment
from .output import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    render_finding_detail,
    render_findings_table,
    render_lessons_list,
    render_run_summary,
    render_runs_table,
    render_status_table,
)
from .sources.watchtower import WatchtowerClient


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """Argus - AI-assisted exception analysis for engineering teams."""
    # Initialize database on startup
    init_db()


# =============================================================================
# argus status
# =============================================================================


@cli.command()
def status() -> None:
    """Check connectivity and configuration."""

    async def _check() -> None:
        client = WatchtowerClient()

        # Check services
        services = []

        # Loki
        healthy, latency = await client.check_loki_health()
        services.append({
            "name": "Loki (logs)",
            "url": settings.watchtower_loki_url,
            "healthy": healthy,
            "latency_ms": latency,
        })

        # Tempo
        healthy, latency = await client.check_tempo_health()
        services.append({
            "name": "Tempo (traces)",
            "url": settings.watchtower_tempo_url,
            "healthy": healthy,
            "latency_ms": latency,
        })

        # Prometheus
        healthy, latency = await client.check_prometheus_health()
        services.append({
            "name": "Prometheus (metrics)",
            "url": settings.watchtower_prometheus_url,
            "healthy": healthy,
            "latency_ms": latency,
        })

        # SonarQube
        healthy, latency = await client.check_sonarqube_health()
        services.append({
            "name": "SonarQube (analysis)",
            "url": settings.sonarqube_url,
            "healthy": healthy,
            "latency_ms": latency,
        })

        # Model
        model_available, model_name = check_model_available()
        services.append({
            "name": f"LLM ({model_name})",
            "url": "via llm library",
            "healthy": model_available,
            "latency_ms": None,
        })

        render_status_table(services)

        # Summary
        healthy_count = sum(1 for s in services if s["healthy"])
        total_count = len(services)
        if healthy_count == total_count:
            print_success(f"All {total_count} services healthy")
        else:
            print_warning(f"{healthy_count}/{total_count} services healthy")

    asyncio.run(_check())


# =============================================================================
# argus run
# =============================================================================


@cli.command()
@click.option("--environment", "-e", type=click.Choice(["staging", "qa", "prod"]), help="Target environment")
@click.option("--service", "-s", help="Filter by service name")
@click.option("--error-code", "-c", help="Filter by error code")
@click.option("--hours", "-h", type=int, default=1, help="Look back N hours (default: 1)")
@click.option("--skip-analysis", is_flag=True, help="Fetch data only, don't run AI analysis")
def run(
    environment: str | None,
    service: str | None,
    error_code: str | None,
    hours: int,
    skip_analysis: bool,
) -> None:
    """Start a new analysis run - fetch data and analyze exceptions."""

    async def _run() -> None:
        # Interactive prompts if not provided
        if not environment:
            env = click.prompt(
                "Environment",
                type=click.Choice(["staging", "qa", "prod"]),
                default="staging",
            )
        else:
            env = environment

        if service is None:
            svc = click.prompt("Service name (or leave blank for all)", default="", show_default=False)
        else:
            svc = service

        if error_code is None:
            err = click.prompt("Error code filter (or leave blank)", default="", show_default=False)
        else:
            err = error_code

        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        # Create run record
        run_record = Run(
            environment=env,
            source="watchtower",
            query_params={
                "service": svc or None,
                "error_code": err or None,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        )

        # Create run directory
        run_dir = settings.runs_dir / run_record.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run_record.run_dir = str(run_dir.absolute())

        # Save to database
        create_run(run_record)
        print_info(f"Created run: {run_record.run_id[:8]}...")

        # Fetch data from Watchtower
        client = WatchtowerClient()

        # Query logs
        print_info("Fetching error logs from Loki...")
        try:
            logs = await client.query_loki_errors(
                service_name=svc or None,
                error_code=err or None,
                start_time=start_time,
                end_time=end_time,
            )
            print_info(f"Found {len(logs)} log entries")

            if logs:
                logs_dir = run_dir / "logs"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = logs_dir / f"errors_{timestamp}.csv"
                client.write_logs_to_csv(logs, csv_path)
                print_success(f"Saved logs to {csv_path}")
        except Exception as e:
            print_error(f"Failed to fetch logs: {e}")
            logs = []

        # Query error traces
        print_info("Fetching error traces from Tempo...")
        try:
            traces = await client.search_error_traces(
                service_name=svc or None,
                start_time=start_time,
                end_time=end_time,
            )
            print_info(f"Found {len(traces)} error traces")

            if traces:
                traces_dir = run_dir / "traces"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = traces_dir / f"errors_{timestamp}.csv"
                client.write_traces_to_csv(traces, csv_path)
                print_success(f"Saved traces to {csv_path}")
        except Exception as e:
            print_error(f"Failed to fetch traces: {e}")
            traces = []

        if not logs and not traces:
            print_warning("No exception data found for the given parameters")
            return

        # Run analysis
        if not skip_analysis:
            print_info("Running AI analysis...")
            findings = await analyze_run(run_record.run_id)

            if findings:
                console.print()
                render_findings_table(findings)
        else:
            print_info("Skipping analysis (--skip-analysis flag)")

        # Show summary
        console.print()
        print_success(f"Run complete: {run_record.run_id}")
        print_info(f"Run directory: {run_dir}")

    asyncio.run(_run())


# =============================================================================
# argus analyze
# =============================================================================


@cli.command()
@click.argument("run_id")
def analyze(run_id: str) -> None:
    """Re-run analysis on an existing run's data."""

    async def _analyze() -> None:
        # Resolve partial run ID
        runs = list_runs(limit=100)
        matching = [r for r in runs if r.run_id.startswith(run_id)]

        if not matching:
            print_error(f"No run found matching: {run_id}")
            sys.exit(1)
        elif len(matching) > 1:
            print_error(f"Multiple runs match '{run_id}'. Please be more specific.")
            for r in matching[:5]:
                print_info(f"  {r.run_id[:12]}... ({r.created_at})")
            sys.exit(1)

        full_run_id = matching[0].run_id

        findings = await analyze_run(full_run_id)

        if findings:
            console.print()
            render_findings_table(findings)

    asyncio.run(_analyze())


# =============================================================================
# argus runs
# =============================================================================


@cli.command()
@click.option("--limit", "-n", type=int, default=20, help="Number of runs to show")
def runs(limit: int) -> None:
    """List recent analysis runs."""
    run_list = list_runs(limit=limit)

    if not run_list:
        print_info("No runs yet. Use 'argus run' to start one.")
        return

    # Get finding counts and avg scores
    finding_counts = {}
    avg_scores = {}
    for r in run_list:
        finding_counts[r.run_id] = count_findings_for_run(r.run_id)
        avg_scores[r.run_id] = get_avg_score_for_run(r.run_id)

    render_runs_table(run_list, finding_counts, avg_scores)


# =============================================================================
# argus findings
# =============================================================================


@cli.command()
@click.argument("run_id")
@click.option("--detail", "-d", is_flag=True, help="Show full details for each finding")
def findings(run_id: str, detail: bool) -> None:
    """Show findings for a run."""
    # Resolve partial run ID
    run_list = list_runs(limit=100)
    matching = [r for r in run_list if r.run_id.startswith(run_id)]

    if not matching:
        print_error(f"No run found matching: {run_id}")
        sys.exit(1)
    elif len(matching) > 1:
        print_error(f"Multiple runs match '{run_id}'. Please be more specific.")
        sys.exit(1)

    full_run_id = matching[0].run_id
    run_record = get_run(full_run_id)

    if run_record:
        finding_count = count_findings_for_run(full_run_id)
        render_run_summary(run_record, finding_count)
        console.print()

    finding_list = get_findings_for_run(full_run_id)

    if detail:
        for finding in finding_list:
            render_finding_detail(finding)
            console.print()
    else:
        render_findings_table(finding_list)


# =============================================================================
# argus score
# =============================================================================


@cli.command()
@click.argument("run_id")
def score(run_id: str) -> None:
    """Score findings for a run (eval workflow)."""
    # Resolve partial run ID
    run_list = list_runs(limit=100)
    matching = [r for r in run_list if r.run_id.startswith(run_id)]

    if not matching:
        print_error(f"No run found matching: {run_id}")
        sys.exit(1)

    full_run_id = matching[0].run_id
    finding_list = get_findings_for_run(full_run_id)

    if not finding_list:
        print_info("No findings to score for this run.")
        return

    print_info(f"Scoring {len(finding_list)} findings for run {full_run_id[:8]}...")
    console.print()

    for i, finding in enumerate(finding_list, 1):
        console.print(f"[bold]Finding {i}/{len(finding_list)}[/bold]")
        render_finding_detail(finding)
        console.print()

        # Get score
        score_val = click.prompt(
            "Score (1-5, or 's' to skip)",
            default="s",
        )

        if score_val.lower() == "s":
            print_info("Skipped")
            console.print()
            continue

        try:
            score_int = int(score_val)
            if not 1 <= score_int <= 5:
                print_error("Score must be 1-5")
                continue
        except ValueError:
            print_error("Invalid score")
            continue

        # Get code owner comment
        comment = click.prompt(
            "Code owner comment (or leave blank)",
            default="",
            show_default=False,
        )

        # Get notes
        notes = click.prompt("Your notes (or leave blank)", default="", show_default=False)

        # Auto-classify sentiment (simple heuristic for now, could use llm)
        sentiment = None
        if comment:
            comment_lower = comment.lower()
            if any(w in comment_lower for w in ["great", "perfect", "good", "thanks", "helpful", "lgtm"]):
                sentiment = Sentiment.POSITIVE
            elif any(w in comment_lower for w in ["wrong", "bad", "incorrect", "no", "nope", "waste"]):
                sentiment = Sentiment.NEGATIVE
            else:
                sentiment = Sentiment.NEUTRAL

        # Save eval
        eval_score = EvalScore(
            finding_id=finding.finding_id,
            score=score_int,
            code_owner_comment=comment,
            sentiment=sentiment,
            notes=notes,
        )
        create_eval(eval_score)

        print_success(f"Saved score: {score_int}/5")
        console.print()

    print_success("Scoring complete!")


# =============================================================================
# argus lessons
# =============================================================================


@cli.command()
@click.option("--promote", "-p", help="Finding ID to promote to a lesson")
def lessons(promote: str | None) -> None:
    """List or create lessons (institutional memory)."""
    settings.ensure_directories()

    if promote:
        # Promote a finding to a lesson
        finding = get_finding(promote)
        if not finding:
            # Try partial match
            all_runs = list_runs(limit=100)
            for r in all_runs:
                finding_list = get_findings_for_run(r.run_id)
                for f in finding_list:
                    if f.finding_id.startswith(promote):
                        finding = f
                        break
                if finding:
                    break

        if not finding:
            print_error(f"Finding not found: {promote}")
            sys.exit(1)

        # Get lesson name
        name = click.prompt("Lesson name (will be saved as <name>.md)")
        name = name.replace(" ", "_").lower()
        if not name.endswith(".md"):
            name += ".md"

        # Create lesson file
        lesson_path = settings.lessons_dir / name
        content = f"""# {finding.summary}

**Original Finding:** {finding.finding_id}
**Error Code:** {finding.error_code or "N/A"}
**Severity:** {finding.severity.value}

## Pattern

{finding.root_cause or "Root cause not determined"}

## Solution

{finding.fix_suggestion or "No fix suggestion"}

## Notes

Promoted from finding on {datetime.now().isoformat()}
"""
        lesson_path.write_text(content)
        print_success(f"Created lesson: {lesson_path}")
        return

    # List lessons
    lesson_files = sorted(settings.lessons_dir.glob("*.md"))
    render_lessons_list([f.name for f in lesson_files])


# =============================================================================
# Entry point
# =============================================================================


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
