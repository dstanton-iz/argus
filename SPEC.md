# Argus Spec

> The hundred-eyed exception analyst

## What This Is

Argus is a Claude Code skill - a folder structure and CLAUDE.md that teaches Claude Code how to analyze production exceptions. The data is local and ephemeral. The value is the workflow and the lessons that accumulate over time.

## Directory Structure

```
argus/
├── CLAUDE.md
├── .env.example
├── .env
├── .gitignore
├── scripts/
│   └── ...
├── logs/
│   └── {ERROR_CODE}/
│       ├── {YYYY-MM-DD}.csv
│       └── diff_{YYYY-MM-DD}.csv
├── samples/
│   ├── req_{REQUEST_ID}_request.json
│   └── req_{REQUEST_ID}_response.json
├── traces/
│   ├── trace_{TRACE_ID}.json
│   └── ...
├── metrics/
│   ├── vitals.csv
│   └── {ERROR_CODE}/
│       └── trend.csv
├── repos/
│   └── {service-name}/
├── findings/
│   └── {ERROR_CODE}/
│       └── {YYYY-MM-DD}.md
├── lessons/
│   ├── index.md
│   └── {LESSON_SLUG}.md
└── incidents/
    └── {YYYY-MM-DD}_{INCIDENT_SLUG}/
        ├── summary.md
        ├── timeline.md
        ├── logs/
        ├── traces/
        └── metrics/
```

### .gitignore

```gitignore
.env
logs/
samples/
traces/
metrics/
repos/
findings/
lessons/
incidents/
scripts/
```

Only track: `CLAUDE.md`, `.env.example`, `.gitignore`

This keeps Argus as a clean, forkable template with zero risk of leaking sensitive data. Export findings and lessons to your company's knowledge system (Confluence, Notion, internal wiki, etc.) as part of your workflow.

**Force-adding exceptions:** Use `git add -f path/to/file` to selectively commit safe, generalized content even from gitignored folders:

- `scripts/` - Generic utilities like `diff_weeks.py` or `new_incident.sh`
- `lessons/` - Generalized patterns applicable to anyone (e.g., retry amplification, timeout cascades)
- `incidents/` - Public postmortems from platforms you depend on (Cloudflare, Vercel, AWS, Stripe, etc.)

Public postmortems are especially valuable - they become part of the template. When troubleshooting, Claude Code can cross-reference against known platform incidents to see if your symptoms match an upstream issue.

### scripts/

Convenience scripts for your specific environment. Gitignored because they'll contain org-specific details (endpoints, paths, export targets). Examples of what you might put here:

- `pull_logs.py` - Fetch logs from your observability platform for a date range
- `pull_traces.py` - Grab traces by trace ID or time window
- `diff_weeks.py` - Generate week-over-week comparison CSVs
- `export_to_confluence.py` - Push lessons/findings to your wiki
- `new_incident.sh` - Scaffold an incident folder with today's date

## Operating Modes

### Weekly Review Mode

Deep analysis of exception trends, meant to run over hours/days. Claude Code works through the backlog, correlates with code, and builds up institutional knowledge.

**Workflow:**
1. Export latest logs/metrics for the week
2. Run diffs against previous week
3. Claude Code analyzes top exceptions, traces code paths, suggests fixes
4. Document findings in `findings/`
5. Extract reusable patterns into `lessons/`
6. Export findings/lessons to company knowledge system (Confluence, Notion, etc.)

**Output:** Findings per error code, lessons learned, suggested PRs

### Incident Mode

Fast, focused analysis during a live incident. Give Claude Code a time window and it pulls everything relevant, cross-references against lessons learned, and helps you triage.

**Workflow:**
1. Create incident folder: `incidents/2025-01-13_payment-failures/`
2. Tell Claude Code: "Incident mode. Time window: 14:30-15:00 UTC. Symptoms: payment failures spiking."
3. Claude Code pulls logs, traces, metrics for that window into the incident folder
4. Cross-references against `lessons/` for known patterns
5. Produces `summary.md` and `timeline.md`

**Output:** Incident-specific folder with all evidence, timeline, and preliminary RCA

### .env.example

These credentials are for Claude Code to use when running in the project root. Claude Code can use these tokens (via MCP servers or direct API calls) to pull logs, traces, and metrics from your observability platforms.

```bash
# ===========================================
# Argus - Observability Platform Credentials
# ===========================================
# Copy this file to .env and fill in your values.
# Only configure the platform(s) you're using.
# These are for Claude Code to access your observability data.

# -------------------------------------------
# Grafana (Local / Self-Hosted)
# -------------------------------------------
GRAFANA_LOCAL_URL=http://localhost:3000
GRAFANA_LOCAL_API_KEY=

# -------------------------------------------
# Grafana Cloud
# -------------------------------------------
GRAFANA_CLOUD_URL=https://your-instance.grafana.net
GRAFANA_CLOUD_API_KEY=
# Loki endpoint for log queries
GRAFANA_CLOUD_LOKI_URL=https://logs-prod-us-central1.grafana.net
# Tempo endpoint for trace queries
GRAFANA_CLOUD_TEMPO_URL=https://tempo-prod-us-central1.grafana.net

# -------------------------------------------
# Sumo Logic
# -------------------------------------------
SUMO_LOGIC_ACCESS_ID=
SUMO_LOGIC_ACCESS_KEY=
SUMO_LOGIC_ENDPOINT=https://api.us2.sumologic.com/api

# -------------------------------------------
# Datadog
# -------------------------------------------
DATADOG_API_KEY=
DATADOG_APP_KEY=
DATADOG_SITE=datadoghq.com
```

### logs/

Organized by error catalog code (e.g., `E001` for uncaught exceptions, `E007` for another type). Each subfolder contains:
- Weekly CSV exports from observability platform
- Optional diff CSVs comparing week-over-week

CSV columns should include at minimum:
- `timestamp`
- `operation_name`
- `exception_type`
- `message`
- `request_id` (when available, for cross-referencing samples)
- `count` (if aggregated)

### samples/

Flat folder of request/response payloads, named by request ID:
- `req_{REQUEST_ID}_request.json`
- `req_{REQUEST_ID}_response.json`

These accumulate over time as you grab interesting examples. Request IDs may appear in log CSVs, allowing correlation between the exception and the actual I/O.

### traces/

Distributed traces exported as JSON, named by trace ID:
- `trace_{TRACE_ID}.json`

Log entries and samples often include a `trace_id` field. When investigating an exception, grab the full trace to see the request's path across services, timing, and where it failed. Traces complete the observability triad alongside logs and metrics.

### metrics/

Aggregated vitals and trends for tracking progress over time.

**vitals.csv** - Top-level health metrics:
```csv
date,total_exceptions,unique_operations,top_error_code,top_error_count,week_over_week_delta
2025-01-06,1423,87,E001,892,+12%
2025-01-13,1156,72,E001,634,-29%
```

**{ERROR_CODE}/trend.csv** - Per-error-code trends:
```csv
date,count,unique_operations,top_operation,top_operation_count,fixes_shipped
2025-01-06,892,34,PaymentService.processRefund,156,0
2025-01-13,634,28,PaymentService.processRefund,89,2
```

Use these to track whether fixes are actually reducing exception rates.

### repos/

Git clones of application codebases. Clone as needed:
```bash
cd repos/
git clone git@github.com:yourorg/booking-service.git
```

### findings/

Analysis output organized by error code. Each markdown file captures:
- Which exceptions were analyzed
- Root cause hypotheses
- Suggested code changes
- Tests to add
- Follow-up actions

### lessons/

Reusable patterns and institutional knowledge extracted from weekly reviews. These accumulate over time and are referenced during incident mode.

**index.md** - Quick reference of all lessons:
```markdown
# Lessons Index

- [null-user-context](null-user-context.md) - Missing user context causes NPEs in auth middleware
- [timeout-cascade](timeout-cascade.md) - Payment gateway timeouts cascade to inventory service
- [retry-amplification](retry-amplification.md) - Aggressive retries during partial outages
```

**{LESSON_SLUG}.md** - Individual lesson:
```markdown
# Null User Context

## Pattern
NullPointerException in auth middleware when session expires mid-request.

## Symptoms
- E001 spike in `AuthMiddleware.validateSession`
- Correlates with deployment of session timeout changes

## Root Cause
Session lookup returns null, not checked before accessing `.userId`

## Fix
Guard clause added in PR #1234

## Detection
Look for: `exception_type=NullPointerException` AND `operation_name=*Auth*`
```

### incidents/

Time-boxed folders for live incident investigations. Each incident gets its own folder with pulled data and analysis.

Structure per incident:
- `summary.md` - What happened, impact, resolution
- `timeline.md` - Minute-by-minute events
- `logs/` - Relevant log snippets for the time window
- `traces/` - Key traces showing the failure path
- `metrics/` - Graphs/data for the incident period

**Public postmortems:** Force-add postmortems from platforms you depend on (Cloudflare, AWS, Vercel, Stripe, etc.). These help Claude Code recognize when your symptoms might match an upstream issue. Structure them the same way:

```
incidents/
├── 2024-11-07_cloudflare-ai-gateway/
│   └── summary.md  # from their public postmortem
├── 2024-09-30_aws-us-east-1/
│   └── summary.md
└── 2025-01-13_payment-failures/  # your internal incident (gitignored)
    ├── summary.md
    ├── timeline.md
    └── ...
```

## CLAUDE.md Content

Create this file in the root of the workspace:

```markdown
# Argus

> The hundred-eyed exception analyst

## What This Is

A workspace for analyzing production exceptions using log data, request/response samples, and application source code. Track trends over time to measure improvement.

## Structure

- `logs/{ERROR_CODE}/` - Weekly exception CSVs organized by error catalog code
- `samples/` - Request/response JSON files named by request ID
- `traces/` - Distributed traces as JSON, named by trace ID
- `metrics/` - Aggregated vitals and per-error-code trends
- `repos/` - Cloned application codebases
- `findings/` - Analysis notes and recommendations per error code
- `lessons/` - Reusable patterns extracted from analysis (check these during incidents!)
- `incidents/` - Time-boxed folders for live incident investigations

## Credentials

The `.env` file contains credentials for observability platforms. Use these to query logs, traces, and metrics directly via API or MCP servers.

## Cross-Referencing

Log entries may contain:
- `request_id` - Check `samples/` for matching request/response payloads
- `trace_id` - Check `traces/` for the full distributed trace

## Analysis Workflow

1. Check `metrics/vitals.csv` for overall trends - are things getting better or worse?
2. Pick an error code to investigate (e.g., E001 for uncaught exceptions)
3. Look at `metrics/{ERROR_CODE}/trend.csv` to see trajectory
4. Look at the latest CSV in `logs/{ERROR_CODE}/`
5. Identify top exceptions by count or week-over-week increase
6. Find the relevant operation in `repos/`
7. If a request_id is available, check `samples/` for I/O context
8. If a trace_id is available, check `traces/` to see the full request path
9. Analyze the code path and suggest:
   - Input validation or guard clauses
   - Better error handling
   - Tests that would catch this failure mode
10. Document findings in `findings/{ERROR_CODE}/{date}.md`
11. After fixes ship, update `metrics/` to track impact

## Key Questions To Answer

- What input conditions could cause this exception?
- Is there missing validation at the entry point?
- Should this operation handle this case explicitly rather than throwing?
- What test cases would prevent regression?
- Are our fixes actually reducing exception counts?
```

## Bootstrap Commands

```bash
mkdir -p argus/{logs,samples,traces,metrics,repos,findings,lessons,incidents,scripts}
cd argus
cp .env.example .env  # then edit with your credentials
touch metrics/vitals.csv
touch lessons/index.md
# Clone repos as needed:
# cd repos && git clone ...
```

## Usage

From the `argus/` directory, invoke Claude Code in either mode.

### Weekly Review Prompts

- "Check metrics/vitals.csv - how are we trending overall? Then look at logs/E001/2025-01-13.csv and find the top 5 exceptions by count."
- "Compare logs/E001/diff_2025-01-13.csv - what's new or spiking since last week? Check if any request IDs have samples we can look at."
- "For the NullPointerException in PaymentService.processRefund, check samples/ for any matching request IDs and hypothesize what input caused it."
- "We shipped fixes last week for E001. Compare the trend.csv before and after - did it help?"
- "This pattern keeps showing up. Create a lesson in lessons/ so we remember it."

### Incident Mode Prompts

- "Incident mode. Time window: 2025-01-13 14:30-15:00 UTC. Symptoms: payment failures spiking. Create an incident folder and pull relevant data."
- "Check lessons/ - have we seen this pattern before?"
- "Build a timeline of what happened based on the logs and traces you pulled."
- "Write up a summary.md for this incident."
