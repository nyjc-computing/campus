"""Set an OAuth client's redirect_uris to an exact list (operator principal).

Validated recipe from the gateway rollout (campus#1295, 2026-11-26):
client principals cannot mutate client records (#881) — authenticate as
the OPERATOR principal (the campus-admin deployment's client on the
target environment; its CLIENT_ID/CLIENT_SECRET live in that service's
Railway variables) and edit the TARGET client's record.

Usage (Git Bash; secrets stay in the environment, never printed):

    railway variables -s campus-admin -e development --kv   # source creds
    CLIENT_ID=... CLIENT_SECRET=... CAMPUS_AUTH_URL=https://campusauth-development.up.railway.app \\
    TARGET_CLIENT_ID=uid-client-7f581eab \\
    EXPECTED_URIS=$'https://a.example/finalize_login\\nhttps://b.example/timetable/finalize_login' \\
    python scripts/railway_set_redirect_uris.py

Behavior: read → compare → write the exact EXPECTED_URIS list (the SDK
update FULL-REPLACES — read-append-write your list carefully; this
script pins the exact set so strays are visible in the diff). Prints
current and post-update lists for verification.

Requires the campus-suite .venv (campus_python). CAMPUS_AUTH_URL is the
bare origin for the SDK (the CLI wants the /auth/v1 suffix instead —
the two live-hit traps in the prod-oauth-client memory).
"""

import os

from campus_python import Campus

target = os.environ["TARGET_CLIENT_ID"]
expected = [u for u in os.environ.get("EXPECTED_URIS", "").splitlines() if u.strip()]
if not target or not expected:
    raise SystemExit("set TARGET_CLIENT_ID and EXPECTED_URIS")

campus = Campus(mode="server")
rec = campus.auth.clients[target].get()
current = list(rec.redirect_uris or [])
print(f"current redirect_uris on {target}:")
for u in current:
    print(f"  - {u}")

if set(current) == set(expected) and len(current) == len(expected):
    print("already exact; no update")
else:
    campus.auth.clients[target].update(redirect_uris=expected)
    after = list(campus.auth.clients[target].get().redirect_uris or [])
    print("post-update:")
    for u in after:
        print(f"  - {u}")
    if after != expected:
        raise SystemExit("post-update list does not match expected — investigate")
