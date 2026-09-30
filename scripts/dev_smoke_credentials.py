#!/usr/bin/env python3
"""Smoke-test credentials + joined token against a Campus auth deployment.

Runs the full client path that broke in issue #633 end-to-end against a
live service: create credentials with a token, GET them back with the
joined token, deserialize via UserCredentials.from_resource(), and assert
the token arrives as an OAuthToken with schema.DateTime fields. Cleans up
after itself unless --keep is given.

Why this exists (2026-09-30): verifying this flow by hand cost roughly ten
improvised commands per session (creds lookup, request composition, three
common failure modes, cleanup). This script does it in one command with a
stable interface. Revisit whether it earns its keep after a few uses; if
the credentials flow changes shape, retire or reshape it rather than
accumulating flags.

Usage:
    CLIENT_ID=... CLIENT_SECRET=... \\
        .venv/Scripts/python.exe scripts/dev_smoke_credentials.py

    # Options: --base-url, --provider, --user-id, --expiry-seconds, --keep

Exit code 0 = all checks passed.

Known caveats:
- DELETE removes the credentials row only; an orphan token row remains in
  the tokens table (accepted dev footprint, precedent #631).
- Requires GET ?client_id= until #624 (missing default) is fixed; the
  script always sends it.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

# Ensure the repo's campus package is imported, not a stale installed copy
# that may exist in site-packages (same convention as the other scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from campus.common import schema  # noqa: E402
from campus.model import credentials  # noqa: E402

TIMEOUT = 10


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test credentials + joined token on a live service."
    )
    parser.add_argument(
        "--base-url",
        default="https://campusauth-development.up.railway.app/auth/v1",
        help="Base URL of the auth service (default: Railway dev)",
    )
    parser.add_argument("--provider", default="campus")
    parser.add_argument(
        "--user-id",
        default=None,
        help="Email-shaped user ID (default: smoke-<timestamp>@campus.dev)",
    )
    parser.add_argument("--expiry-seconds", type=int, default=3600)
    parser.add_argument(
        "--client-id",
        default=None,
        help="Client ID (default: env CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=None,
        help="Client secret (default: env CLIENT_SECRET)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Skip cleanup, leaving the smoke credentials in place",
    )
    args = parser.parse_args(argv)
    args.client_id = args.client_id or _require_env("CLIENT_ID")
    args.client_secret = args.client_secret or _require_env("CLIENT_SECRET")
    args.base_url = args.base_url.rstrip("/")
    if args.user_id is None:
        args.user_id = f"smoke-{int(time.time())}@campus.dev"
    return args


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: env {name} not set (or pass the corresponding flag)")
    return value


def main() -> int:
    args = parse_args()
    session = requests.Session()
    session.auth = (args.client_id, args.client_secret)
    base = f"{args.base_url}/credentials/{args.provider}/{args.user_id}"

    failures: list[str] = []

    def check(ok: bool, label: str) -> None:
        print(f"{'PASS' if ok else 'FAIL'}: {label}")
        if not ok:
            failures.append(label)

    created = False
    try:
        resp = session.post(
            base,
            json={"scopes": ["read"], "expiry_seconds": args.expiry_seconds},
            timeout=TIMEOUT,
        )
        check(resp.status_code == 201, f"POST credentials -> {resp.status_code}")
        created = resp.status_code == 201

        resp = session.get(base, params={"client_id": args.client_id},
                           timeout=TIMEOUT)
        check(resp.status_code == 200, f"GET credentials -> {resp.status_code}")
        if resp.status_code != 200:
            return finish(failures)
        resource = resp.json()

        user_creds = credentials.UserCredentials.from_resource(resource)
        token = user_creds.token

        # #648: the token resource carries the RFC 6749 fields
        token_resource = resource.get("token", {})
        check(token_resource.get("token_type") == "Bearer",
              "token resource token_type is Bearer "
              f"(got {token_resource.get('token_type')!r})")
        check(isinstance(token_resource.get("expires_in"), int)
              and "scope" in token_resource,
              "token resource carries expires_in and scope (#648)")

        check(isinstance(token, credentials.OAuthToken),
              f"from_resource token is OAuthToken (got {type(token).__name__})")
        if isinstance(token, credentials.OAuthToken):
            check(isinstance(token.expires_at, schema.DateTime),
                  "token.expires_at is schema.DateTime "
                  f"(got {type(token.expires_at).__name__})")
            check(isinstance(token.is_expired(), bool),
                  "token.is_expired() callable")
            check(token.token_type == "Bearer"
                  and isinstance(token.expires_in, int)
                  and isinstance(token.provider_fields, dict),
                  "token model exposes token_type/expires_in/provider_fields")
    finally:
        if created and not args.keep:
            resp = session.delete(base, timeout=TIMEOUT)
            check(resp.status_code == 200, f"DELETE credentials -> {resp.status_code}")
            resp = session.get(base, params={"client_id": args.client_id},
                               timeout=TIMEOUT)
            check(resp.status_code == 404,
                  f"GET after delete -> {resp.status_code} (expect 404)")

    return finish(failures)


def finish(failures: list[str]) -> int:
    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
