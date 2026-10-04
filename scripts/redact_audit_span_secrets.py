#!/usr/bin/env python3
"""One-off patch: redact stored secrets in an audit spans table (#805).

Spans ingested before producer-side redaction (#805) carry credentials in
stored JSON fields: client_secret in /auth/v1/token request bodies,
access_token/refresh_token in token response bodies, Cookie session headers
on login spans, and query params on GET /root/authenticate calls. This
script rewrites those rows in place, applying the SAME redaction function
the tracing middleware uses (campus.audit.middleware.tracing.redact_sensitive),
so historical data matches what producers emit from now on.

The redaction is idempotent: values already masked are rewritten to the
same marker, so a second run reports zero changes.

Usage (dry run by default; --apply writes):

    POSTGRESDB_URI=postgresql://... python scripts/redact_audit_span_secrets.py [--apply]

Deploying against Railway dev (no public path to the audit Postgres — run
in-network as a one-off service; recipe proven 2026-10-03 on the migration
ledger, see docs/migration-protocol.md). Keep the repo layout (scripts/
beside campus/) so the sys.path insert above resolves:

    mkdir /tmp/redact-deploy && cd /tmp/redact-deploy
    mkdir scripts
    cp <repo>/scripts/redact_audit_span_secrets.py scripts/redact.py
    cp -r <repo>/campus campus_src          # indexer drops a dir named campus/
    printf 'flask\\nrequests\\npsycopg2-binary\\n' > requirements.txt
    cat > railway.json <<'JSON'
    {"startCommand": "mv campus_src campus && python scripts/redact.py"}
    JSON
    railway link -p <project> -e development -s campus.audit   # injects POSTGRESDB_URI
    railway up        # then read the deployment logs for the summary

    # rerun with startCommand "... scripts/redact.py --apply" (fresh
    # `railway up`: `railway redeploy` reuses the OLD deployment's config)

Exit code 0 = scan (and apply, if requested) completed.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Import the producer-side redaction so historical data ends up byte-for-byte
# consistent with what upgraded producers emit. Needs only flask+requests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from campus.audit.middleware.tracing import redact_sensitive  # noqa: E402

# JSON-bearing span columns scanned for secrets (#805)
REDACTED_COLUMNS = (
    "query_params",
    "request_headers",
    "request_body",
    "response_headers",
    "response_body",
)

TIMEOUT = 300


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redact stored secrets in an audit spans table (#805)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write redacted rows. Default is a read-only dry run.",
    )
    return parser.parse_args(argv)


def decode(raw: object) -> object:
    """Storage JSON-encodes structured columns; accept text or decoded."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def encode(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    uri = os.environ.get("POSTGRESDB_URI")
    if not uri:
        print("POSTGRESDB_URI not set; nothing to do.", file=sys.stderr)
        return 1

    with psycopg2.connect(uri, connect_timeout=TIMEOUT) as conn, \
            conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT id, {', '.join(REDACTED_COLUMNS)} FROM spans"
            )
            rows = cursor.fetchall()

            updates: list[tuple[str, dict]] = []
            per_column: dict[str, int] = dict.fromkeys(REDACTED_COLUMNS, 0)
            for row in rows:
                row_updates: dict[str, object] = {}
                for col in REDACTED_COLUMNS:
                    value = decode(row[col])
                    redacted = redact_sensitive(value)
                    if redacted != value:
                        row_updates[col] = encode(redacted)
                        per_column[col] += 1
                if row_updates:
                    updates.append((row["id"], row_updates))

            mode = "DRY RUN" if not args.apply else "APPLY"
            print(f"[{mode}] spans scanned: {len(rows)}")
            for col, count in per_column.items():
                print(f"[{mode}]   {col}: {count} row(s) with secrets")
            print(f"[{mode}] rows to update: {len(updates)}")

            if not args.apply:
                print("[DRY RUN] no rows written; rerun with --apply")
                return 0

            for row_id, row_updates in updates:
                assignments = ", ".join(f"{col} = %s" for col in row_updates)
                cursor.execute(
                    f"UPDATE spans SET {assignments} WHERE id = %s",
                    [*row_updates.values(), row_id],
                )
            print(f"[APPLY] updated {len(updates)} row(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
