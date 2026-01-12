# Argus

> The hundred-eyed exception analyst

A Claude Code skill for analyzing production exceptions. Bring your logs, traces, and code — Argus provides the workflow and accumulates lessons over time.

## How It Works

**Weekly Review Mode** — Deep analysis of exception trends. Claude Code correlates logs with code, suggests fixes, and documents patterns in `lessons/` for future reference.

**Incident Mode** — Fast triage during outages. Pull logs for a time window, cross-reference against known patterns, and build a timeline.

## Quick Start

```bash
cp .env.example .env              # Add your observability credentials
cd repos && git clone <your-app>  # Clone codebases to analyze
```

Then ask Claude Code:
- "Check metrics/vitals.csv — how are we trending?"
- "Incident mode. Time window: 14:30-15:00 UTC. Symptoms: payment failures."

## What Gets Tracked

| Folder | Purpose |
|--------|---------|
| `logs/` | Exception CSVs by error code |
| `samples/` | Request/response payloads |
| `traces/` | Distributed traces |
| `metrics/` | Trends over time |
| `findings/` | Analysis per error code |
| `lessons/` | Reusable patterns |
| `incidents/` | Time-boxed investigations |

Everything except `CLAUDE.md`, `.env.example`, and `.gitignore` is gitignored. Export findings to your wiki; keep the template clean.

## License

MIT
