"""Tests for AI analysis module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from argus.analysis import (
    PROMPT_SEPARATOR,
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_prompt_for_run,
    check_model_available,
    format_full_prompt,
    load_lessons,
    load_logs_from_run,
    load_traces_from_run,
    parse_findings_response,
)
from argus.models import Run, Severity


class TestBuildAnalysisPrompt:
    """Test prompt construction."""

    def test_empty_data(self) -> None:
        """build_analysis_prompt handles empty data."""
        prompt = build_analysis_prompt(
            logs=[],
            traces=[],
            sonarqube_issues=[],
            lessons=[],
        )
        assert "## Your Task" in prompt
        assert "Analyze the above exception data" in prompt

    def test_with_logs(self) -> None:
        """build_analysis_prompt includes log entries."""
        logs = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "line": "Error: Connection refused to database",
                "labels": {"service_name": "api", "job": "backend"},
            }
        ]
        prompt = build_analysis_prompt(
            logs=logs,
            traces=[],
            sonarqube_issues=[],
            lessons=[],
        )
        assert "## Exception Logs" in prompt
        assert "Connection refused to database" in prompt
        assert "api" in prompt

    def test_with_traces(self) -> None:
        """build_analysis_prompt includes trace entries."""
        traces = [
            {
                "traceID": "abc123",
                "rootServiceName": "frontend",
                "rootTraceName": "GET /api/users",
                "durationMs": 1500,
            }
        ]
        prompt = build_analysis_prompt(
            logs=[],
            traces=traces,
            sonarqube_issues=[],
            lessons=[],
        )
        assert "## Error Traces" in prompt
        assert "frontend" in prompt
        assert "GET /api/users" in prompt
        assert "1500ms" in prompt

    def test_with_sonarqube_issues(self) -> None:
        """build_analysis_prompt includes SonarQube issues."""
        issues = [
            {
                "severity": "CRITICAL",
                "component": "project:src/api/handler.py",
                "message": "Null pointer dereference",
            }
        ]
        prompt = build_analysis_prompt(
            logs=[],
            traces=[],
            sonarqube_issues=issues,
            lessons=[],
        )
        assert "## SonarQube Issues" in prompt
        assert "CRITICAL" in prompt
        assert "handler.py" in prompt
        assert "Null pointer" in prompt

    def test_with_lessons(self) -> None:
        """build_analysis_prompt includes lesson content."""
        lessons = [
            ("database_timeouts.md", "# Database Timeouts\n\nWhen DB times out, check connection pool."),
        ]
        prompt = build_analysis_prompt(
            logs=[],
            traces=[],
            sonarqube_issues=[],
            lessons=lessons,
        )
        assert "## Institutional Memory" in prompt
        assert "database_timeouts.md" in prompt
        assert "connection pool" in prompt

    def test_with_code_context(self) -> None:
        """build_analysis_prompt includes code context."""
        prompt = build_analysis_prompt(
            logs=[],
            traces=[],
            sonarqube_issues=[],
            lessons=[],
            code_context="def handler():\n    raise Exception('test')",
        )
        assert "## Code Context" in prompt
        assert "def handler()" in prompt

    def test_truncates_long_logs(self) -> None:
        """build_analysis_prompt truncates very long log lines."""
        long_line = "x" * 5000
        logs = [{"timestamp": "2024-01-01", "line": long_line, "labels": {}}]
        prompt = build_analysis_prompt(
            logs=logs,
            traces=[],
            sonarqube_issues=[],
            lessons=[],
        )
        # Should be truncated to 2000 chars
        assert len(prompt) < len(long_line) + 1000

    def test_limits_log_count(self) -> None:
        """build_analysis_prompt limits to 50 logs."""
        logs = [
            {"timestamp": "2024-01-01", "line": f"Log {i}", "labels": {"job": "test"}}
            for i in range(100)
        ]
        prompt = build_analysis_prompt(
            logs=logs,
            traces=[],
            sonarqube_issues=[],
            lessons=[],
        )
        assert "... and 50 more log entries" in prompt


class TestParseFindings:
    """Test LLM response parsing."""

    def test_parse_valid_json(self) -> None:
        """parse_findings_response extracts findings from valid JSON."""
        response = json.dumps({
            "findings": [
                {
                    "error_code": "ERR_500",
                    "operation_id": "op-123",
                    "severity": "P1",
                    "summary": "Database connection failed",
                    "root_cause": "Connection pool exhausted",
                    "fix_suggestion": "Increase pool size",
                    "is_noise": False,
                    "matched_lesson": None,
                }
            ]
        })
        findings = parse_findings_response(response, "run-001")

        assert len(findings) == 1
        assert findings[0].error_code == "ERR_500"
        assert findings[0].severity == Severity.P1
        assert findings[0].root_cause == "Connection pool exhausted"
        assert findings[0].run_id == "run-001"

    def test_parse_json_in_markdown_block(self) -> None:
        """parse_findings_response handles JSON in markdown code block."""
        response = """Here is my analysis:

```json
{
    "findings": [
        {
            "severity": "P2",
            "summary": "API timeout",
            "root_cause": "Slow downstream",
            "fix_suggestion": "Add timeout"
        }
    ]
}
```

Let me know if you need more details."""

        findings = parse_findings_response(response, "run-002")

        assert len(findings) == 1
        assert findings[0].severity == Severity.P2
        assert findings[0].summary == "API timeout"

    def test_parse_multiple_findings(self) -> None:
        """parse_findings_response handles multiple findings."""
        response = json.dumps({
            "findings": [
                {"severity": "P0", "summary": "Critical error 1"},
                {"severity": "P1", "summary": "Major error 2"},
                {"severity": "P3", "summary": "Minor error 3"},
            ]
        })
        findings = parse_findings_response(response, "run-003")

        assert len(findings) == 3
        assert findings[0].severity == Severity.P0
        assert findings[1].severity == Severity.P1
        assert findings[2].severity == Severity.P3

    def test_parse_handles_noise_flag(self) -> None:
        """parse_findings_response correctly parses is_noise."""
        response = json.dumps({
            "findings": [
                {"severity": "P3", "summary": "Background job noise", "is_noise": True},
            ]
        })
        findings = parse_findings_response(response, "run-004")

        assert findings[0].is_noise is True

    def test_parse_invalid_json(self) -> None:
        """parse_findings_response returns empty list for invalid JSON."""
        response = "This is not valid JSON at all"
        findings = parse_findings_response(response, "run-005")
        assert findings == []

    def test_parse_missing_findings_key(self) -> None:
        """parse_findings_response handles missing findings key."""
        response = json.dumps({"analysis": "some other format"})
        findings = parse_findings_response(response, "run-006")
        assert findings == []

    def test_parse_default_severity(self) -> None:
        """parse_findings_response defaults to P3 for unknown severity."""
        response = json.dumps({
            "findings": [{"summary": "Error", "severity": "UNKNOWN"}]
        })
        findings = parse_findings_response(response, "run-007")
        assert findings[0].severity == Severity.P3

    def test_parse_null_values(self) -> None:
        """parse_findings_response handles null values."""
        response = json.dumps({
            "findings": [
                {
                    "severity": "P2",
                    "summary": "Error",
                    "error_code": None,
                    "operation_id": None,
                    "matched_lesson": None,
                }
            ]
        })
        findings = parse_findings_response(response, "run-008")

        assert findings[0].error_code == ""
        assert findings[0].operation_id == ""
        assert findings[0].matched_lesson == ""


class TestLoadLessons:
    """Test lesson loading."""

    def test_load_lessons_from_directory(self) -> None:
        """load_lessons reads all .md files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lessons_dir = Path(tmpdir)
            (lessons_dir / "lesson1.md").write_text("# Lesson 1\nContent 1")
            (lessons_dir / "lesson2.md").write_text("# Lesson 2\nContent 2")
            (lessons_dir / "not_a_lesson.txt").write_text("Ignored")

            with patch("argus.analysis.settings") as mock_settings:
                mock_settings.lessons_dir = lessons_dir
                lessons = load_lessons()

            assert len(lessons) == 2
            assert any(name == "lesson1.md" for name, _ in lessons)
            assert any("Content 1" in content for _, content in lessons)

    def test_load_lessons_empty_directory(self) -> None:
        """load_lessons returns empty list for empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("argus.analysis.settings") as mock_settings:
                mock_settings.lessons_dir = Path(tmpdir)
                lessons = load_lessons()

            assert lessons == []

    def test_load_lessons_no_directory(self) -> None:
        """load_lessons returns empty list when directory doesn't exist."""
        with patch("argus.analysis.settings") as mock_settings:
            mock_settings.lessons_dir = Path("/nonexistent/path")
            lessons = load_lessons()

        assert lessons == []


class TestLoadLogsFromRun:
    """Test loading logs from run directory."""

    def test_load_logs_from_csv(self) -> None:
        """load_logs_from_run reads CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            logs_dir = run_dir / "logs"
            logs_dir.mkdir()

            csv_content = "timestamp,line,service_name\n2024-01-01,Error,api\n"
            (logs_dir / "errors.csv").write_text(csv_content)

            logs = load_logs_from_run(run_dir)

            assert len(logs) == 1
            assert logs[0]["timestamp"] == "2024-01-01"
            assert logs[0]["line"] == "Error"

    def test_load_logs_no_directory(self) -> None:
        """load_logs_from_run returns empty when no logs dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            logs = load_logs_from_run(run_dir)
            assert logs == []


class TestLoadTracesFromRun:
    """Test loading traces from run directory."""

    def test_load_traces_from_csv(self) -> None:
        """load_traces_from_run reads CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            traces_dir = run_dir / "traces"
            traces_dir.mkdir()

            csv_content = "traceID,rootServiceName,durationMs\nabc123,api,150\n"
            (traces_dir / "traces.csv").write_text(csv_content)

            traces = load_traces_from_run(run_dir)

            assert len(traces) == 1
            assert traces[0]["traceID"] == "abc123"

    def test_load_traces_no_directory(self) -> None:
        """load_traces_from_run returns empty when no traces dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            traces = load_traces_from_run(run_dir)
            assert traces == []


class TestCheckModelAvailable:
    """Test model availability check."""

    def test_model_available(self) -> None:
        """check_model_available returns True when model loads."""
        mock_model = MagicMock()
        mock_model.model_id = "claude-3-sonnet-20240229"

        with patch("llm.get_model", return_value=mock_model):
            with patch("argus.analysis.settings") as mock_settings:
                mock_settings.argus_model = "claude-3-sonnet"
                available, name = check_model_available()

        assert available is True
        assert name == "claude-3-sonnet-20240229"

    def test_model_not_available(self) -> None:
        """check_model_available returns False when model fails to load."""
        with patch("llm.get_model", side_effect=Exception("Model not found")):
            with patch("argus.analysis.settings") as mock_settings:
                mock_settings.argus_model = "nonexistent-model"
                available, name = check_model_available()

        assert available is False
        assert name == "nonexistent-model"


class TestAnalyzeRun:
    """Test the main analyze_run function."""

    @pytest.mark.asyncio
    async def test_analyze_run_success(self) -> None:
        """analyze_run processes data and creates findings."""
        from argus.analysis import analyze_run
        from argus.models import Run, RunStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Create logs
            logs_dir = run_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "errors.csv").write_text(
                "timestamp,line,service_name\n2024-01-01,Error: DB failed,api\n"
            )

            # Mock run record
            mock_run = Run(
                run_id="test-run-001",
                run_dir=str(run_dir),
                status=RunStatus.PENDING,
            )

            # Mock model response
            mock_response = MagicMock()
            mock_response.text.return_value = json.dumps({
                "findings": [
                    {
                        "severity": "P1",
                        "summary": "Database connection failed",
                        "root_cause": "Connection timeout",
                        "fix_suggestion": "Increase timeout",
                    }
                ]
            })
            mock_model = MagicMock()
            mock_model.prompt.return_value = mock_response

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.create_finding"):
                    with patch("argus.analysis.update_run_status"):
                        with patch("llm.get_model", return_value=mock_model):
                            with patch("argus.analysis.settings") as mock_settings:
                                mock_settings.argus_model = "test-model"
                                mock_settings.lessons_dir = Path("/nonexistent")

                                findings = await analyze_run("test-run-001")

            assert len(findings) == 1
            assert findings[0].summary == "Database connection failed"
            mock_model.prompt.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_run_not_found(self) -> None:
        """analyze_run returns empty list when run not found."""
        from argus.analysis import analyze_run

        with patch("argus.analysis.get_run", return_value=None):
            findings = await analyze_run("nonexistent")

        assert findings == []

    @pytest.mark.asyncio
    async def test_analyze_run_no_data(self) -> None:
        """analyze_run returns empty list when no data."""
        from argus.analysis import analyze_run
        from argus.models import Run

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            mock_run = Run(run_id="test-run-002", run_dir=str(run_dir))

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.settings") as mock_settings:
                    mock_settings.lessons_dir = Path("/nonexistent")
                    findings = await analyze_run("test-run-002")

        assert findings == []

    @pytest.mark.asyncio
    async def test_analyze_run_model_error(self) -> None:
        """analyze_run handles model errors gracefully."""
        from argus.analysis import analyze_run
        from argus.models import Run

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)

            # Create logs
            logs_dir = run_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "errors.csv").write_text(
                "timestamp,line\n2024-01-01,Error\n"
            )

            mock_run = Run(run_id="test-run-003", run_dir=str(run_dir))
            mock_model = MagicMock()
            mock_model.prompt.side_effect = Exception("API error")

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.update_run_status"):
                    with patch("llm.get_model", return_value=mock_model):
                        with patch("argus.analysis.settings") as mock_settings:
                            mock_settings.argus_model = "test-model"
                            mock_settings.lessons_dir = Path("/nonexistent")

                            findings = await analyze_run("test-run-003")

            assert findings == []


class TestFormatFullPrompt:
    """Test prompt formatting for copy-paste output."""

    def test_format_includes_both_prompts(self) -> None:
        """format_full_prompt includes system and user prompt sections."""
        output = format_full_prompt("You are an analyst.", "Here are some logs.")
        assert "SYSTEM PROMPT" in output
        assert "ANALYSIS DATA" in output
        assert "You are an analyst." in output
        assert "Here are some logs." in output

    def test_format_uses_separator(self) -> None:
        """format_full_prompt uses visual separators."""
        output = format_full_prompt("system", "user")
        assert PROMPT_SEPARATOR in output


class TestBuildPromptForRun:
    """Test building prompt from a run without calling the LLM."""

    def test_returns_prompts_with_data(self) -> None:
        """build_prompt_for_run returns system and user prompt tuple."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            logs_dir = run_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "errors.csv").write_text(
                "timestamp,line,service_name\n2024-01-01,Error: DB failed,api\n"
            )

            mock_run = Run(
                run_id="prompt-test-001",
                run_dir=str(run_dir),
            )

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.settings") as mock_settings:
                    mock_settings.lessons_dir = Path("/nonexistent")
                    result = build_prompt_for_run("prompt-test-001")

            assert result is not None
            system_prompt, user_prompt = result
            assert system_prompt == SYSTEM_PROMPT
            assert "DB failed" in user_prompt

    def test_returns_none_when_no_data(self) -> None:
        """build_prompt_for_run returns None when no logs or traces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            mock_run = Run(run_id="prompt-test-002", run_dir=str(run_dir))

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.settings") as mock_settings:
                    mock_settings.lessons_dir = Path("/nonexistent")
                    result = build_prompt_for_run("prompt-test-002")

            assert result is None

    def test_returns_none_when_run_not_found(self) -> None:
        """build_prompt_for_run returns None for missing run."""
        with patch("argus.analysis.get_run", return_value=None):
            result = build_prompt_for_run("nonexistent")
        assert result is None

    def test_does_not_call_llm(self) -> None:
        """build_prompt_for_run never imports or calls llm."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            logs_dir = run_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "errors.csv").write_text(
                "timestamp,line\n2024-01-01,Error\n"
            )

            mock_run = Run(run_id="prompt-test-003", run_dir=str(run_dir))

            with patch("argus.analysis.get_run", return_value=mock_run):
                with patch("argus.analysis.settings") as mock_settings:
                    mock_settings.lessons_dir = Path("/nonexistent")
                    with patch("llm.get_model") as mock_get_model:
                        build_prompt_for_run("prompt-test-003")
                        mock_get_model.assert_not_called()
