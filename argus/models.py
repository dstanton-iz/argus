"""Data models for Argus."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class RunStatus(str, Enum):
    """Status of an analysis run."""

    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


class Severity(str, Enum):
    """Exception severity levels."""

    P0 = "P0"  # Production down
    P1 = "P1"  # Major feature broken
    P2 = "P2"  # Degraded
    P3 = "P3"  # Minor/cosmetic


class Sentiment(str, Enum):
    """Code owner comment sentiment."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass
class Run:
    """Represents a single analysis run."""

    run_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    environment: str = ""  # staging, qa, prod
    source: str = "watchtower"  # watchtower or sumo (future)
    model: str = ""  # llm model string used
    query_params: dict[str, Any] = field(default_factory=dict)
    status: RunStatus = RunStatus.PENDING
    run_dir: str = ""  # Absolute path to run files

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "environment": self.environment,
            "source": self.source,
            "model": self.model,
            "query_params": self.query_params,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "run_dir": self.run_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Run":
        """Create from dictionary."""
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = RunStatus(status)
        return cls(
            run_id=data["run_id"],
            created_at=data["created_at"],
            environment=data.get("environment", ""),
            source=data.get("source", "watchtower"),
            model=data.get("model", ""),
            query_params=data.get("query_params", {}),
            status=status,
            run_dir=data.get("run_dir", ""),
        )


@dataclass
class Finding:
    """Represents an exception/error pattern identified in a run."""

    finding_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = ""
    error_code: str = ""
    operation_id: str = ""  # Nullable
    severity: Severity = Severity.P3
    summary: str = ""  # One-line description
    analysis: str = ""  # Full AI analysis text
    root_cause: str = ""
    fix_suggestion: str = ""
    is_noise: bool = False  # Background job / cache loader noise
    matched_lesson: str = ""  # Reference to lesson file if applicable
    pr_url: str = ""  # Nullable
    pr_status: str = ""  # draft, open, merged, closed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "finding_id": self.finding_id,
            "run_id": self.run_id,
            "error_code": self.error_code,
            "operation_id": self.operation_id,
            "severity": self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "summary": self.summary,
            "analysis": self.analysis,
            "root_cause": self.root_cause,
            "fix_suggestion": self.fix_suggestion,
            "is_noise": self.is_noise,
            "matched_lesson": self.matched_lesson,
            "pr_url": self.pr_url,
            "pr_status": self.pr_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        """Create from dictionary."""
        severity = data.get("severity", "P3")
        if isinstance(severity, str):
            severity = Severity(severity)
        return cls(
            finding_id=data["finding_id"],
            run_id=data["run_id"],
            error_code=data.get("error_code", ""),
            operation_id=data.get("operation_id", ""),
            severity=severity,
            summary=data.get("summary", ""),
            analysis=data.get("analysis", ""),
            root_cause=data.get("root_cause", ""),
            fix_suggestion=data.get("fix_suggestion", ""),
            is_noise=data.get("is_noise", False),
            matched_lesson=data.get("matched_lesson", ""),
            pr_url=data.get("pr_url", ""),
            pr_status=data.get("pr_status", ""),
        )


@dataclass
class EvalScore:
    """Outcome scoring for a finding."""

    eval_id: str = field(default_factory=lambda: str(uuid4()))
    finding_id: str = ""
    scored_at: str = field(default_factory=lambda: datetime.now().isoformat())
    score: int = 3  # 1-5
    code_owner_comment: str = ""  # Raw comment text
    sentiment: Sentiment | None = None  # Auto-classified
    notes: str = ""  # Scorer's notes

    def __post_init__(self) -> None:
        """Validate score is in range."""
        if not 1 <= self.score <= 5:
            raise ValueError(f"Score must be 1-5, got {self.score}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "eval_id": self.eval_id,
            "finding_id": self.finding_id,
            "scored_at": self.scored_at,
            "score": self.score,
            "code_owner_comment": self.code_owner_comment,
            "sentiment": self.sentiment.value if self.sentiment else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalScore":
        """Create from dictionary."""
        sentiment = data.get("sentiment")
        if sentiment and isinstance(sentiment, str):
            sentiment = Sentiment(sentiment)
        return cls(
            eval_id=data["eval_id"],
            finding_id=data["finding_id"],
            scored_at=data.get("scored_at", ""),
            score=data["score"],
            code_owner_comment=data.get("code_owner_comment", ""),
            sentiment=sentiment,
            notes=data.get("notes", ""),
        )
