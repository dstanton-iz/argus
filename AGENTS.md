# Argus

> The hundred-eyed exception analyst

## Purpose

This workspace supports production exception analysis using logs, samples, traces, metrics, and application source code. Use it to identify failure modes, propose fixes, and track impact over time.

## Structure

- `logs/{ERROR_CODE}/` - Weekly exception CSVs organized by error catalog code
- `samples/` - Request/response JSON files named by request ID
- `traces/` - Distributed traces as JSON, named by trace ID
- `metrics/` - Aggregated vitals and per-error-code trends
- `repos/` - Cloned application codebases
- `findings/` - Analysis notes and recommendations per error code
- `lessons/` - Reusable patterns extracted from analysis
- `incidents/` - Time-boxed folders for live incident investigations

## Data Safety

- Treat `samples/` and `traces/` as sensitive; avoid copying raw payloads into notes.
- Never print secrets or access tokens from `.env`; redact any credentials.
- If sharing snippets, strip PII and keep only what is needed for reasoning.

## Cross-Referencing

Log entries may contain:
- `request_id` - Check `samples/` for matching request/response payloads
- `trace_id` - Check `traces/` for the full distributed trace

## Analysis Workflow

1. Check `metrics/vitals.csv` for overall trends.
2. Pick an error code to investigate.
3. Review `metrics/{ERROR_CODE}/trend.csv` for trajectory.
4. Inspect the latest CSV in `logs/{ERROR_CODE}/`.
5. Identify top exceptions by count or week-over-week increase.
6. Locate the relevant operation in `repos/`.
7. If a `request_id` is available, check `samples/` for I/O context.
8. If a `trace_id` is available, check `traces/` to see the request path.
9. Analyze the code path and suggest:
   - Input validation or guard clauses
   - Better error handling
   - Tests that would catch this failure mode
10. Document findings in `findings/{ERROR_CODE}/{date}.md`.
11. After fixes ship, update `metrics/` to track impact.

## Prioritization

If multiple error codes are hot, prioritize:
1. Highest user impact or severity
2. Largest week-over-week increase
3. Highest absolute count

## Findings Format

Use a concise structure:
- Summary of failure mode
- Trigger conditions
- Suspected code path(s)
- Recommended fix(es)
- Test coverage gaps
- Impact tracking plan

## Key Questions To Answer

- What input conditions could cause this exception?
- Is there missing validation at the entry point?
- Should this operation handle this case explicitly rather than throwing?
- What test cases would prevent regression?
- Are our fixes actually reducing exception counts?

## When To Ask The User

- Missing logs, samples, traces, or repos needed to proceed
- Ambiguous error code selection or scope
- Unclear expectations for output depth or format
