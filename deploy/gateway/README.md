# Campus edge gateway

nginx path-dispatching reverse proxy that serves `campus.auth`,
`campus.api` and `campus.audit` under **one** hostname (Railway dev:
`campus-development.up.railway.app`). Anchored in issue #995; the
application-side prerequisites (per-service session cookie names,
`PUBLIC_PREFIX` health/landing placement) shipped in PR #996.

## Dispatch

| Public path            | Upstream (HTTPS hairpin)                              | Notes |
|------------------------|--------------------------------------------------------|-------|
| `/auth/*`              | `campusauth-development.up.railway.app`                | `/auth/v1/*` OAuth/users/sessions |
| `/integrations/*`      | `campusauth-development.up.railway.app`                | public integrations catalog — mounted *outside* `/auth/v1`, easy to forget |
| `/api/*`               | `campusapi-development.up.railway.app`                 | `/api/v1/*` |
| `/audit/*`             | `campusaudit-development.up.railway.app`               | API + web UI + static (all audit surface already lives under `/audit/*`) |
| `/`                    | gateway-owned                                          | 302 → `/audit/` (relative Location) |
| `/health`              | gateway-owned                                          | **gateway liveness only** (also the Railway healthcheck candidate) |

Paths pass through **unchanged** (`proxy_pass` with no URI part): each
service's internal routes already carry its public prefix, and the test
harness (`tests/fixtures/services.py`) runs this exact single-origin
topology, so no app-side routing change is involved.

## Environment variables (set on the Railway service)

| Variable    | Value                                    | Purpose |
|-------------|------------------------------------------|---------|
| `PORT`      | `8080`                                   | gateway's own listen port — the service domain's target port must match |
| `NGINX_ENTRYPOINT_LOCAL_RESOLVERS` | `1`               | activates the stock `15-local-resolvers.envsh`, which exports `NGINX_LOCAL_RESOLVERS` |

(`AUTH_PORT` / `API_PORT` / `AUDIT_PORT` are not currently used — they
belong to the private-upstream form documented below.)

## Upstream choice: public hairpin, not private networking (for now)

The template proxies to the services' **public** domains over HTTPS
(SNI on, `proxy_ssl_server_name`). Private networking
(`*.railway.internal`) was investigated on 2026-10-29 and **does not
currently work** from the gateway to the three services:

- The private endpoints report `ACTIVE` with stable IPv6 addresses
  (`campus-auth` / `campus-api` / `campusaudit.railway.internal`), and
  each backend listens on `0.0.0.0:8080` (verified in gunicorn boot
  logs).
- Yet DNS inside the gateway consistently returned **different**
  addresses than the live endpoints (same subnet, other interface IDs),
  and every connect was `ECONNREFUSED` — 0/10 requests ever reached an
  upstream. Not round-robin luck: dead addresses every time.
- Caveat discovered along the way: Railway's private DNS serves IPv6
  nameservers and nginx's `resolver` misparses bare IPv6 literals — the
  stock `15-local-resolvers.envsh` brackets them; that part is solved
  here and stays useful.

The public hairpin is functionally identical for dispatch (Railway
routes by SNI, not Host, so the backends still see
`Host: campus-development.up.railway.app` and generate correct
absolute URLs) at the cost of edge latency and a public round-trip.
When private networking is resolved (Railway support / config),
flip the three `set $*_upstream` lines in the template to the
`http://…railway.internal:${*_PORT}` form kept in the comment there —
no other change needed.

## Why per-request DNS resolution

Railway re-issues service private IPs on every backend redeploy. nginx
resolves literal `proxy_pass` hostnames once at config load, so a
static upstream would 502 after the next backend deploy until the
gateway restarted. The template therefore proxies to `$`-variables and
re-resolves through `NGINX_LOCAL_RESOLVERS` with a 10s TTL.

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
