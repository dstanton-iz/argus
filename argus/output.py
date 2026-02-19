"""Rich-based terminal output for Argus."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import Finding, Run, Severity

console = Console()


# =============================================================================
# Color mappings
# =============================================================================

SEVERITY_COLORS = {
    Severity.P0: "red",
    Severity.P1: "orange1",
    Severity.P2: "yellow",
    Severity.P3: "white",
}

SCORE_COLORS = {
    5: "green",
    4: "green",
    3: "yellow",
    2: "orange1",
    1: "red",
}


def severity_color(severity: Severity | str) -> str:
    """Get color for a severity level."""
    if isinstance(severity, str):
        severity = Severity(severity)
    return SEVERITY_COLORS.get(severity, "white")


def score_color(score: int) -> str:
    """Get color for an eval score."""
    return SCORE_COLORS.get(score, "white")


# =============================================================================
# Rendering functions
# =============================================================================


def render_score(score: int) -> Text:
    """Render an eval score as filled/empty stars."""
    filled = "★" * score
    empty = "☆" * (5 - score)
    color = score_color(score)
    return Text(filled + empty, style=color)


def render_status_table(services: list[dict]) -> None:
    """
    Render a status table for service health checks.

    Args:
        services: List of dicts with keys: name, url, healthy, latency_ms
    """
    table = Table(title="Argus Status", show_header=True, header_style="bold")
    table.add_column("Service", style="cyan")
    table.add_column("URL")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")

    for svc in services:
        status = Text("✓", style="green") if svc["healthy"] else Text("✗", style="red")
        latency = f"{svc['latency_ms']:.0f}ms" if svc.get("latency_ms") else "-"
        table.add_row(svc["name"], svc["url"], status, latency)

    console.print(table)


def render_runs_table(runs: list[Run], finding_counts: dict[str, int], avg_scores: dict[str, float | None]) -> None:
    """
    Render a table of recent runs.

    Args:
        runs: List of Run objects
        finding_counts: Dict mapping run_id to finding count
        avg_scores: Dict mapping run_id to average eval score (or None)
    """
    table = Table(title="Recent Runs", show_header=True, header_style="bold")
    table.add_column("Run ID", style="cyan", max_width=12)
    table.add_column("Created")
    table.add_column("Env")
    table.add_column("Source")
    table.add_column("Model", max_width=20)
    table.add_column("Status")
    table.add_column("Findings", justify="right")
    table.add_column("Avg Score", justify="center")

    for run in runs:
        run_id_short = run.run_id[:8] + "..."
        status_color = "green" if run.status.value == "complete" else "yellow" if run.status.value == "pending" else "red"
        status = Text(run.status.value, style=status_color)
        finding_count = str(finding_counts.get(run.run_id, 0))

        avg_score = avg_scores.get(run.run_id)
        if avg_score is not None:
            score_text = render_score(round(avg_score))
        else:
            score_text = Text("-", style="dim")

        table.add_row(
            run_id_short,
            run.created_at[:19],  # Truncate to seconds
            run.environment or "-",
            run.source,
            run.model or "-",
            status,
            finding_count,
            score_text,
        )

    console.print(table)


def render_findings_table(findings: list[Finding]) -> None:
    """
    Render a table of findings for a run.

    Args:
        findings: List of Finding objects
    """
    if not findings:
        console.print("[dim]No findings for this run.[/dim]")
        return

    table = Table(title="Findings", show_header=True, header_style="bold")
    table.add_column("Severity", justify="center")
    table.add_column("Error Code", style="cyan")
    table.add_column("Operation ID")
    table.add_column("Summary", max_width=60)
    table.add_column("Noise", justify="center")

    for finding in findings:
        sev_color = severity_color(finding.severity)
        severity = Text(finding.severity.value, style=f"bold {sev_color}")
        noise = Text("🔇", style="dim") if finding.is_noise else Text("")

        table.add_row(
            severity,
            finding.error_code or "-",
            finding.operation_id or "-",
            finding.summary[:60] + "..." if len(finding.summary) > 60 else finding.summary,
            noise,
        )

    console.print(table)


def render_finding_detail(finding: Finding) -> None:
    """
    Render full details for a single finding.

    Args:
        finding: Finding object
    """
    sev_color = severity_color(finding.severity)

    # Header
    header = Text()
    header.append(f"[{finding.severity.value}] ", style=f"bold {sev_color}")
    header.append(finding.summary)

    # Content
    content = []

    if finding.error_code:
        content.append(f"[bold]Error Code:[/bold] {finding.error_code}")
    if finding.operation_id:
        content.append(f"[bold]Operation ID:[/bold] {finding.operation_id}")
    if finding.is_noise:
        content.append("[dim]⚠ Classified as background job noise[/dim]")
    if finding.matched_lesson:
        content.append(f"[bold]Matched Lesson:[/bold] {finding.matched_lesson}")

    content.append("")
    content.append("[bold]Root Cause:[/bold]")
    content.append(finding.root_cause or "[dim]Not determined[/dim]")

    content.append("")
    content.append("[bold]Fix Suggestion:[/bold]")
    content.append(finding.fix_suggestion or "[dim]No suggestion[/dim]")

    if finding.analysis:
        content.append("")
        content.append("[bold]Full Analysis:[/bold]")
        content.append(finding.analysis)

    if finding.pr_url:
        content.append("")
        content.append(f"[bold]PR:[/bold] {finding.pr_url} ({finding.pr_status or 'unknown'})")

    panel = Panel(
        "\n".join(content),
        title=header,
        border_style=sev_color,
        expand=False,
    )
    console.print(panel)


def render_run_summary(run: Run, finding_count: int) -> None:
    """
    Render a summary panel for a run.

    Args:
        run: Run object
        finding_count: Number of findings
    """
    content = []
    content.append(f"[bold]Run ID:[/bold] {run.run_id}")
    content.append(f"[bold]Created:[/bold] {run.created_at}")
    content.append(f"[bold]Environment:[/bold] {run.environment or 'not set'}")
    content.append(f"[bold]Source:[/bold] {run.source}")
    content.append(f"[bold]Model:[/bold] {run.model or 'not set'}")
    content.append(f"[bold]Status:[/bold] {run.status.value}")
    content.append(f"[bold]Findings:[/bold] {finding_count}")

    if run.query_params:
        content.append("")
        content.append("[bold]Query Parameters:[/bold]")
        for key, value in run.query_params.items():
            content.append(f"  {key}: {value}")

    panel = Panel(
        "\n".join(content),
        title="Run Summary",
        border_style="cyan",
        expand=False,
    )
    console.print(panel)


def render_lessons_list(lessons: list[str]) -> None:
    """
    Render a list of lesson files.

    Args:
        lessons: List of lesson file names
    """
    if not lessons:
        console.print("[dim]No lessons yet. Use 'argus lessons --promote' to add one.[/dim]")
        return

    table = Table(title="Lessons (Institutional Memory)", show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=4)
    table.add_column("Lesson File")

    for i, lesson in enumerate(lessons, 1):
        table.add_row(str(i), lesson)

    console.print(table)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[cyan]→[/cyan] {message}")
