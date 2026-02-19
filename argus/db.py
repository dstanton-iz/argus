"""SQLite database for Argus metadata."""

import json
import sqlite3

from .config import settings
from .models import EvalScore, Finding, Run


def get_connection() -> sqlite3.Connection:
    """Get a database connection, creating the database if needed."""
    settings.ensure_directories()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                environment TEXT,
                source TEXT,
                model TEXT,
                query_params TEXT,
                status TEXT,
                run_dir TEXT
            );

            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                error_code TEXT,
                operation_id TEXT,
                severity TEXT,
                summary TEXT,
                analysis TEXT,
                root_cause TEXT,
                fix_suggestion TEXT,
                is_noise INTEGER DEFAULT 0,
                matched_lesson TEXT,
                pr_url TEXT,
                pr_status TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS evals (
                eval_id TEXT PRIMARY KEY,
                finding_id TEXT NOT NULL,
                scored_at TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
                code_owner_comment TEXT,
                sentiment TEXT,
                notes TEXT,
                FOREIGN KEY (finding_id) REFERENCES findings(finding_id)
            );

            CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
            CREATE INDEX IF NOT EXISTS idx_evals_finding_id ON evals(finding_id);
        """)
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# Run operations
# =============================================================================


def create_run(run: Run) -> Run:
    """Insert a new run record."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO runs (run_id, created_at, environment, source, model, query_params, status, run_dir)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.created_at,
                run.environment,
                run.source,
                run.model,
                json.dumps(run.query_params),
                run.status.value,
                run.run_dir,
            ),
        )
        conn.commit()
        return run
    finally:
        conn.close()


def get_run(run_id: str) -> Run | None:
    """Get a run by ID."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["query_params"] = json.loads(data["query_params"] or "{}")
        return Run.from_dict(data)
    finally:
        conn.close()


def update_run_status(run_id: str, status: str, model: str | None = None) -> None:
    """Update a run's status and optionally its model."""
    conn = get_connection()
    try:
        if model:
            conn.execute(
                "UPDATE runs SET status = ?, model = ? WHERE run_id = ?",
                (status, model, run_id),
            )
        else:
            conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
        conn.commit()
    finally:
        conn.close()


def list_runs(limit: int = 20) -> list[Run]:
    """List recent runs."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        runs = []
        for row in rows:
            data = dict(row)
            data["query_params"] = json.loads(data["query_params"] or "{}")
            runs.append(Run.from_dict(data))
        return runs
    finally:
        conn.close()


# =============================================================================
# Finding operations
# =============================================================================


def create_finding(finding: Finding) -> Finding:
    """Insert a new finding record."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO findings (
                finding_id, run_id, error_code, operation_id, severity, summary,
                analysis, root_cause, fix_suggestion, is_noise, matched_lesson, pr_url, pr_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.finding_id,
                finding.run_id,
                finding.error_code,
                finding.operation_id,
                finding.severity.value,
                finding.summary,
                finding.analysis,
                finding.root_cause,
                finding.fix_suggestion,
                1 if finding.is_noise else 0,
                finding.matched_lesson,
                finding.pr_url,
                finding.pr_status,
            ),
        )
        conn.commit()
        return finding
    finally:
        conn.close()


def get_findings_for_run(run_id: str) -> list[Finding]:
    """Get all findings for a run."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM findings WHERE run_id = ? ORDER BY severity", (run_id,)
        ).fetchall()
        findings = []
        for row in rows:
            data = dict(row)
            data["is_noise"] = bool(data["is_noise"])
            findings.append(Finding.from_dict(data))
        return findings
    finally:
        conn.close()


def get_finding(finding_id: str) -> Finding | None:
    """Get a finding by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM findings WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["is_noise"] = bool(data["is_noise"])
        return Finding.from_dict(data)
    finally:
        conn.close()


def count_findings_for_run(run_id: str) -> int:
    """Count findings for a run."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM findings WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row["count"] if row else 0
    finally:
        conn.close()


# =============================================================================
# Eval operations
# =============================================================================


def create_eval(eval_score: EvalScore) -> EvalScore:
    """Insert a new eval record."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO evals (eval_id, finding_id, scored_at, score, code_owner_comment, sentiment, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_score.eval_id,
                eval_score.finding_id,
                eval_score.scored_at,
                eval_score.score,
                eval_score.code_owner_comment,
                eval_score.sentiment.value if eval_score.sentiment else None,
                eval_score.notes,
            ),
        )
        conn.commit()
        return eval_score
    finally:
        conn.close()


def get_evals_for_finding(finding_id: str) -> list[EvalScore]:
    """Get all evals for a finding."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM evals WHERE finding_id = ? ORDER BY scored_at DESC", (finding_id,)
        ).fetchall()
        return [EvalScore.from_dict(dict(row)) for row in rows]
    finally:
        conn.close()


def get_avg_score_for_run(run_id: str) -> float | None:
    """Get average eval score for all findings in a run."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT AVG(e.score) as avg_score
            FROM evals e
            JOIN findings f ON e.finding_id = f.finding_id
            WHERE f.run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return row["avg_score"] if row and row["avg_score"] else None
    finally:
        conn.close()
