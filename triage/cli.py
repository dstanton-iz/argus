#!/usr/bin/env python3
"""Argus triage CLI — manage triaged error codes per environment."""

import argparse
import csv
import datetime
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import connect  # noqa: E402

ALLOWED_STATUSES = [
    "Assess",
    "Known Error",
    "Pending Change",
    "Awaiting Release",
    "Registered",
    "Fix Recommended",
    "Resolved",
]

ALLOWED_RESPONSIBILITY = ["INTERNAL", "EXTERNAL", "CLIENT", "UNKNOWN"]

EDITABLE_FIELDS = [
    "classification_code",
    "responsibility_type",
    "category",
    "supplier",
    "status",
    "notes",
    "suggested_fix",
    "related_pr",
    "related_argus_finding",
    "first_seen",
    "last_seen",
    "last_reviewed",
]


def _normalize_date(s):
    """Translate 'today'/'now' to ISO date; pass everything else through."""
    if s is None:
        return None
    if s.lower() in ("today", "now"):
        return datetime.date.today().isoformat()
    return s


def _resolve_target(args):
    """If a positional `target` was given, parse it as either an integer id or a
    composite key (CODE|COMP|OP|ENV) and stuff the parts back into args."""
    target = getattr(args, "target", None)
    if not target:
        return
    if target.isdigit():
        args.id = int(target)
        return
    if "|" in target:
        parts = target.split("|")
        if len(parts) != 4:
            sys.exit(f"Composite key must be CODE|COMP|OP|ENV (4 parts, got {len(parts)}: {target!r})")
        args.code, args.component, args.operation, args.env = parts
        return
    sys.exit(f"Target {target!r} not recognized — use a numeric id or CODE|COMP|OP|ENV")


def _find_one(conn, args):
    _resolve_target(args)
    if args.id:
        row = conn.execute("SELECT * FROM codes WHERE id = ?", (args.id,)).fetchone()
        if not row:
            sys.exit(f"No code with id={args.id}")
        return row
    if not (args.code and args.component and args.operation and args.env):
        sys.exit("Specify <id-or-key> positional, --id, or all of --code/--component/--operation/--env")
    row = conn.execute(
        "SELECT * FROM codes WHERE error_code=? AND component_id=? AND operation_id=? AND environment=?",
        (args.code, args.component, args.operation, args.env),
    ).fetchone()
    if not row:
        sys.exit("No code matches those filters")
    return row


def cmd_add(args):
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO codes
               (error_code, component_id, operation_id, environment,
                classification_code, responsibility_type, category, supplier,
                status, notes, suggested_fix, related_pr, related_argus_finding,
                first_seen, last_seen, last_reviewed)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                args.code, args.component, args.operation, args.env,
                args.classification_code, args.responsibility_type, args.category, args.supplier,
                args.status, args.notes, args.suggested_fix, args.related_pr, args.related_argus_finding,
                _normalize_date(args.first_seen), _normalize_date(args.last_seen), _normalize_date(args.last_reviewed),
            ),
        )
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"Added id={new_id}: {args.code} {args.component}/{args.operation} ({args.env}) as {args.status}")
    except sqlite3.IntegrityError as e:
        sys.exit(f"Insert failed: {e}")
    finally:
        conn.close()


def cmd_update(args):
    conn = connect()
    row = _find_one(conn, args)
    updates = {}
    for field in EDITABLE_FIELDS:
        val = getattr(args, field, None)
        if val is not None:
            if field in ("first_seen", "last_seen", "last_reviewed"):
                val = _normalize_date(val)
            updates[field] = val
    if not updates:
        sys.exit("Nothing to update — pass at least one editable field")
    setclause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE codes SET {setclause} WHERE id = ?",
        list(updates.values()) + [row["id"]],
    )
    conn.commit()
    print(f"Updated id={row['id']} {row['error_code']} {row['component_id']}/{row['operation_id']} ({row['environment']}): {', '.join(updates.keys())}")
    conn.close()


def cmd_list(args):
    conn = connect()
    wheres, params = [], []
    for col, val in [
        ("environment", args.env),
        ("status", args.status),
        ("supplier", args.supplier),
        ("error_code", args.code),
        ("component_id", args.component),
        ("operation_id", args.operation),
    ]:
        if val:
            wheres.append(f"{col} = ?")
            params.append(val)
    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    rows = conn.execute(
        f"SELECT id, error_code, component_id, operation_id, environment, status, supplier FROM codes {where} ORDER BY error_code, environment",
        params,
    ).fetchall()
    if not rows:
        print("(no rows match)")
        return
    print(f"{'ID':<5} {'CODE':<10} {'ENV':<16} {'STATUS':<18} {'SUPPLIER':<14} COMPONENT/OPERATION")
    print("-" * 110)
    for r in rows:
        sup = (r["supplier"] or "")[:14]
        print(f"{r['id']:<5} {r['error_code']:<10} {r['environment']:<16} {r['status']:<18} {sup:<14} {r['component_id']}/{r['operation_id']}")
    print(f"\n{len(rows)} row(s)")
    conn.close()


def cmd_show(args):
    conn = connect()
    row = _find_one(conn, args)
    print(f"=== id={row['id']}  {row['error_code']}  {row['component_id']}/{row['operation_id']}  ({row['environment']}) ===")
    print(f"  status         : {row['status']}")
    print(f"  classification : {row['classification_code'] or '-'}")
    print(f"  responsibility : {row['responsibility_type'] or '-'} / {row['category'] or '-'}")
    print(f"  supplier       : {row['supplier'] or '-'}")
    print(f"  first_seen     : {row['first_seen'] or '-'}")
    print(f"  last_seen      : {row['last_seen'] or '-'}")
    print(f"  last_reviewed  : {row['last_reviewed'] or '-'}")
    print(f"  related_pr     : {row['related_pr'] or '-'}")
    print(f"  argus_finding  : {row['related_argus_finding'] or '-'}")
    print(f"  notes          : {row['notes'] or '-'}")
    print(f"  suggested_fix  : {row['suggested_fix'] or '-'}")
    print(f"  created_at     : {row['created_at']}")
    print(f"  updated_at     : {row['updated_at']}")
    print()
    print("--- status history ---")
    hist = conn.execute(
        "SELECT * FROM status_history WHERE code_id=? ORDER BY changed_at",
        (row["id"],),
    ).fetchall()
    for h in hist:
        old = h["old_status"] or "(new)"
        note = f"  {h['note']}" if h["note"] else ""
        print(f"  {h['changed_at']}  {old:<18} -> {h['new_status']:<18}{note}")
    conn.close()


def cmd_history(args):
    conn = connect()
    row = _find_one(conn, args)
    hist = conn.execute(
        "SELECT * FROM status_history WHERE code_id=? ORDER BY changed_at",
        (row["id"],),
    ).fetchall()
    print(f"Status history for {row['error_code']} {row['component_id']}/{row['operation_id']} ({row['environment']}):")
    for h in hist:
        old = h["old_status"] or "(new)"
        print(f"  {h['changed_at']}  {old} -> {h['new_status']}  {h['note'] or ''}")
    conn.close()


def cmd_search(args):
    conn = connect()
    needle = f"%{args.text}%"
    rows = conn.execute(
        """SELECT id, error_code, component_id, operation_id, environment, status
           FROM codes WHERE notes LIKE ? OR suggested_fix LIKE ?
           ORDER BY error_code, environment""",
        (needle, needle),
    ).fetchall()
    for r in rows:
        print(f"  [{r['id']}] {r['error_code']} {r['component_id']}/{r['operation_id']} ({r['environment']}) — {r['status']}")
    print(f"\n{len(rows)} match(es)")
    conn.close()


SUPPRESSION_STATUSES = ["Known Error", "Pending Change", "Awaiting Release", "Resolved"]


def render_skinny_markdown(conn, env, include_all=False):
    """Render a skinny markdown table of triaged codes for one environment,
    grouped by status. By default only includes suppression-worthy statuses
    (codes Gemma should NOT flag); pass include_all=True for everything."""
    if include_all:
        rows = conn.execute(
            """SELECT error_code, component_id, operation_id, status, supplier
               FROM codes WHERE environment = ?
               ORDER BY status, error_code, component_id, operation_id""",
            (env,),
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(SUPPRESSION_STATUSES))
        rows = conn.execute(
            f"""SELECT error_code, component_id, operation_id, status, supplier
                FROM codes WHERE environment = ? AND status IN ({placeholders})
                ORDER BY status, error_code, component_id, operation_id""",
            [env] + SUPPRESSION_STATUSES,
        ).fetchall()

    if not rows:
        return f"_(no triaged codes for {env})_\n"

    from collections import defaultdict
    by_status = defaultdict(list)
    for r in rows:
        by_status[r["status"]].append(r)

    status_order = ["Known Error", "Pending Change", "Awaiting Release", "Fix Recommended",
                    "Assess", "Registered", "Resolved"]

    out = [f"_Source: `argus/triage/triage.db` (env={env}). {len(rows)} codes. Do not flag these in digests._", ""]
    for status in status_order:
        if status not in by_status:
            continue
        group = by_status[status]
        out.append(f"**{status}** ({len(group)})")
        out.append("")
        out.append("| Code | Supplier | Component / Operation |")
        out.append("|---|---|---|")
        for r in group:
            sup = r["supplier"] or "-"
            out.append(f"| `{r['error_code']}` | {sup} | `{r['component_id']}` / `{r['operation_id']}` |")
        out.append("")
    return "\n".join(out)


def cmd_render(args):
    conn = connect()
    markdown = render_skinny_markdown(conn, args.env, include_all=args.all)
    conn.close()

    if not args.inject:
        print(markdown)
        return

    target = Path(args.inject)
    if not target.exists():
        sys.exit(f"Target file not found: {target}")
    content = target.read_text()
    start_marker = "<!-- TRIAGED-CODES-START -->"
    end_marker = "<!-- TRIAGED-CODES-END -->"
    if start_marker not in content or end_marker not in content:
        sys.exit(
            f"Marker block not found in {target}.\n"
            f"Add this block where you want the table to appear:\n\n"
            f"{start_marker}\n(content will be regenerated here)\n{end_marker}"
        )
    start_idx = content.index(start_marker) + len(start_marker)
    end_idx = content.index(end_marker)
    new_content = (
        content[:start_idx]
        + f"\n<!-- regenerated by `triage render --env {args.env} --inject ...` -->\n\n"
        + markdown
        + "\n"
        + content[end_idx:]
    )
    target.write_text(new_content)
    print(f"Injected {len(markdown.splitlines())} lines into {target}")


def cmd_export_csv(args):
    """Export DB to a flat CSV (8 columns: key, code, component, operation,
    status, notes, suggested_fix, last_reviewed).

    Codes can exist in multiple environments; the CSV is single-source.
    When envs diverge on editable fields, prefer the row from --priority-env
    (or the alphabetically-first env when none is given) and emit a stderr
    warning so divergences are visible.
    """
    from collections import defaultdict

    conn = connect()
    rows = conn.execute(
        """SELECT error_code, component_id, operation_id, environment,
                  status, notes, suggested_fix, last_reviewed
           FROM codes
           ORDER BY error_code, component_id, operation_id, environment"""
    ).fetchall()
    conn.close()

    by_key = defaultdict(list)
    for r in rows:
        by_key[(r["error_code"], r["component_id"], r["operation_id"])].append(r)

    out_rows = []
    divergences = []
    priority_env = args.priority_env
    for key in sorted(by_key.keys()):
        candidates = by_key[key]
        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            if priority_env:
                chosen = next((c for c in candidates if c["environment"] == priority_env), candidates[0])
            else:
                chosen = sorted(candidates, key=lambda c: c["environment"])[0]
            ref = (chosen["status"], chosen["notes"], chosen["suggested_fix"], chosen["last_reviewed"])
            for c in candidates:
                cmp_ = (c["status"], c["notes"], c["suggested_fix"], c["last_reviewed"])
                if cmp_ != ref:
                    divergences.append((key, chosen["environment"], c["environment"]))
                    break
        out_rows.append(chosen)

    fieldnames = ["key", "error_code", "component_id", "operation_id",
                  "status", "notes", "suggested_fix", "last_reviewed"]

    if args.output:
        out_file = open(args.output, "w", newline="")
    else:
        out_file = sys.stdout

    try:
        writer = csv.DictWriter(out_file, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in out_rows:
            # Strip the (router, _unrouted) sentinel back to empty for CSV compatibility —
            # these are codes rejected before routing, so component/operation are unknown.
            comp = "" if r["component_id"] == "router" and r["operation_id"] == "_unrouted" else r["component_id"]
            op = "" if r["component_id"] == "router" and r["operation_id"] == "_unrouted" else r["operation_id"]
            writer.writerow({
                "key": f"{r['error_code']}|{comp}|{op}",
                "error_code": r["error_code"],
                "component_id": comp,
                "operation_id": op,
                "status": r["status"],
                "notes": r["notes"] or "",
                "suggested_fix": r["suggested_fix"] or "",
                "last_reviewed": r["last_reviewed"] or "",
            })
    finally:
        if args.output:
            out_file.close()

    print(f"Exported {len(out_rows)} rows" + (f" to {args.output}" if args.output else ""), file=sys.stderr)
    if divergences:
        label = priority_env or "alphabetically-first env"
        print(f"\n{len(divergences)} divergence(s) — kept the {label} version:", file=sys.stderr)
        for key, kept_env, other_env in divergences[:20]:
            print(f"  {key[0]} {key[1]}/{key[2]}  (kept {kept_env}, diverged from {other_env})", file=sys.stderr)


def cmd_import(args):
    conn = connect()
    inserted = skipped = duplicates = 0
    with open(args.csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comp = (row.get("component_id") or "").strip()
            op = (row.get("operation_id") or "").strip()
            code = (row.get("error_code") or "").strip()
            if not (comp and op and code):
                skipped += 1
                continue
            status = (row.get("status") or "").strip() or "Assess"
            notes = (row.get("notes") or "").strip() or None
            sfix = (row.get("suggested_fix") or "").strip() or None
            last_reviewed = (row.get("last_reviewed") or "").strip() or None
            if args.dry_run:
                print(f"[dry-run] would insert {code:10s} {comp}/{op}  ({args.env})  status={status}")
                inserted += 1
                continue
            try:
                conn.execute(
                    """INSERT INTO codes
                       (error_code, component_id, operation_id, environment,
                        status, notes, suggested_fix, last_reviewed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code, comp, op, args.env, status, notes, sfix, last_reviewed),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                duplicates += 1
    if not args.dry_run:
        conn.commit()
    conn.close()
    label = "[dry-run] " if args.dry_run else ""
    print(f"\n{label}import summary:")
    print(f"  inserted   : {inserted}")
    print(f"  skipped    : {skipped}  (missing required fields)")
    print(f"  duplicates : {duplicates}  (already in DB)")


def cmd_compare(args):
    conn = connect()
    rows = conn.execute(
        """SELECT environment, status, supplier, first_seen, last_seen, last_reviewed
           FROM codes
           WHERE error_code=? AND component_id=? AND operation_id=?
           ORDER BY first_seen, environment""",
        (args.code, args.component, args.operation),
    ).fetchall()
    print(f"{args.code}  {args.component}/{args.operation}  across environments:")
    if not rows:
        print("  (not in DB)")
        return
    print(f"  {'ENV':<16} {'STATUS':<18} {'SUPPLIER':<14} {'FIRST':<12} {'LAST':<12} {'REVIEWED':<12}")
    for r in rows:
        print(
            f"  {r['environment']:<16} {r['status']:<18} {(r['supplier'] or '-'):<14} "
            f"{(r['first_seen'] or '-'):<12} {(r['last_seen'] or '-'):<12} {(r['last_reviewed'] or '-'):<12}"
        )
    conn.close()


def build_parser():
    p = argparse.ArgumentParser(prog="triage", description="Argus triage DB CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_locator(sp):
        sp.add_argument("target", nargs="?", help="record id (integer) or composite key CODE|COMP|OP|ENV")
        sp.add_argument("--id", type=int, help="record id")
        sp.add_argument("--code", help="error code")
        sp.add_argument("--component", help="component_id")
        sp.add_argument("--operation", help="operation_id")
        sp.add_argument("--env", help="environment")

    def add_editable(sp, required_status=False):
        sp.add_argument("--classification-code", "--class", dest="classification_code")
        sp.add_argument("--responsibility-type", "--resp", dest="responsibility_type", choices=ALLOWED_RESPONSIBILITY)
        sp.add_argument("--category", "--cat")
        sp.add_argument("--supplier", "--sup")
        sp.add_argument("--status", choices=ALLOWED_STATUSES, default=("Assess" if required_status else None))
        sp.add_argument("--notes")
        sp.add_argument("--suggested-fix", "--fix", dest="suggested_fix")
        sp.add_argument("--related-pr", "--pr", dest="related_pr")
        sp.add_argument("--related-argus-finding", "--af", dest="related_argus_finding")
        sp.add_argument("--first-seen", dest="first_seen", help="date (or 'today'/'now')")
        sp.add_argument("--last-seen", "--seen", dest="last_seen", help="date (or 'today'/'now')")
        sp.add_argument("--last-reviewed", "--reviewed", dest="last_reviewed", help="date (or 'today'/'now')")

    a = sub.add_parser("add", help="add a new code row")
    a.add_argument("--code", required=True)
    a.add_argument("--component", required=True)
    a.add_argument("--operation", required=True)
    a.add_argument("--env", required=True)
    add_editable(a, required_status=True)
    a.set_defaults(func=cmd_add)

    u = sub.add_parser("update", help="update fields on an existing row")
    add_locator(u)
    add_editable(u)
    u.set_defaults(func=cmd_update)

    l = sub.add_parser("list", help="list codes")
    l.add_argument("--env")
    l.add_argument("--status")
    l.add_argument("--supplier")
    l.add_argument("--code")
    l.add_argument("--component")
    l.add_argument("--operation")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show one code with detail and history")
    add_locator(s)
    s.set_defaults(func=cmd_show)

    h = sub.add_parser("history", help="status history for one code")
    add_locator(h)
    h.set_defaults(func=cmd_history)

    sr = sub.add_parser("search", help="search notes and suggested_fix")
    sr.add_argument("text")
    sr.set_defaults(func=cmd_search)

    cp = sub.add_parser("compare", help="show a code across all environments")
    cp.add_argument("--code", required=True)
    cp.add_argument("--component", required=True)
    cp.add_argument("--operation", required=True)
    cp.set_defaults(func=cmd_compare)

    imp = sub.add_parser("import", help="bulk import codes from CSV — all rows attributed to --env")
    imp.add_argument("csv_path", help="path to CSV file")
    imp.add_argument("--env", required=True, help="environment to attribute all imported rows to")
    imp.add_argument("--dry-run", action="store_true", help="preview without writing")
    imp.set_defaults(func=cmd_import)

    ec = sub.add_parser("export-csv", help="export DB to flat CSV format (single-source, divergences warned to stderr)")
    ec.add_argument("--output", "-o", help="output file path (default stdout)")
    ec.add_argument("--priority-env", help="when codes diverge across envs, prefer this env's row")
    ec.set_defaults(func=cmd_export_csv)

    rd = sub.add_parser("render", help="render skinny markdown table of suppression-worthy codes for Gemma context")
    rd.add_argument("--env", required=True, help="environment to render")
    rd.add_argument("--all", action="store_true", help="include all statuses, not just suppression-worthy")
    rd.add_argument("--inject", help="path to a markdown file with TRIAGED-CODES marker block to replace")
    rd.set_defaults(func=cmd_render)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
