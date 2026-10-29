# Campus edge gateway

nginx path-dispatching reverse proxy that serves `campus.auth`,
`campus.api` and `campus.audit` under **one** hostname (Railway dev:
`campus-development.up.railway.app`). Anchored in issue #995; the
application-side prerequisites (per-service session cookie names,
`PUBLIC_PREFIX` health/landing placement) shipped in PR #996.

## Dispatch

| Public path            | Backend                       | Notes |
|------------------------|-------------------------------|-------|
| `/auth/*`              | `campus-auth.railway.internal`| `/auth/v1/*` OAuth/users/sessions |
| `/integrations/*`      | `campus-auth.railway.internal`| public integrations catalog — mounted *outside* `/auth/v1`, easy to forget |
| `/api/*`               | `campus-api.railway.internal` | `/api/v1/*` |
| `/audit/*`             | `campusaudit.railway.internal`| API + web UI + static (all audit surface already lives under `/audit/*`) |
| `/`                    | gateway-owned                 | 302 → `/audit/` until the cutover decides otherwise |
| `/health`              | gateway-owned                 | **gateway liveness only** (also the Railway healthcheck candidate) |

Paths pass through **unchanged** (`proxy_pass` with no URI part): each
service's internal routes already carry its public prefix, and the test
harness (`tests/fixtures/services.py`) runs this exact single-origin
topology, so no app-side routing change is involved.

## Environment variables (set on the Railway service)

| Variable    | Value                                    | Purpose |
|-------------|------------------------------------------|---------|
| `AUTH_PORT` | `8080`                                   | campus.auth private upstream port |
| `API_PORT`  | `8080`                                   | campus.api private upstream port |
| `AUDIT_PORT`| `8080`                                   | campus.audit private upstream port |
| `PORT`      | *(injected by Railway; fallback 8080)*   | gateway's own listen port — set the service domain's target port to match |

The upstream *hostnames* are baked into the template on purpose: they
are Railway's private-network endpoint names, which are per-service and
stable (note they are **not** mechanical derivations of service names —
`campus.audit` resolves as `campusaudit.railway.internal`, no hyphen).
`RESOLVER_IP` is derived at container start from `/etc/resolv.conf`
(`15-gateway-env.sh`) and is not set by hand.

Railway private networking is IPv6-only; the nginx `resolver` handles
AAAA fine — do not add `ipv6=off`.

## Why per-request DNS resolution

Railway re-issues service private IPs on every backend redeploy. nginx
resolves literal `proxy_pass` hostnames once at config load, so a
static upstream would 502 after the next backend deploy until the
gateway restarted. The template therefore proxies to `$`-variables and
re-resolves through `RESOLVER_IP` with a 10s TTL.

## Railway service wiring

- Source: `nyjc-computing/campus`, branch `weekly`, **root directory
  `deploy/gateway`** (this folder is the Docker build context).
- Watch patterns: `deploy/gateway/**` only — gateway rebuilds must not
  ride along on unrelated weekly pushes (and the auth/api/audit watch
  patterns don't match this folder, so it's symmetric).

## Cutover notes (see #995 checklist)

- Until the services set `PUBLIC_PREFIX` (PR #996), `/auth/health`,
  `/api/health` and `/audit/health` 404 through the gateway — expected;
  the standalone `/health` on each service's own domain is unaffected.
- Federated Google login reached **through the gateway hostname** will
  fail with a redirect_uri mismatch until the Google client's
  authorized redirect URIs are updated (cutover step). Don't point
  browsers at the gateway for logins before the flip.
- The gateway domain shares no cookies with the per-service domains;
  sessions created on `campusauth-development.up.railway.app` do not
  carry over. That's fine pre-cutover.
