#!/usr/bin/env python3
"""Backfill Client.allowed_scopes from issued campus tokens.

Rollout aid for the fail-closed scope allowlist (#705,
docs/auth-token-invariants.md A1): existing clients predate the
allowed_scopes column and backfill with an empty allowlist, which
rejects every scope-bearing login. This script unions the scopes of
each client's campus-provider credential tokens and writes the result
to the client's allowed_scopes, so a deployed client keeps working
with exactly the scopes it has actually been granted. Clients with no
campus credentials are left empty (an admin sets their allowlist
explicitly via PATCH /clients/{id}/).

Idempotent: re-running recomputes the same union. It only ever widens
a client's allowlist if new scopes were granted since the last run.

Usage (on Railway where POSTGRESDB_URI is available):
    python scripts/backfill_client_allowed_scopes.py [--dry-run]
"""

import argparse
import os
import sys

# Set DEPLOY to avoid vault lookup for POSTGRESDB_URI
os.environ.setdefault('DEPLOY', 'campus.auth')

# Make the campus package importable when run from a repo checkout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if 'POSTGRESDB_URI' not in os.environ:
    print("WARNING: POSTGRESDB_URI not set in environment")
    print("Proceeding - the storage backend will fail if unconfigured")

from campus.auth import resources as auth_resources
from campus.auth.resources.client import ensure_public_client_schema
from campus.auth.resources.credentials import (
    cred_storage,
    token_storage,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the computed allowlists without writing them",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("BACKFILLING CLIENT ALLOWED_SCOPES FROM ISSUED TOKENS")
    print("=" * 80)

    # Align the table schema first (no-op where current) so the update
    # below does not fail with UndefinedColumn on pre-#705 databases
    ensure_public_client_schema()

    scopes_by_client: dict[str, set[str]] = {}
    credentials = cred_storage.get_matching({"provider": "campus"})
    for cred in credentials:
        token_record = token_storage.get_by_id(cred.get("token_id", ""))
        if not token_record:
            continue
        raw_scopes = token_record.get("scope") or ""
        client_id = cred.get("client_id", "")
        scopes_by_client.setdefault(client_id, set()).update(
            raw_scopes.split()
        )

    if not scopes_by_client:
        print("No campus credentials found; nothing to backfill.")

    for client_id, scopes in sorted(scopes_by_client.items()):
        allowlist = sorted(scopes)
        try:
            client = auth_resources.client[client_id]
            current = client.get().allowed_scopes
        except Exception as e:
            print(f"✗ {client_id}: cannot read client ({e}); skipped")
            continue
        # Never narrow an allowlist an admin has already set
        merged = (
            sorted(set(current) | set(allowlist))
            if current
            else allowlist
        )
        if merged == sorted(current):
            print(f"• {client_id}: allowlist already {merged}")
            continue
        if args.dry_run:
            print(f"… {client_id}: would set {merged}")
            continue
        client.update(allowed_scopes=merged)
        print(f"✓ {client_id}: allowed_scopes set to {merged}")

    print("=" * 80)


if __name__ == "__main__":
    main()
