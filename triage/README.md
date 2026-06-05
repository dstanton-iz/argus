# Argus triage

SQLite + Python CLI for tracking triaged error codes across multiple environments.

## Why

Flat CSV triage files outgrow themselves when you want to:

- Track the same error code across multiple environments (was it in qa first? when did prod start seeing it?)
- See the status history of an entry (how long has this been at `Assess`?)
- Group by supplier, classification family, or component
- Generate multiple projections (rich report vs. skinny lookup) from one source

This is a small, dependency-free local store designed for that.

## Setup

```sh
chmod +x cli.py
ln -s "$(pwd)/cli.py" /usr/local/bin/triage   # optional
```

Python 3 stdlib only — no `pip install`.

The database file (`triage.db`) is created on first invocation and is gitignored.

## Commands

### add

```sh
triage add --code E1234567 --component <comp> --operation <op> --env <env> \
           --classification-code IS0030 --supplier <supplier> \
           --responsibility-type INTERNAL --category SOFTWARE \
           --status 'Assess' --notes '...'
```

### update

Find a row by positional `<id-or-key>` (integer id or composite `CODE|COMP|OP|ENV`), or by the long flags (`--id` / `--code --component --operation --env`), then set any editable fields.

```sh
triage update 42 --status 'Known Error' --notes '...'
triage update 'E1234567|service-x|opXyz|qa' --status 'Known Error'
```

### Shortcuts for common typing

- Date fields accept `today` / `now` as shorthand: `--seen today`, `--reviewed today`
- Short aliases for the most-typed flags:
  - `--sup` → `--supplier`
  - `--class` → `--classification-code`
  - `--resp` → `--responsibility-type`
  - `--cat` → `--category`
  - `--fix` → `--suggested-fix`
  - `--pr` → `--related-pr`
  - `--af` → `--related-argus-finding`
  - `--seen` → `--last-seen`
  - `--reviewed` → `--last-reviewed`

Typical triage closing call:
```sh
triage update 'E0001234|service-x|opXyz|production' \
  --status 'Known Error' --sup vendor-name --class IS0030 \
  --resp INTERNAL --cat SOFTWARE --seen today --reviewed today
```

### list

```sh
triage list --env <env>
triage list --status 'Known Error'
triage list --supplier <supplier>
```

### show

Full record + status history:

```sh
triage show --id 42
```

### history

Just the status change log:

```sh
triage history --id 42
```

### search

Substring search of `notes` and `suggested_fix`:

```sh
triage search 'PCC'
```

### compare

Same error code across all environments in the DB:

```sh
triage compare --code E1234567 --component <comp> --operation <op>
```

## Schema

See [schema.sql](schema.sql). Two tables:

- `codes` — one row per `(error_code, component_id, operation_id, environment)`
- `status_history` — append-only log; populated by triggers on every status change

## Allowed statuses

`Assess`, `Known Error`, `Pending Change`, `Awaiting Release`, `Registered`, `Fix Recommended`, `Resolved`

## Allowed responsibility types

`INTERNAL`, `EXTERNAL`, `CLIENT`, `UNKNOWN`
