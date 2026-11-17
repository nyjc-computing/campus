#!/usr/bin/env python3
"""Initialize a service's storage tables out-of-band (#1103).

Production deployments block startup storage initialization: the
storage layer's init_from_model is @env.block_env(PRODUCTION), and
startup init runs through campus.bootstrap.run_init_storage, which
skips there. A fresh production database therefore needs this one-off
run before the service's first boot (docs/prod-rollout.md §3, phase 2):

    railway ssh -s campus.api -e production
    ENV=development python scripts/init_storage.py --service api

ENV=development applies to this process only: it unlocks the storage
DDL layer while the deployments themselves stay in production. Each
target is idempotent (CREATE TABLE IF NOT EXISTS / collection
bootstrap), so the script is safe to re-run. Document-backed resources
are not listed: their collections auto-create on first use.

After this, bring the migration ledger up to date
(`python migrations/runner.py ensure` + `stamp`) so the startup
pending-migration warning reflects reality — see
docs/migration-protocol.md.

Supersedes the per-table scripts/init_*.py fragments (pre-split era,
hardcoded Codespaces paths): this wrapper derives the target list from
the service's own resources, so a new table-backed resource only needs
a line here.
"""

import argparse
import os
import sys
from collections.abc import Callable

# Make the campus package importable when run from a repo checkout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _auth_targets() -> list[tuple[str, Callable[[], None]]]:
    from campus.auth.resources.client import (
        ClientsResource,
        ensure_public_client_schema,
    )
    from campus.auth.resources.credentials import CredentialsResource
    from campus.auth.resources.grant import GrantsResource
    from campus.auth.resources.user import UsersResource
    from campus.auth.resources.vault import VaultsResource

    def clients() -> None:
        ClientsResource.init_storage()
        ensure_public_client_schema()

    return [
        ("users table", UsersResource.init_storage),
        ("vault table", VaultsResource.init_storage),
        ("credentials table", CredentialsResource.init_storage),
        ("clients tables + public-client schema", clients),
        ("access grants table", GrantsResource.init_storage),
    ]


def _api_targets() -> list[tuple[str, Callable[[], None]]]:
    from campus.api.resources.calendar import CalendarResource
    from campus.api.resources.circle import CirclesResource
    from campus.api.resources.emailotp import EmailOTPResource
    from campus.api.resources.timetable import TimetablesResource

    return [
        ("emailotp table", EmailOTPResource.init_storage),
        ("timetable members table", TimetablesResource.init_storage),
        ("school calendar table", CalendarResource.init_storage),
        ("circles collection + access-control bootstrap",
         CirclesResource.init_storage),
    ]


def _audit_targets() -> list[tuple[str, Callable[[], None]]]:
    from campus.audit.resources import ratelimit
    from campus.audit.resources.apikeys import APIKeysResource
    from campus.audit.resources.traces import TracesResource

    return [
        ("api keys table", APIKeysResource.init_storage),
        ("trace spans table", TracesResource.init_storage),
        ("rate-limit buckets table", ratelimit.init_storage),
    ]


TARGETS = {
    "auth": _auth_targets,
    "api": _api_targets,
    "audit": _audit_targets,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/init_storage.py",
        description="Out-of-band storage bootstrap for a suite service "
                    "(#1103). Run with ENV=development for this process "
                    "only.",
    )
    parser.add_argument(
        "--service", required=True, choices=sorted(TARGETS),
        help="whose storage to initialize (the DEPLOY context is set "
             "from this, so vault-backed secrets resolve for the right "
             "service)",
    )
    args = parser.parse_args()

    # Avoid a vault lookup for POSTGRESDB_URI: DEPLOY selects the
    # service context the same way the deployments do.
    os.environ.setdefault("DEPLOY", f"campus.{args.service}")

    from campus.common import env
    if env.ENV == env.PRODUCTION:
        print(
            "ERROR: ENV=production — storage initialization is blocked "
            "there by design. Re-run with ENV=development for THIS "
            "process only: ENV=development python scripts/init_storage.py "
            f"--service {args.service}",
            file=sys.stderr,
        )
        return 1

    print("=" * 80)
    print(f"INITIALIZING {args.service.upper()} STORAGE "
          f"(ENV={env.ENV}, DEPLOY={os.environ['DEPLOY']})")
    print("=" * 80)

    failures: list[str] = []
    for label, run in TARGETS[args.service]():
        try:
            run()
        except Exception as e:
            failures.append(label)
            print(f"[FAILED] {label}: {type(e).__name__}: {e}")
        else:
            print(f"[ok] {label}")

    if failures:
        print(
            f"\n{len(failures)} target(s) failed: {', '.join(failures)}\n"
            "Fix the connection/credentials and re-run (every target is "
            "idempotent). Then update the migration ledger: python "
            "migrations/runner.py ensure + stamp.",
            file=sys.stderr,
        )
        return 1
    print(
        "\nAll targets initialized. Now update the migration ledger "
        "(python migrations/runner.py ensure + stamp) — see "
        "docs/migration-protocol.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
