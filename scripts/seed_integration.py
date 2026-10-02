#!/usr/bin/env python3
"""Seed an integration's vault label on a live Campus auth deployment.

Sets the CLIENT_ID / CLIENT_SECRET / SCOPES / CONNECT_TARGETS keys for a
namespaced integration (google.classroom today) in the auth service's
vault, per the #730 design (§2.1) and #733 Phase 1. Idempotent: every
write is an upsert, so re-running refreshes the values.

Two credential pairs are involved (do not confuse them):

- The campus client performing the writes: CLIENT_ID / CLIENT_SECRET
  env vars — a campus client with vault write access. On dev these are
  the campus.auth service's admin client (`railway variables --service
  campus.auth`).
- The integration's Google OAuth client being seeded: --client-id /
  --client-secret args, or GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET env
  vars (on dev, the campus-classroom service's own vars — the same GCP
  client that used to back classroom's own OAuth flow). Secrets are
  never echoed; only a masked fingerprint is printed.

SCOPES defaults to the canonical classroom MVP list + the userinfo pair
(#730 §2.9) for --integration classroom; other integrations must pass
--scopes explicitly. CONNECT_TARGETS comes from --connect-target (repeat
for multiple origins); omitting it leaves the key unset, which keeps
the connect flow disabled (fail-closed).

Usage:
    CLIENT_ID=... CLIENT_SECRET=... \\
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \\
        .venv/Scripts/python.exe scripts/seed_integration.py \\
        --connect-target https://campus-profile-development.up.railway.app

Exit code 0 = seeded and verified.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

# Ensure the repo's campus package is imported, not a stale installed
# copy that may exist in site-packages (same convention as scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TIMEOUT = 60  # generous: fresh dev deploys wait out a cold DB pool (~25s observed)

# Canonical classroom MVP scopes + the userinfo pair (#730 §2.9): the
# vault copy is the integration's hard scope cap, mirroring what the
# campus-classroom app asks for.
CLASSROOM_SCOPES = (
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.addons.teacher",
    "https://www.googleapis.com/auth/classroom.addons.student",
    "https://www.googleapis.com/auth/classroom.course-work.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed an integration's vault label (CLIENT_ID, "
                    "CLIENT_SECRET, SCOPES, CONNECT_TARGETS)."
    )
    parser.add_argument(
        "--base-url",
        default="https://campusauth-development.up.railway.app",
        help="Auth service base URL (default: Railway dev)",
    )
    parser.add_argument(
        "--integration",
        default="classroom",
        help="Integration slug (default: classroom)",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("GOOGLE_CLIENT_ID"),
        help="The integration's Google OAuth client id "
             "(default: GOOGLE_CLIENT_ID env)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("GOOGLE_CLIENT_SECRET"),
        help="The integration's Google OAuth client secret "
             "(default: GOOGLE_CLIENT_SECRET env)",
    )
    parser.add_argument(
        "--scopes",
        default=None,
        help="Space-delimited scope cap (default: the classroom MVP "
             "list for --integration classroom)",
    )
    parser.add_argument(
        "--connect-target",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="HTTPS origin the connect flow may redirect to; repeat "
             "for multiple. Omit to leave connect disabled.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without writing",
    )
    return parser.parse_args(argv)


def fingerprint(secret_value: str) -> str:
    """Masked printable form of a secret (never the value itself)."""
    return f"***{secret_value[-4:]} (len {len(secret_value)})" if secret_value else "<empty>"


def vault_request(
        method: str,
        url: str,
        auth: tuple[str, str],
        json_body: dict | None = None,
) -> requests.Response:
    response = requests.request(
        method, url, auth=auth, json=json_body, timeout=TIMEOUT
    )
    if response.status_code >= 400:
        print(f"ERROR: {method} {url} -> {response.status_code}: "
              f"{response.text[:500]}")
        sys.exit(1)
    return response


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    admin_client_id = os.environ.get("CLIENT_ID")
    admin_client_secret = os.environ.get("CLIENT_SECRET")
    if not (admin_client_id and admin_client_secret):
        print("ERROR: CLIENT_ID / CLIENT_SECRET env vars required (the "
              "campus client that performs the vault writes)")
        sys.exit(1)
    if not (args.client_id and args.client_secret):
        print("ERROR: the integration's Google OAuth client is required "
              "via --client-id / --client-secret or GOOGLE_CLIENT_ID / "
              "GOOGLE_CLIENT_SECRET env vars")
        sys.exit(1)

    scopes = args.scopes
    if scopes is None:
        if args.integration == "classroom":
            scopes = " ".join(CLASSROOM_SCOPES)
        else:
            print("ERROR: --scopes is required for integrations other "
                  "than classroom")
            sys.exit(1)

    targets: list[str] = []
    for target in args.connect_target:
        parsed = urlparse(target)
        if parsed.scheme != "https" or not parsed.netloc:
            print(f"ERROR: --connect-target must be an HTTPS origin, "
                  f"got {target!r}")
            sys.exit(1)
        targets.append(f"{parsed.scheme}://{parsed.netloc}")

    label = f"google.{args.integration}"
    base_url = args.base_url.rstrip("/")
    auth = (admin_client_id, admin_client_secret)

    keys: dict[str, str] = {
        "CLIENT_ID": args.client_id,
        "CLIENT_SECRET": args.client_secret,
        "SCOPES": scopes,
    }
    if targets:
        keys["CONNECT_TARGETS"] = ",".join(targets)

    mode = "DRY RUN" if args.dry_run else "Seeding"
    print(f"{mode} vault label {label!r} at {base_url} "
          f"({len(keys)} keys):")
    for key, value in keys.items():
        shown = (f"{len(value.split())} scopes" if key == "SCOPES"
                 else fingerprint(value) if key == "CLIENT_SECRET"
                 else value)
        print(f"  {key} = {shown}")
    if args.dry_run:
        print("Dry run: nothing written.")
        return

    for key, value in keys.items():
        vault_request(
            "POST",
            f"{base_url}/auth/v1/vaults/{label}/{key}",
            auth=auth,
            json_body={"value": value},
        )
        print(f"  set {key}")

    present = vault_request(
        "GET",
        f"{base_url}/auth/v1/vaults/{label}/",
        auth=auth,
    ).json()["keys"]
    missing = set(keys) - set(present)
    if missing:
        print(f"ERROR: verification failed; keys missing after seed: "
              f"{sorted(missing)}")
        sys.exit(1)
    print(f"Verified: {label} now carries keys {sorted(present)}")


if __name__ == "__main__":
    main()
