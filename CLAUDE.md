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
