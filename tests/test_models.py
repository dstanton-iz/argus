"""Tests for Argus data models."""

import pytest

from argus.models import EvalScore, Finding, Run, RunStatus, Sentiment, Severity


class TestEnums:
    """Test enum definitions."""

    def test_run_status_values(self) -> None:
        """RunStatus has expected values."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.COMPLETE.value == "complete"
        assert RunStatus.FAILED.value == "failed"

    def test_severity_values(self) -> None:
        """Severity has expected P0-P3 values."""
        assert Severity.P0.value == "P0"
        assert Severity.P1.value == "P1"
        assert Severity.P2.value == "P2"
        assert Severity.P3.value == "P3"

    def test_sentiment_values(self) -> None:
        """Sentiment has expected values."""
        assert Sentiment.POSITIVE.value == "positive"
        assert Sentiment.NEUTRAL.value == "neutral"
        assert Sentiment.NEGATIVE.value == "negative"


class TestRun:
    """Test Run dataclass."""

    def test_default_values(self) -> None:
        """Run has sensible defaults."""
        run = Run()
        assert run.run_id  # Auto-generated UUID
        assert run.created_at  # Auto-generated timestamp
        assert run.source == "watchtower"
        assert run.status == RunStatus.PENDING
        assert run.query_params == {}

    def test_custom_values(self) -> None:
        """Run accepts custom values."""
        run = Run(
            run_id="test-123",
            environment="staging",
            source="watchtower",
            model="claude-3-opus",
            status=RunStatus.COMPLETE,
        )
        assert run.run_id == "test-123"
        assert run.environment == "staging"
        assert run.model == "claude-3-opus"
        assert run.status == RunStatus.COMPLETE

    def test_to_dict(self) -> None:
        """Run.to_dict serializes correctly."""
        run = Run(
            run_id="test-123",
            created_at="2024-01-01T00:00:00",
            environment="prod",
            status=RunStatus.COMPLETE,
            query_params={"service": "api"},
        )
        data = run.to_dict()
        assert data["run_id"] == "test-123"
        assert data["environment"] == "prod"
        assert data["status"] == "complete"  # Enum value, not enum
        assert data["query_params"] == {"service": "api"}

    def test_from_dict(self) -> None:
        """Run.from_dict deserializes correctly."""
        data = {
            "run_id": "test-456",
            "created_at": "2024-01-01T00:00:00",
            "environment": "staging",
            "source": "watchtower",
            "model": "gpt-4",
            "query_params": {"hours": 1},
            "status": "failed",
            "run_dir": "/tmp/runs/test-456",
        }
        run = Run.from_dict(data)
        assert run.run_id == "test-456"
        assert run.environment == "staging"
        assert run.status == RunStatus.FAILED
        assert run.run_dir == "/tmp/runs/test-456"

    def test_from_dict_missing_optional(self) -> None:
        """Run.from_dict handles missing optional fields."""
        data = {
            "run_id": "test-789",
            "created_at": "2024-01-01T00:00:00",
        }
        run = Run.from_dict(data)
        assert run.run_id == "test-789"
        assert run.environment == ""
        assert run.source == "watchtower"
        assert run.status == RunStatus.PENDING


class TestFinding:
    """Test Finding dataclass."""

    def test_default_values(self) -> None:
        """Finding has sensible defaults."""
        finding = Finding()
        assert finding.finding_id  # Auto-generated UUID
        assert finding.severity == Severity.P3
        assert finding.is_noise is False

    def test_custom_values(self) -> None:
        """Finding accepts custom values."""
        finding = Finding(
            finding_id="find-001",
            run_id="run-001",
            error_code="ERR_CONNECTION_REFUSED",
            severity=Severity.P0,
            summary="Database connection failed",
            is_noise=False,
        )
        assert finding.error_code == "ERR_CONNECTION_REFUSED"
        assert finding.severity == Severity.P0
        assert finding.summary == "Database connection failed"

    def test_to_dict(self) -> None:
        """Finding.to_dict serializes correctly."""
        finding = Finding(
            finding_id="find-002",
            run_id="run-001",
            severity=Severity.P1,
            summary="API timeout",
            is_noise=True,
        )
        data = finding.to_dict()
        assert data["finding_id"] == "find-002"
        assert data["severity"] == "P1"  # Enum value
        assert data["is_noise"] is True

    def test_from_dict(self) -> None:
        """Finding.from_dict deserializes correctly."""
        data = {
            "finding_id": "find-003",
            "run_id": "run-002",
            "error_code": "500",
            "operation_id": "op-123",
            "severity": "P2",
            "summary": "Degraded performance",
            "analysis": "Full analysis here",
            "root_cause": "Memory leak",
            "fix_suggestion": "Add GC tuning",
            "is_noise": False,
            "matched_lesson": "memory_leak.md",
            "pr_url": "https://github.com/org/repo/pull/123",
            "pr_status": "open",
        }
        finding = Finding.from_dict(data)
        assert finding.severity == Severity.P2
        assert finding.root_cause == "Memory leak"
        assert finding.matched_lesson == "memory_leak.md"
        assert finding.pr_status == "open"


class TestEvalScore:
    """Test EvalScore dataclass."""

    def test_default_values(self) -> None:
        """EvalScore has sensible defaults."""
        eval_score = EvalScore()
        assert eval_score.eval_id  # Auto-generated UUID
        assert eval_score.scored_at  # Auto-generated timestamp
        assert eval_score.score == 3
        assert eval_score.sentiment is None

    def test_score_validation(self) -> None:
        """EvalScore validates score range."""
        # Valid scores
        for score in [1, 2, 3, 4, 5]:
            EvalScore(score=score)  # Should not raise

        # Invalid scores
        with pytest.raises(ValueError, match="Score must be 1-5"):
            EvalScore(score=0)

        with pytest.raises(ValueError, match="Score must be 1-5"):
            EvalScore(score=6)

    def test_to_dict(self) -> None:
        """EvalScore.to_dict serializes correctly."""
        eval_score = EvalScore(
            eval_id="eval-001",
            finding_id="find-001",
            scored_at="2024-01-01T00:00:00",
            score=4,
            sentiment=Sentiment.POSITIVE,
            code_owner_comment="Great fix!",
        )
        data = eval_score.to_dict()
        assert data["score"] == 4
        assert data["sentiment"] == "positive"  # Enum value
        assert data["code_owner_comment"] == "Great fix!"

    def test_to_dict_no_sentiment(self) -> None:
        """EvalScore.to_dict handles null sentiment."""
        eval_score = EvalScore(score=3)
        data = eval_score.to_dict()
        assert data["sentiment"] is None

    def test_from_dict(self) -> None:
        """EvalScore.from_dict deserializes correctly."""
        data = {
            "eval_id": "eval-002",
            "finding_id": "find-002",
            "scored_at": "2024-01-01T12:00:00",
            "score": 2,
            "code_owner_comment": "Not helpful",
            "sentiment": "negative",
            "notes": "Suggested wrong fix",
        }
        eval_score = EvalScore.from_dict(data)
        assert eval_score.score == 2
        assert eval_score.sentiment == Sentiment.NEGATIVE
        assert eval_score.notes == "Suggested wrong fix"

    def test_from_dict_no_sentiment(self) -> None:
        """EvalScore.from_dict handles missing sentiment."""
        data = {
            "eval_id": "eval-003",
            "finding_id": "find-003",
            "score": 3,
        }
        eval_score = EvalScore.from_dict(data)
        assert eval_score.sentiment is None
