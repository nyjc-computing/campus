#!/usr/bin/env bash
# Trigger a Railway deployment and VERIFY it actually runs, with
# automatic recovery from the SKIPPED trap (#1106).
#
# `serviceInstanceDeploy(latestCommit)` can return true while the
# deployment row is created SKIPPED and nothing ever deploys; later
# triggers keep no-oping while the stale deployment keeps serving.
# Twice bitten on 2026-11-16 (campus.auth served without newly-set
# vars for ~25 minutes despite two "successful" deploy calls). This
# wrapper:
#
#   1. records the current active deployment (id + createdAt),
#   2. triggers with `railway redeploy --from-source` (latest commit),
#   3. polls `railway status --json` until a NEW deployment row
#      reaches SUCCESS — a new SKIPPED row triggers recovery
#      (redeploy of the ACTIVE deployment, the path that actually
#      works; a SKIPPED row has "no snapshot"), and
#   4. exits non-zero on CRASHED or when no new row materializes
#      (the silently-not-deploying state) within the timeout.
#
# Usage:
#   scripts/railway_deploy.sh <service> [environment] [timeout-seconds]
#
# Environment defaults to `development`; production needs an explicit
# second argument so a fat-fingered tab can't prod-deploy.
# Requires: railway CLI (logged in), python on PATH (JSON parsing only).
# Windows note: `railway` cannot be spawned from Windows-Python
# subprocess — this script runs it from bash directly, which is fine.

set -euo pipefail

SVC="${1:?usage: railway_deploy.sh <service> [environment] [timeout-seconds]}"
ENVIRONMENT="${2:-development}"
TIMEOUT="${3:-600}"
POLL_INTERVAL=10

# latest deployment row for one service: "<id>\t<createdAt>\t<status>"
# (empty when the service has never deployed). The service/env are
# passed to the inline python via `env` — a pipeline's `VAR=x cmd`
# prefix only applies to the first command.
snapshot_for() {
    railway status --json 2>/dev/null | env \
        RAILWAY_TARGET_ENV="$ENVIRONMENT" RAILWAY_TARGET_SVC="$SVC" \
        python -c '
import json, os, sys
data = json.load(sys.stdin)
for e in data["environments"]["edges"]:
    node = e["node"]
    if node["name"] != os.environ["RAILWAY_TARGET_ENV"]:
        continue
    for se in node["serviceInstances"]["edges"]:
        si = se["node"]
        if si.get("serviceName") == os.environ["RAILWAY_TARGET_SVC"]:
            ads = si.get("activeDeployments") or []
            if ads:
                a = ads[0]
                print("\t".join([a.get("id", ""), a.get("createdAt", ""),
                                 a.get("status", "")]))
            break
    break
'
}

echo "==> $SVC in $ENVIRONMENT: recording current deployment"
BEFORE=$(snapshot_for)
if [ -n "$BEFORE" ]; then
    echo "    active: $(echo "$BEFORE" | cut -f2) ($(echo "$BEFORE" | cut -f3))"
else
    echo "    none (service has never deployed)"
fi

echo "==> triggering deploy (railway redeploy --from-source)"
railway redeploy --service "$SVC" --environment "$ENVIRONMENT" --yes --from-source

ELAPSED=0
RECOVERED=0
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    sleep "$POLL_INTERVAL"
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    CURRENT=$(snapshot_for || true)
    ID=$(echo "$CURRENT" | cut -f1)
    CREATED=$(echo "$CURRENT" | cut -f2)
    STATUS=$(echo "$CURRENT" | cut -f3)
    BEFORE_CREATED=$(echo "$BEFORE" | cut -f2)

    if [ -z "$CURRENT" ]; then
        echo "    [${ELAPSED}s] no deployment row yet"
        continue
    fi
    if [ -n "$BEFORE_CREATED" ] && [ "$CREATED" = "$BEFORE_CREATED" ]; then
        echo "    [${ELAPSED}s] still the old deployment ($STATUS) — no new row"
        continue
    fi

    case "$STATUS" in
        SKIPPED)
            if [ "$RECOVERED" -eq 0 ]; then
                RECOVERED=1
                echo "    [${ELAPSED}s] SKIPPED trap hit — recovering with a plain redeploy of the active deployment"
                if ! railway redeploy --service "$SVC" --environment "$ENVIRONMENT" --yes; then
                    echo "    recovery redeploy refused (no snapshot?) — retrying --from-source"
                    railway redeploy --service "$SVC" --environment "$ENVIRONMENT" --yes --from-source
                fi
                BEFORE="$CURRENT"   # wait for the NEXT row now
            else
                echo "    [${ELAPSED}s] SKIPPED again after recovery — manual intervention needed (docs/prod-rollout.md §7.4)"
                exit 3
            fi
            ;;
        CRASHED|REMOVED)
            echo "    [${ELAPSED}s] deployment $STATUS — get logs: railway logs \"$ID\" -b"
            exit 1
            ;;
        SUCCESS)
            echo "==> verified: new deployment ($CREATED) reached SUCCESS"
            exit 0
            ;;
        *)
            echo "    [${ELAPSED}s] new deployment $STATUS ($CREATED)"
            ;;
    esac
done

echo "TIMEOUT after ${TIMEOUT}s: no new deployment row reached SUCCESS — the deploy is silently not happening. Check railway status / docs/prod-rollout.md §7.4." >&2
exit 2
