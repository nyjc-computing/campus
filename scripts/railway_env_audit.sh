#!/usr/bin/env bash
# Audit both Railway environments' service inventories (#1109).
#
# Environment duplication used to copy every service into prod — six
# consumer "ghosts" ran dev code with dev vars until they were removed
# (2026-11-17), and any future duplication would recreate them. This
# read-only audit prints each environment's instances with their
# active-deployment status and flags:
#   - NEVER-DEPLOYED instances (the ghost signature: a duplicated or
#     orphaned instance that has never run — could also be a service
#     wired but awaiting its release, e.g. profile/nyxchange)
#   - SLEEPING/STOPPED instances in PRODUCTION (prod fleet members
#     should be up; a stopped prod instance is either deliberate or a
#     ghost)
#
# Usage: scripts/railway_env_audit.sh
# Requires: railway CLI (logged in), python on PATH.

set -euo pipefail

railway status --json 2>/dev/null | python -c '
import json, sys

data = json.load(sys.stdin)
for e in data["environments"]["edges"]:
    node = e["node"]
    env_name = node["name"]
    is_prod = env_name == "production"
    print(f"== {env_name} ==")
    for se in node["serviceInstances"]["edges"]:
        si = se["node"]
        name = si.get("serviceName") or "?"
        ads = si.get("activeDeployments") or []
        status = ads[0]["status"] if ads else "NEVER-DEPLOYED"
        flags = []
        if status == "NEVER-DEPLOYED":
            flags.append("ghost-candidate: instance has never deployed")
        if is_prod and status in ("SLEEPING", "STOPPED", "CRASHED"):
            flags.append(f"prod fleet member is {status}")
        line = f"  {name:34s} {status}"
        if flags:
            line += "   << " + "; ".join(flags)
        print(line)
'
