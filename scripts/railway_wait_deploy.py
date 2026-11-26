"""Wait for Railway deployments to reach SUCCESS.

Usage (from Git Bash, per the railway-ops skill's shell rules):

    python scripts/railway_wait_deploy.py --since 2026-11-26T08:00:00 \
        [--env production] [--service campus-gateway --service campus.api]

Waits until every named service's latest deployment is SUCCESS with a
createdAt after --since, then exits 0. Services default to the four
consumer-app deployments plus the gateway. No --service flag = all
tracked services.

Token handling follows the railway-ops skill: development needs
RAILWAY_TOKEN (exported per shell); production needs the personal
login — run with `env -u RAILWAY_TOKEN` and the active login carrying
production access. The script spawns `railway` via subprocess and needs
MSYS `env` on PATH, so run it from Git Bash, not Windows-Python.
"""

import argparse
import json
import subprocess
import sys
import time

DEFAULT_SERVICES = [
    "campus-gateway",
    "nyxchange-timetable-v2",
    "campus-classroom",
    "campus-apphost",
    "campus-admin",
    "campus-profile",
]
ENVS = {
    "development": "e954f5fa-1195-41af-b737-b5732028331b",
    "production": "d5221f3b-b5c9-4d78-ac36-b0cb7b9d0a0e",
}
POLL_SECONDS = 25


def railway(args: list[str]) -> str:
    """Run `railway` via subprocess — from Git Bash, never Windows-Python
    directly (railway-ops skill; MSYS PATH resolves env.exe + railway)."""
    # RAILWAY_API_TOKEN always stripped (it overrides RAILWAY_TOKEN
    # silently — railway-ops skill). RAILWAY_TOKEN handling is the
    # caller's: keep it exported for development; drop it (`env -u
    # RAILWAY_TOKEN python scripts/...`) so production resolves via the
    # personal login.
    cmd = ["env", "-u", "RAILWAY_API_TOKEN", "railway"] + args
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def service_ids(env_id: str, wanted: set[str]) -> dict[str, str]:
    raw = railway(["status", "--json"])
    ids = {}
    for e in json.loads(raw)["environments"]["edges"]:
        for si in e["node"].get("serviceInstances", {}).get("edges", []):
            n = si["node"]
            name = n.get("serviceName")
            if name in wanted and e["node"]["name"] in ENVS:
                ids[name] = n["serviceId"]
    return ids


def latest(sid: str, env_id: str) -> tuple[str, str]:
    out = railway([
        "api",
        "query($e:String!,$s:String!){ serviceInstance(environmentId:$e, serviceId:$s)"
        "{ latestDeployment { status createdAt } } }",
        "--var", f"e={env_id}", "--var", f"s={sid}",
    ])
    d = json.loads(out)["data"]["serviceInstance"]["latestDeployment"]
    return d["status"], d["createdAt"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="ISO timestamp; deployments must be newer")
    parser.add_argument("--env", default="development", choices=sorted(ENVS))
    parser.add_argument("--service", action="append", dest="services")
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait (default 900)")
    args = parser.parse_args()

    env_id = ENVS[args.env]
    wanted = set(args.services or DEFAULT_SERVICES)
    ids = service_ids(env_id, wanted)
    missing = wanted - set(ids)
    if missing:
        print(f"services not found in {args.env}: {sorted(missing)}", file=sys.stderr)
        return 2

    done: dict[str, str] = {}
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        rows = []
        pending = False
        for name, sid in ids.items():
            if name in done:
                rows.append(f"{name:24s} SUCCESS {done[name]}")
                continue
            status, created = latest(sid, env_id)
            if status == "SUCCESS" and created > args.since:
                done[name] = created
                rows.append(f"{name:24s} SUCCESS {created}")
            else:
                pending = True
                rows.append(f"{name:24s} {status} {created}")
        print(" | ".join(rows), flush=True)
        if not pending:
            print("ALL DEPLOYED")
            return 0
        time.sleep(POLL_SECONDS)
    print(f"TIMEOUT: not all services deployed within {args.timeout}s", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
