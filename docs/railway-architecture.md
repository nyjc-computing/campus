# Railway architecture

How Campus is laid out on Railway: environments, services, request flow, and
the private-networking rules every deployment must follow. The environment,
access, and log-scrubbing policy lives in
[environment-access-policy.md](environment-access-policy.md); operational
CLI/API recipes and their traps live in the `railway-ops` skill
(`.zcode/skills/railway-ops/SKILL.md`); gateway configuration is documented
in [deploy/gateway/README.md](../deploy/gateway/README.md).

Project: `campus` (`76e0b6d0-0832-41dc-841f-e3bc758d3eca`).

## Environments

| Environment | Purpose | Deploy trigger |
|---|---|---|
| `development` | Live dev and **all testing**; **merges to `weekly` autodeploy here** | push to `weekly` + config changes |
| `production` | Prod fleet (auth/api/audit/gateway + consumers + per-service DBs, live 2026-11-16; see [prod-rollout.md](prod-rollout.md)) | push to `main` — i.e. the `weekly` → `main` release PR, the only path to `main` |

`weekly` is the integration branch for all dev work
([CONTRIBUTING.md](CONTRIBUTING.md)). The `weekly` → `main` cutover
completed 2026-11-17: production instances deploy from `main`, and pushes
to `weekly` touch `development` only (prod-rollout.md §6 records the
cutover). Two environments only — the `staging` and
`production-legacy` Railway environments, the `staging` git branch, and
its ruleset were all deleted 2026-11-17 (#1122).

**Access (policy, 2026-11-17):** production Railway access — logs,
variables, SSH, dashboards, prod data — is **superadmin-only**; routine
Railway CLI/API access is environment-bound to `development`; production
data is never accessed directly. Details:
[environment-access-policy.md](environment-access-policy.md).

## Service inventory (development)

Campus core — one Flask app per service, all built from this repo with
`campus.deploy.create_app` (selected by the `DEPLOY` env var):

| Service | App | Public domain | Notes |
|---|---|---|---|
| campus.auth | campus.auth | campusauth-development.up.railway.app | gunicorn, 2 workers |
| campus.api | campus.api | campusapi-development.up.railway.app | gunicorn |
| campus.audit | campus.audit | campusaudit-development.up.railway.app | gunicorn; owns the audit web UI |
| campus-gateway | `deploy/gateway/` nginx | campus-development.up.railway.app | unified host; see below |
| campus.vault | campus.vault | — | secrets vault (shared across envs) |

Backing stores: `campus.auth-postgres`, `campus.auth-mongodb`,
`campus.api-postgres`, `campus.api-mongodb`, `campus.audit-postgres`
(Railway images). Other project services (campus-classroom, campus-admin,
campus-profile, …) deploy from their own repos into the same environment.

Base URLs for inter-service clients are registered in
`campus/config.py` (`BASE_URLS`) and consumed via `get_base_url()`.

## Request flow: single gateway, prefixed paths

`campus-development.up.railway.app` (campus-gateway, nginx) terminates TLS
and dispatches by path prefix:

```
/integrations/, /auth/  → campus-auth.railway.internal:8080    (campus.auth)
/api/                   → campus-api.railway.internal:8080     (campus.api)
/audit/                 → campusaudit.railway.internal:8080    (campus.audit)
/health                 → 200 "ok"        (gateway-owned)
/                       → 302 /audit/     (gateway-owned)
```

Upstreams resolve via the Railway mesh DNS on every request (nginx
`resolver … valid=10s`), so redeploys of backends need no gateway change.
The gateway is deployed from `deploy/gateway/` in this repo (rootDirectory +
watch patterns scope its builds). The gateway is LIVE and dispatching to
all three services on dev (end-to-end smoke green 2026-10-30); the
per-service domains above remain the primary entrypoints until the
single-hostname cutover tracked on issue #995 (`PUBLIC_PREFIX`,
`SESSION_COOKIE_NAMES` prerequisites shipped in PR #996).

## Private networking rules (must-follow for every deployment)

Railway's private network (the `*.railway.internal` mesh) is **IPv6-only**:

- Services that accept mesh traffic must listen on IPv6 — gunicorn
  `--bind [::]:$PORT` (dual-stack; public IPv4 keeps working), MongoDB
  `mongod --ipv6 --bind_ip ::,0.0.0.0`. An app bound only to `0.0.0.0`
  rejects mesh connections.
- Cross-service calls use `<name>.railway.internal:<port>` names
  (e.g. `campus.auth` → `auth-postgres.railway.internal:5432`); names are
  not mechanically derivable from service names, check the dashboard/API.
- Do not hairpin: calling a service's own public domain from inside Railway
  hangs (internal DNS returns a mesh address that only serves targetPort).
- Postgres/MongoDB URIs for each service live in its Railway variables
  (`MONGODB_URI`, `POSTGRESDB_URI`, …); some one-off tooling uses the public
  TCP proxy instead (e.g. audit-postgres from a workstation).

## In-deployment observability

What a deployment can measure about itself (probed empirically 2026-11-24,
#1239 — recipes and traps live in the railway-ops skill):

- **Every replica is a dedicated microVM** (boot log: "Booting VM for
  replica N"; kernel `6.18.60-railway`), sized to the service's instance
  limits. The defaults are generous — 32 vCPU / 32 GB / pid limit 1000 —
  and the guest sees its entitlement directly: `nproc` and
  `os.cpu_count()` report the vCPU limit, `/proc/meminfo` reports the
  memory limit. Worker sizing off `os.cpu_count()` is therefore
  entitlement-correct, but a service with no limits set looks like a
  32-core machine.
- **CPU%**: sample `/sys/fs/cgroup/cpu.stat` and diff `usage_usec` against
  wall time; `nr_throttled` / `throttled_usec` double as a CPU-starvation
  signal. The other cgroup files (`cpu.max`, `memory.max` / `memory.current` /
  `memory.peak`, `pids.*`) are **empty** — Railway sizes the VM instead of
  enforcing cgroup quotas, so the quota-denominator question doesn't arise.
- **RAM**: `/proc/meminfo` `MemAvailable` (VM headroom),
  `/proc/self/status` `VmRSS` (process), `/sys/fs/cgroup/memory.stat`
  (anon/file breakdown). psutil is not in the fleet images — parse the
  files.
- **Instance identity and count**: `RAILWAY_REPLICA_ID` names the replica;
  no variable exposes the count. From inside, resolve
  `$RAILWAY_PRIVATE_DOMAIN` — the mesh DNS returns one AAAA record per
  live replica. From outside, GraphQL `deployment(id){ instances { id
  status } }` lists them, and instance `id` == the in-guest
  `RAILWAY_REPLICA_ID`.
- **Scaling replicas** (e.g. for the multi-region failover pattern) needs
  `numReplicas` AND `multiRegionConfig.<region>.numReplicas` set to the
  same value — the per-region entry (default 1) silently overrides the
  top-level field. Recipe in the railway-ops skill.
- **Request arrival time**: Railway's edge stamps every public request with
  `X-Request-Start` — Unix milliseconds for when the request was received
  ([Specs & Limits](https://docs.railway.com/networking/public-networking/specs-and-limits)).
  It is present on requests to the services' own domains as well. The
  gateway passes it through; never stamp it there, because
  `proxy_set_header` would overwrite the edge's earlier value (#1243). The
  gap between that stamp and a service's first line of code is the queue
  wait that WSGI cannot see by itself. A development sample on 2026-11-24
  put it at 5–7 ms on campus.auth and campus-admin and at about 110 ms on
  campus.audit (#1245); clock skew between the edge and the VM is part of
  the measurement.

## Sleep: outbound traffic keeps a service awake

Railway's serverless deployments sleep on **outbound** traffic, not CPU:
"Inactivity is based on the detection of any outbound packets, which could
include network requests, database connections, or even NTP." A service is
treated as inactive 5 minutes after its last packet and, because
inactivity is sampled, sleeps somewhere between 5 and 10 minutes after it.
Inbound traffic from the internet or from another service in the same
project wakes it, and the first request to a slept service may get a 502
([Deployments → Serverless](https://docs.railway.com/deployments/serverless)).

The rule that follows: **no outbound packets except while serving an
inbound request.** A timer may compute, sample and buffer locally; it must
not send. A heartbeat thread, a connection pool with keep-alives, or a
cron that pings a service every minute keeps it awake for good. Periodic
work rides on request traffic instead (#1249).

## Build & runtime configuration

- Builder: Railpack (Nixpacks-compatible plan inferred from the repo;
  `railway.json` is NOT read by Railpack — use `railpack.json` or
  service-level settings). gunicorn comes from `pyproject.toml`.
- Start commands are set per service instance (environment-scoped);
  all instances (dev and production) bind `[::]` for the IPv6-only
  private mesh.
- Health checks: `GET /health` on every Flask app (#842 convention); the
  gateway serves its own `/health`.
