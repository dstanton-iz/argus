"""Tests for Argus database operations."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from argus.db import (
    count_findings_for_run,
    create_eval,
    create_finding,
    create_run,
    get_avg_score_for_run,
    get_connection,
    get_evals_for_finding,
    get_finding,
    get_findings_for_run,
    get_run,
    init_db,
    list_runs,
    update_run_status,
)
from argus.models import EvalScore, Finding, Run, RunStatus, Sentiment, Severity


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with patch("argus.db.settings") as mock_settings:
            mock_settings.db_path = db_path
            mock_settings.ensure_directories = lambda: db_path.parent.mkdir(
                parents=True, exist_ok=True
            )
            init_db()
            yield db_path, mock_settings


class TestConnection:
    """Test database connection."""

    def test_get_connection_creates_db(self, temp_db) -> None:
        """get_connection creates database file."""
        db_path, mock_settings = temp_db
        conn = get_connection()
        conn.close()
        assert db_path.exists()


class TestRunOperations:
    """Test run CRUD operations."""

    def test_create_run(self, temp_db) -> None:
        """create_run inserts a run record."""
        run = Run(
            run_id="test-run-001",
            environment="staging",
            source="watchtower",
            query_params={"service": "api"},
        )
        result = create_run(run)
        assert result.run_id == "test-run-001"

    def test_get_run(self, temp_db) -> None:
        """get_run retrieves a run by ID."""
        run = Run(
            run_id="test-run-002",
            environment="prod",
            model="claude-3-sonnet",
        )
        create_run(run)

        retrieved = get_run("test-run-002")
        assert retrieved is not None
        assert retrieved.run_id == "test-run-002"
        assert retrieved.environment == "prod"
        assert retrieved.model == "claude-3-sonnet"

    def test_get_run_not_found(self, temp_db) -> None:
        """get_run returns None for missing run."""
        result = get_run("nonexistent")
        assert result is None

    def test_update_run_status(self, temp_db) -> None:
        """update_run_status updates status field."""
        run = Run(run_id="test-run-003")
        create_run(run)

        update_run_status("test-run-003", "complete")

        retrieved = get_run("test-run-003")
        assert retrieved.status == RunStatus.COMPLETE

    def test_update_run_status_with_model(self, temp_db) -> None:
        """update_run_status updates both status and model."""
        run = Run(run_id="test-run-004")
        create_run(run)

        update_run_status("test-run-004", "complete", "gpt-4")

        retrieved = get_run("test-run-004")
        assert retrieved.status == RunStatus.COMPLETE
        assert retrieved.model == "gpt-4"

    def test_list_runs(self, temp_db) -> None:
        """list_runs returns recent runs in order."""
        for i in range(5):
            run = Run(run_id=f"test-run-{i:03d}")
            create_run(run)

        runs = list_runs(limit=3)
        assert len(runs) == 3
        # Most recent first (by created_at DESC)
        assert runs[0].run_id == "test-run-004"

    def test_list_runs_empty(self, temp_db) -> None:
        """list_runs returns empty list when no runs."""
        runs = list_runs()
        assert runs == []


class TestFindingOperations:
    """Test finding CRUD operations."""

    def test_create_finding(self, temp_db) -> None:
        """create_finding inserts a finding record."""
        # Create parent run first
        run = Run(run_id="test-run-f01")
        create_run(run)

        finding = Finding(
            finding_id="find-001",
            run_id="test-run-f01",
            error_code="ERR_500",
            severity=Severity.P1,
            summary="Server error",
        )
        result = create_finding(finding)
        assert result.finding_id == "find-001"

    def test_get_finding(self, temp_db) -> None:
        """get_finding retrieves a finding by ID."""
        run = Run(run_id="test-run-f02")
        create_run(run)

        finding = Finding(
            finding_id="find-002",
            run_id="test-run-f02",
            error_code="ERR_TIMEOUT",
            severity=Severity.P2,
            summary="Request timeout",
            root_cause="Database slow",
            fix_suggestion="Add index",
            is_noise=True,
        )
        create_finding(finding)

        retrieved = get_finding("find-002")
        assert retrieved is not None
        assert retrieved.error_code == "ERR_TIMEOUT"
        assert retrieved.severity == Severity.P2
        assert retrieved.is_noise is True

    def test_get_finding_not_found(self, temp_db) -> None:
        """get_finding returns None for missing finding."""
        result = get_finding("nonexistent")
        assert result is None

    def test_get_findings_for_run(self, temp_db) -> None:
        """get_findings_for_run returns all findings for a run."""
        run = Run(run_id="test-run-f03")
        create_run(run)

        for i, sev in enumerate([Severity.P0, Severity.P2, Severity.P1]):
            finding = Finding(
                finding_id=f"find-{i:03d}",
                run_id="test-run-f03",
                severity=sev,
                summary=f"Finding {i}",
            )
            create_finding(finding)

        findings = get_findings_for_run("test-run-f03")
        assert len(findings) == 3
        # Ordered by severity (P0 < P1 < P2 alphabetically)
        assert findings[0].severity == Severity.P0

    def test_get_findings_for_run_empty(self, temp_db) -> None:
        """get_findings_for_run returns empty list when no findings."""
        run = Run(run_id="test-run-f04")
        create_run(run)

        findings = get_findings_for_run("test-run-f04")
        assert findings == []

    def test_count_findings_for_run(self, temp_db) -> None:
        """count_findings_for_run returns correct count."""
        run = Run(run_id="test-run-f05")
        create_run(run)

        for i in range(4):
            finding = Finding(
                finding_id=f"count-find-{i}",
                run_id="test-run-f05",
                summary=f"Finding {i}",
            )
            create_finding(finding)

        count = count_findings_for_run("test-run-f05")
        assert count == 4

    def test_count_findings_for_run_empty(self, temp_db) -> None:
        """count_findings_for_run returns 0 when no findings."""
        run = Run(run_id="test-run-f06")
        create_run(run)

        count = count_findings_for_run("test-run-f06")
        assert count == 0


class TestEvalOperations:
    """Test eval CRUD operations."""

    def test_create_eval(self, temp_db) -> None:
        """create_eval inserts an eval record."""
        run = Run(run_id="test-run-e01")
        create_run(run)
        finding = Finding(finding_id="find-e01", run_id="test-run-e01")
        create_finding(finding)

        eval_score = EvalScore(
            eval_id="eval-001",
            finding_id="find-e01",
            score=4,
            code_owner_comment="Good fix",
            sentiment=Sentiment.POSITIVE,
        )
        result = create_eval(eval_score)
        assert result.eval_id == "eval-001"

    def test_get_evals_for_finding(self, temp_db) -> None:
        """get_evals_for_finding returns all evals for a finding."""
        run = Run(run_id="test-run-e02")
        create_run(run)
        finding = Finding(finding_id="find-e02", run_id="test-run-e02")
        create_finding(finding)

        for i, score in enumerate([3, 4, 5]):
            eval_score = EvalScore(
                eval_id=f"eval-e{i:02d}",
                finding_id="find-e02",
                score=score,
            )
            create_eval(eval_score)

        evals = get_evals_for_finding("find-e02")
        assert len(evals) == 3

    def test_get_avg_score_for_run(self, temp_db) -> None:
        """get_avg_score_for_run returns average of all eval scores."""
        run = Run(run_id="test-run-e03")
        create_run(run)

        # Two findings with evals
        finding1 = Finding(finding_id="find-avg1", run_id="test-run-e03")
        finding2 = Finding(finding_id="find-avg2", run_id="test-run-e03")
        create_finding(finding1)
        create_finding(finding2)

        create_eval(EvalScore(eval_id="eval-avg1", finding_id="find-avg1", score=4))
        create_eval(EvalScore(eval_id="eval-avg2", finding_id="find-avg2", score=2))

        avg = get_avg_score_for_run("test-run-e03")
        assert avg == 3.0  # (4 + 2) / 2

    def test_get_avg_score_for_run_no_evals(self, temp_db) -> None:
        """get_avg_score_for_run returns None when no evals."""
        run = Run(run_id="test-run-e04")
        create_run(run)

        avg = get_avg_score_for_run("test-run-e04")
        assert avg is None

    def test_get_avg_score_for_run_nonexistent(self, temp_db) -> None:
        """get_avg_score_for_run returns None for nonexistent run."""
        avg = get_avg_score_for_run("nonexistent")
        assert avg is None
