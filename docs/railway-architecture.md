# Railway architecture

How Campus is laid out on Railway: environments, services, request flow, and
the private-networking rules every deployment must follow. Operational
CLI/API recipes and their traps live in the `railway-ops` skill
(`.zcode/skills/railway-ops/SKILL.md`); gateway configuration is documented
in [deploy/gateway/README.md](../deploy/gateway/README.md).

Project: `campus` (`76e0b6d0-0832-41dc-841f-e3bc758d3eca`).

## Environments

| Environment | Purpose | Deploy trigger |
|---|---|---|
| `development` | Live dev; **merges to `weekly` autodeploy here** | push to `weekly` + config changes |
| `staging` | Parity environment (campus.api, campus.vault, postgres) | manual |
| `production` | Prod (campus.api, campus.vault, Campus DB) | manual, gated |

The main branch is never deployed; `weekly` is the integration branch for
all dev work (see [CONTRIBUTING.md](CONTRIBUTING.md)).

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
watch patterns scope its builds). Today the per-service domains above remain
the primary entrypoints; the gateway becomes the canonical host during the
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

## Build & runtime configuration

- Builder: Railpack (Nixpacks-compatible plan inferred from the repo;
  `railway.json` is NOT read by Railpack — use `railpack.json` or
  service-level settings). gunicorn comes from `pyproject.toml`.
- Start commands are set per service instance (environment-scoped); the
  production instances currently still bind `0.0.0.0` and must be switched
  to `[::]` as part of any production rollout (issue #995 checklist).
- Health checks: `GET /health` on every Flask app (#842 convention); the
  gateway serves its own `/health`.
