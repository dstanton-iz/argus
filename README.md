# Argus

> AI-powered exception analysis for engineering teams

Argus analyzes your error logs and traces, identifies root causes, and suggests fixes. It queries your local [Watchtower](https://github.com/gotoplanb/watchtower) observability stack and uses AI to turn noisy exception data into actionable findings.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/gotoplanb/argus.git
cd argus
cp .env.example .env

# Create virtual environment and install
make venv

# Check connectivity to Watchtower
make status
```

## Requirements

- Python 3.12+
- [Watchtower](https://github.com/gotoplanb/watchtower) running locally (Loki, Tempo, Prometheus, SonarQube)
- An LLM configured via [llm](https://llm.datasette.io/) (e.g., `llm install llm-claude-3`)

## Usage

### Check Status

```bash
argus status
```

Shows health of all connected services (Loki, Tempo, Prometheus, SonarQube, LLM).

### Start an Analysis Run

```bash
argus run
```

Interactive prompts guide you through:
- Environment (staging/qa/prod)
- Service filter (optional)
- Error code filter (optional)
- Time window (default: 1 hour)

Argus fetches error logs from Loki and error traces from Tempo, then runs AI analysis to produce findings.

### View Runs and Findings

```bash
# List recent runs
argus runs

# Show findings for a run (use first 8 chars of run ID)
argus findings abc12345

# Show full details
argus findings abc12345 --detail
```

### Prompt-Only Mode (Free with Claude Code Max)

```bash
# Fetch data and copy the prompt to clipboard instead of calling the LLM API
argus run -e staging --prompt-only | pbcopy

# Or generate the prompt from an existing run
argus analyze abc12345 --prompt-only | pbcopy
```

Paste the output into a Claude Code session to get the same analysis quality at no additional API cost. This is ideal for supervised, local development. Reserve direct LLM calls for unsupervised runs (e.g., scheduled in AWS).

### Re-analyze Existing Data

```bash
argus analyze abc12345
```

Re-runs AI analysis on data already collected, useful when testing different models.

### Score Findings (Eval Workflow)

```bash
argus score abc12345
```

Walk through each finding and rate it 1-5. Scores track model quality over time.

### Manage Lessons

```bash
# List lessons (institutional memory)
argus lessons

# Promote a finding to a reusable lesson
argus lessons --promote abc12345
```

Lessons are markdown files in `lessons/` that get included in future analysis prompts, helping the AI recognize patterns your team has seen before.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# AI Model (any model supported by llm library)
ARGUS_MODEL=claude-sonnet-4-6

# Watchtower endpoints
WATCHTOWER_LOKI_URL=http://localhost:3100
WATCHTOWER_TEMPO_URL=http://localhost:3200
WATCHTOWER_PROMETHEUS_URL=http://localhost:9090

# SonarQube (optional)
SONARQUBE_URL=http://localhost:9000
SONARQUBE_TOKEN=your-token-here
```

## Development

```bash
make venv      # Create virtualenv and install dependencies
make test      # Run test suite (95 tests)
make lint      # Run ruff linter
make format    # Auto-format code
make clean     # Remove build artifacts
```

## Project Structure

```
argus/
├── cli.py           # Click CLI commands
├── config.py        # Settings from environment
├── models.py        # Run, Finding, EvalScore dataclasses
├── db.py            # SQLite metadata storage
├── output.py        # Rich terminal rendering
├── analysis.py      # LLM prompt construction and parsing
└── sources/
    └── watchtower.py   # Loki, Tempo, Prometheus, SonarQube clients

lessons/             # Institutional memory (committed to git)
runs/                # Analysis run data (gitignored)
```

## How It Works

1. **Fetch** - Query Loki for error logs and Tempo for error traces in your time window
2. **Enrich** - Optionally pull SonarQube issues for static analysis context
3. **Analyze** - Send data + lessons to LLM with structured prompt
4. **Store** - Parse findings into SQLite, save markdown to run directory
5. **Learn** - Promote good findings to lessons for future runs

## License

MIT
