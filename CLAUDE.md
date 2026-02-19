# Argus

> AI-powered exception analysis CLI

## What This Is

A CLI tool that queries Watchtower (local LGTM stack) for error data, runs AI analysis, and produces actionable findings. Designed for fast feedback loops during development.

## Architecture

```
argus/
├── cli.py           # Click commands (status, run, analyze, runs, findings, score, lessons)
├── config.py        # Settings from environment variables
├── models.py        # Run, Finding, EvalScore dataclasses
├── db.py            # SQLite for run metadata (~/.argus/argus.db)
├── output.py        # Rich terminal rendering
├── analysis.py      # LLM prompt construction and response parsing
└── sources/
    └── watchtower.py   # Async clients for Loki, Tempo, Prometheus, SonarQube
```

## Data Flow

1. `argus run` queries Loki (logs) and Tempo (traces) for errors
2. Data is saved to `runs/{run_id}/logs/` and `runs/{run_id}/traces/` as CSVs
3. `analysis.py` builds a prompt with logs + traces + lessons
4. LLM response is parsed into Finding objects and saved to SQLite + markdown
5. `argus findings {run_id}` displays results

## Key Commands

```bash
argus status              # Health check all services
argus run                 # New analysis run (interactive)
argus runs                # List recent runs
argus findings <run_id>   # Show findings
argus analyze <run_id>    # Re-run analysis on existing data
argus score <run_id>      # Rate findings 1-5 (eval workflow)
argus lessons             # List/promote institutional memory
```

## External Dependencies

- **Watchtower stack** - Loki:3100, Tempo:3200, Prometheus:9090, SonarQube:9000
- **llm library** - Model-agnostic AI calls (Simon Willison's library)
- **SQLite** - Run/finding/eval metadata at `~/.argus/argus.db`

## Testing

All tests use `pytest` with `unittest.mock`. No live API calls or model calls.

```bash
make test   # 89 tests
make lint   # ruff check
```

## Important Files

- `lessons/` - Markdown files included in analysis prompts (institutional memory)
- `runs/` - Gitignored, contains raw data per run
- `.env` - Watchtower URLs and model config (gitignored)

## Adding Features

When modifying analysis:
1. Update `SYSTEM_PROMPT` in `analysis.py` for LLM instructions
2. Update `build_analysis_prompt()` for input formatting
3. Update `parse_findings_response()` for output parsing
4. Add tests that mock `llm.get_model`

When adding CLI commands:
1. Add to `cli.py` with `@cli.command()` decorator
2. Use `print_info/success/error/warning` from output.py
3. Use async functions wrapped with `asyncio.run()` for API calls
