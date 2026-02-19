# Argus v2 Specification

> The hundred-eyed exception analyst — v2 application spec

## Overview

Argus v2 promotes the existing Claude Code skill (a flat-file manual workflow) into a proper Python CLI application. The goal is a local-first tool for AI-assisted exception analysis that can eventually run as a stage in a CD pipeline.

Core design principles:

- **Local-first**: runs on a developer's machine with no cloud infrastructure required
- **Model-agnostic**: uses Simon Willison's `llm` library so any supported model works — Claude, GPT-4o, Gemini, local Ollama models — controlled by a single env var
- **Pipeline-ready**: every CLI command accepts arguments directly (not just interactively) and returns meaningful exit codes so the tool can eventually drop into a CD pipeline stage
- **Disk for data, SQLite for metadata**: raw log CSVs and finding markdown files live on disk; only run metadata and eval scores go in SQLite
- **Lessons are institutional memory**: the `lessons/` directory is never gitignored and accumulates reusable patterns over time

---

## Tech Stack

| Dependency | Purpose |
|------------|---------|
| Python 3.12+ | Runtime |
| `click` | CLI commands and options |
| `rich` | Terminal output — tables, panels, progress, color-coded severity |
| `httpx` | Async HTTP calls to Sumo Logic and Watchtower APIs |
| `llm` | All model interactions — the only AI dependency |
| `sqlite3` | Run metadata and eval tracking (stdlib, no ORM) |
| `pytest` | Tests |
| `ruff` | Linting and formatting |

**Do not** use the Anthropic SDK, OpenAI SDK, or any provider-specific AI library directly. All model calls go through `llm`. Do not introduce a web framework, task queue, or any cloud infrastructure.

---

## Model Configuration

Argus is model-agnostic. The active model is set via `ARGUS_MODEL` in `.env`. Default is `claude-sonnet-4-6`.

Users install provider support via `llm` plugins:

```bash
# Anthropic (Claude) — default
llm install llm-anthropic
llm keys set anthropic

# OpenAI — built into llm, no plugin needed
llm keys set openai

# Google Gemini
llm install llm-gemini
llm keys set gemini

# Local models via Ollama
llm install llm-ollama
# No key needed
```

Note: API keys for LLM providers are managed by the `llm` tool via `llm keys set <provider>`, not via `.env`. Document this clearly in the README.

All model calls in the codebase follow this pattern — never import a provider SDK directly:

```python
import llm

model = llm.get_model(settings.argus_model)
response = model.prompt(prompt, system=system_prompt)
result = response.text()
```

Never hardcode a model name anywhere except the default value in `config.py`.

---

## Project Structure

```
argus/
├── argus/
│   ├── __init__.py
│   ├── cli.py              # click entry point, all commands
│   ├── config.py           # env var loading and validation
│   ├── db.py               # SQLite schema and queries
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── sumo.py         # Sumo Logic API client
│   │   └── watchtower.py   # Watchtower/Grafana LGTM API client
│   ├── analysis.py         # llm calls and prompt construction
│   ├── output.py           # rich-based terminal rendering
│   └── models.py           # dataclasses: Run, Finding, EvalScore
├── runs/                   # gitignored — one subdir per run_id
├── lessons/                # persistent reusable patterns — NOT gitignored
├── tests/
│   ├── test_db.py
│   ├── test_sources.py
│   ├── test_analysis.py
│   └── test_models.py
├── .env.example
├── CLAUDE.md
├── README.md
├── SPEC.md                 # this file
├── pyproject.toml
└── Makefile
```

---

## Database Schema

Database location: `~/.argus/argus.db` — not in the repo directory.

### `runs` table

One row per analysis run.

| Column | Type | Notes |
|--------|------|-------|
| `run_id` | TEXT | Primary key, UUID |
| `created_at` | TEXT | ISO 8601 |
| `environment` | TEXT | `staging`, `qa`, `prod` |
| `source` | TEXT | `sumo` or `watchtower` |
| `model` | TEXT | The `llm` model string used, e.g. `claude-sonnet-4-6` |
| `query_params` | TEXT | JSON blob — error code, operation id, time range, etc. |
| `status` | TEXT | `pending`, `complete`, `failed` |
| `run_dir` | TEXT | Absolute path to the run's files on disk |

### `findings` table

One row per exception/error pattern identified in a run.

| Column | Type | Notes |
|--------|------|-------|
| `finding_id` | TEXT | Primary key, UUID |
| `run_id` | TEXT | Foreign key → runs |
| `error_code` | TEXT | |
| `operation_id` | TEXT | Nullable |
| `summary` | TEXT | One-line description |
| `analysis` | TEXT | Full AI analysis text |
| `pr_url` | TEXT | Nullable |
| `pr_status` | TEXT | Nullable: `draft`, `open`, `merged`, `closed` |

### `evals` table

Outcome scoring for a finding. This is the core eval feedback loop.

| Column | Type | Notes |
|--------|------|-------|
| `eval_id` | TEXT | Primary key, UUID |
| `finding_id` | TEXT | Foreign key → findings |
| `scored_at` | TEXT | ISO 8601 |
| `score` | INTEGER | 1–5, see scoring rubric below |
| `code_owner_comment` | TEXT | Nullable — raw comment text |
| `sentiment` | TEXT | Nullable: `positive`, `neutral`, `negative` — auto-classified via llm |
| `notes` | TEXT | Nullable — scorer's own notes |

The `model` field in `runs` enables future cross-model eval comparison: you can re-run `argus analyze` on the same data with a different model and compare average scores over time.

---

## Eval Scoring Rubric

| Score | Meaning |
|-------|---------|
| 5 | PR accepted as-is — highly effective |
| 4 | Right solution, minor placement adjustment, used without meaningful changes |
| 3 | Right solution, wrong abstraction or location, required rework but the core idea was used |
| 2 | Wrong solution, distracted the team, some time lost |
| 1 | Completely wrong, significant engineering time wasted |

The primary feedback signal is a code owner comment on the draft PR. Comments are auto-classified for sentiment via `llm` to assist scoring. Merge status alone is insufficient — a PR can be merged with significant modifications or sit open for unrelated reasons.

---

## CLI Commands

Every command must work two ways:
1. **Interactive**: run with no arguments and prompt the user
2. **Direct**: accept all parameters as arguments for pipeline use

Exit codes must be meaningful:
- `0` — success
- `1` — analysis error (model failure, parse error)
- `2` — connectivity failure (can't reach Sumo Logic or Watchtower)

### `argus run`

Interactive or direct run setup. Collects:
- Source: `sumo` or `watchtower`
- Environment: `staging`, `qa`, `prod`
- Error code (optional)
- Operation ID (optional)
- Time range (default: last 24h)

Builds the appropriate query, pulls log data, writes CSVs to `runs/{run_id}/logs/`, then immediately kicks off analysis via `argus analyze`.

### `argus analyze <run_id>`

Re-run analysis on an existing run's data without re-fetching. Useful for iterating on prompts or comparing model outputs. Updates the `model` field in the run record to reflect which model was used.

### `argus score <run_id>`

Interactive scoring workflow. Lists findings for the run, then for each finding prompts for:
- PR URL
- Score (1–5)
- Code owner comment (paste the raw comment text)
- Notes

Auto-classifies comment sentiment via `llm`. Saves results to the `evals` table.

### `argus runs`

Lists recent runs as a `rich` table with columns: run_id (truncated), created_at, environment, source, model, status, finding count, avg eval score if any evals exist.

### `argus findings <run_id>`

Shows all findings for a run as rich panels with color-coded severity (P0=red, P1=orange, P2=yellow, P3=default).

### `argus lessons`

Lists files in `lessons/`. Allows promoting a finding to a lesson (copies the finding markdown into `lessons/` with a user-provided name).

### `argus status`

Connectivity and configuration check. Hits health endpoints for each Watchtower service and the Sumo Logic API. Also resolves `ARGUS_MODEL` via `llm` and reports whether the model is available. Renders a rich status table with service name, URL, status (✓ green / ✗ red), and latency in ms.

---

## Data Sources

### Sumo Logic (`sources/sumo.py`)

Credentials from env: `SUMO_ACCESS_ID`, `SUMO_ACCESS_KEY`, `SUMO_BASE_URL`

Implement the Sumo Logic search job workflow:
1. `POST /api/v1/search/jobs` to create the job
2. Poll `GET /api/v1/search/jobs/{id}` until status is `DONE GATHERING RESULTS`
3. Fetch records via `GET /api/v1/search/jobs/{id}/records`
4. Return as list of dicts
5. Write CSV to `runs/{run_id}/logs/{error_code}_{timestamp}.csv`

Include a `build_query(environment, error_code, operation_id, time_range)` function that constructs a valid Sumo Logic query string from parameters.

### Watchtower (`sources/watchtower.py`)

Base URL from env: `WATCHTOWER_URL` (default `http://localhost:3000`)

Implement clients for:

| Signal | Endpoint |
|--------|---------|
| Loki logs | `GET {WATCHTOWER_URL}/loki/api/v1/query_range` |
| Tempo traces | `GET {WATCHTOWER_URL}:3200/api/search` |
| Prometheus metrics | `GET {WATCHTOWER_URL}:9090/api/v1/query` |
| SonarQube issues | `GET {SONARQUBE_URL}/api/issues/search` |

Each client returns a normalized list of dicts. SonarQube credentials from env: `SONARQUBE_URL`, `SONARQUBE_TOKEN`.

---

## Analysis Pipeline (`analysis.py`)

The `analyze_run(run_id)` function:

1. Load CSVs from `runs/{run_id}/logs/`
2. Load all files from `lessons/` as reusable context
3. Check `runs/{run_id}/code/` for cloned repo context (optional — skip gracefully if absent)
4. If Watchtower source: also pull SonarQube issues for any files referenced in the exceptions
5. Construct prompt (see below)
6. Call `llm.get_model(settings.argus_model)` — never call a provider SDK directly
7. Parse response into one or more `Finding` dataclass instances
8. Save findings to the `findings` table
9. Write each finding as a markdown file to `runs/{run_id}/findings/`
10. Render output to terminal via `output.py`

### Prompt Instructions

Instruct the model to analyze the provided exception data and return structured findings. Each finding should include:

- Most likely root cause
- Specific fix suggestion with file and line context (if code context is available)
- Whether the exception is in a file already flagged by SonarQube (if SonarQube data is available)
- Severity estimate: P0 (production down), P1 (major feature broken), P2 (degraded), P3 (minor/cosmetic)
- Whether this looks like background job / cache loader / reservation updater noise (flag as likely noise if so)
- Reference to any matching lesson from `lessons/` if relevant

---

## Terminal Output (`output.py`)

Use `rich` throughout. Never use plain `print()` for user-facing output.

Key rendering components:

- **Run summary panel**: environment, source, model, time range, finding count
- **Findings table**: severity (color-coded), error code, operation id, one-line summary
- **Finding detail panel**: full analysis text in a bordered panel
- **Eval score**: 1–5 rendered as filled/empty stars with color (5=green, 3=yellow, 1=red)
- **Status table**: service name, URL, ✓/✗ status colored green/red, latency in ms. Include a row for the configured `ARGUS_MODEL` showing whether `llm` can resolve it.
- **Progress indicators**: use `rich.progress` when polling Sumo Logic jobs or fetching large datasets

---

## Environment Variables

Document all of these in `.env.example`:

```bash
# Model — any model string supported by the llm library
# API keys are managed separately via: llm keys set <provider>
ARGUS_MODEL=claude-sonnet-4-6

# Sumo Logic
SUMO_ACCESS_ID=
SUMO_ACCESS_KEY=
SUMO_BASE_URL=https://api.sumologic.com

# Watchtower (local LGTM stack)
WATCHTOWER_URL=http://localhost:3000

# SonarQube (part of Watchtower stack)
SONARQUBE_URL=http://localhost:9000
SONARQUBE_TOKEN=

# GitHub — optional, for future PR status lookups
GITHUB_TOKEN=
```

---

## Tests

All tests use `pytest` with `unittest.mock`. No live API calls and no live model calls anywhere in the test suite. Mock at the `llm.get_model` boundary for all analysis tests.

### `test_db.py`
- Create a run record and read it back
- Insert a finding with foreign key to run
- Insert an eval with foreign key to finding
- Query findings by run_id
- Assert `model` field is stored and retrieved correctly
- Assert score validation (1–5 range)

### `test_sources.py`
- Mock `httpx` responses for Sumo Logic search job workflow (create, poll, fetch)
- Mock `httpx` responses for each Watchtower endpoint (Loki, Tempo, Prometheus, SonarQube)
- Assert each client returns normalized list of dicts with expected keys
- Assert `build_query()` constructs correct Sumo Logic query strings for various param combinations

### `test_analysis.py`
- Mock `llm.get_model()` to return a fake model with a controllable `.prompt()` response
- Assert prompt construction includes exception data, lessons context, and code context when present
- Assert SonarQube flags appear in prompt when data is available
- Assert a known response string is correctly parsed into `Finding` dataclass instances
- Assert findings are written to the correct `runs/{run_id}/findings/` path

### `test_models.py`
- Dataclass instantiation for `Run`, `Finding`, `EvalScore`
- Serialization to/from dict
- Score validation raises on values outside 1–5

---

## Makefile

```makefile
install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check argus/

format:
	ruff format argus/

run:
	argus run

status:
	argus status

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## pyproject.toml

Use `[project.scripts]` so `argus` is available as a CLI command after `pip install -e .`.

```toml
[project]
name = "argus"
version = "2.0.0"
requires-python = ">=3.12"
dependencies = [
    "click",
    "rich",
    "httpx",
    "llm",
]

[project.scripts]
argus = "argus.cli:cli"

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",
]
```

Do not add `llm-anthropic` or any provider plugin as a hard dependency — these are user-installed. The README should explain this clearly.

---

## README: Model Providers Section

Include this section in the README:

```markdown
## Model Providers

Argus uses [llm](https://github.com/simonw/llm) for all AI calls, making it compatible
with any supported model. Set `ARGUS_MODEL` in your `.env` to switch providers.

| Provider | Plugin | Setup |
|----------|--------|-------|
| Anthropic (default) | `llm install llm-anthropic` | `llm keys set anthropic` |
| OpenAI | built-in | `llm keys set openai` |
| Google Gemini | `llm install llm-gemini` | `llm keys set gemini` |
| Local (Ollama) | `llm install llm-ollama` | No key needed |

API keys are stored by `llm` separately from your `.env` file.
```

---

## Important Constraints

- **Raw data stays on disk**: CSVs and finding markdown files live under `runs/` — never store raw log data in SQLite
- **SQLite is metadata only**: run records, finding summaries, and eval scores only
- **Lessons are permanent**: `lessons/` is never gitignored — it is the institutional memory of the tool
- **Interactive and direct modes**: every command must work both ways for pipeline compatibility
- **Meaningful exit codes**: 0 success, 1 analysis error, 2 connectivity failure
- **No verbose flags**: use `rich` progress and panels to make default output informative — don't hide information behind a flag
- **No hardcoded model names**: only the default value in `config.py` may reference a specific model string
- **No provider SDK imports**: `llm` is the only AI import anywhere in the codebase
- **Background job noise**: the analysis prompt must explicitly ask the model to flag exceptions that look like background job / cache loader / reservation updater artifacts, as staging environments generate significant noise from these sources

---

## Future Work (Out of Scope for v2)

These are intentionally deferred:

- GitHub PR status webhook or polling (GITHUB_TOKEN is stubbed for this)
- CD pipeline integration (exit codes are designed for this but the pipeline config is out of scope)
- Multi-repo code context (v2 supports a single `runs/{run_id}/code/` directory)
- Cross-model eval comparison dashboard (the data model supports it via the `model` field, UI is deferred)
- Watchtower AWS deployment for QA environment integration (Watchtower handles this separately)
