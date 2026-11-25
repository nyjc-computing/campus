# Campus edge gateway

nginx path-dispatching reverse proxy that serves `campus.auth`,
`campus.api` and `campus.audit` under **one** hostname (Railway dev:
`campus-development.up.railway.app`). Anchored in issue #995; the
application-side prerequisites (per-service session cookie names,
`PUBLIC_PREFIX` health/landing placement) shipped in PR #996.

## Dispatch

| Public path            | Upstream (private mesh)                               | Notes |
|------------------------|--------------------------------------------------------|-------|
| `/auth/*`              | `${AUTH_HOST}` → `campus-auth-dev.railway.internal`    | `/auth/v1/*` OAuth/users/sessions |
| `/integrations/*`      | `${AUTH_HOST}`                                          | public integrations catalog — mounted *outside* `/auth/v1`, easy to forget |
| `/api/*`               | `${API_HOST}` → `campus-api-dev.railway.internal`      | `/api/v1/*` |
| `/audit/*`             | `${AUDIT_HOST}` → `campus-audit-dev.railway.internal`  | API (+ audit web UI retired to campus-admin: its `/audit/*` UI paths 302 to admin's own domain) |
| `/timetable/*`         | `${TIMETABLE_HOST}` → nyxchange-timetable-v2 (#1274)   | timetable portal (`/timetable/` namespace) |
| `/apps/*`              | `${APPHOST_HOST}` → campus-apphost (#1274)             | embedded-app host (`/apps/` namespace) |
| `/admin/*`             | `${ADMIN_HOST}` → campus-admin (#1274)                 | admin portal (`/admin/` namespace; home/sign-in/audit UI stay at admin's root) |
| `/profile/*`           | `${PROFILE_HOST}` → campus-profile (#1274)             | profile portal (`/profile/` namespace) |
| `/classroom/*`         | `${CLASSROOM_HOST}` → campus-classroom (#1274)         | classroom portal (`/classroom/` namespace) |
| `/`                    | gateway-owned                                          | 302 → `/audit/` (relative Location) |
| `/health`              | gateway-owned                                          | **gateway liveness only** (also the Railway healthcheck candidate) |

Paths pass through **unchanged** (`proxy_pass` with no URI part): each
service's internal routes already carry its public prefix, and the test
harness (`tests/fixtures/services.py`) runs this exact single-origin
topology, so no app-side routing change is involved.

## Downstream consumer apps (#1274)

Each downstream app is routed under the namespace it already serves on
its own deployment (verified by probing the dev domains 2026-11-25):
`/timetable/` (nyxchange-timetable-v2), `/apps/` (campus-apphost),
`/admin/` (campus-admin — e.g. `/admin/dashboard`; its home, sign-in and
audit-UI surfaces live at its root and are not carved out of the gateway's
root space), `/profile/`, `/classroom/`. A bare `/timetable` (no slash)
gets a 308 to the slashed form instead of the gateway's `/` → `/audit/`
bounce.

**Per-environment wiring.** The upstreams read `TIMETABLE_HOST` /
`APPHOST_HOST` / `ADMIN_HOST` / `PROFILE_HOST` / `CLASSROOM_HOST` (+`_PORT`,
`8080` everywhere today) from gateway service variables. The Dockerfile
ships `.invalid` placeholder `ENV` defaults, because the stock envsubst
runner substitutes only *defined* variables — an undefined `${TIMETABLE_HOST}`
would render literally and nginx would fail config load (gateway-wide
outage). Where the vars are unset (production, currently) the config stays
valid and those five paths just 502. Wiring an environment = set the vars
on that environment's gateway service + redeploy; the vars must reference
the environment's own mesh names.

**Private mesh, not the public hairpin.** Railway's edge rejects
Host-mismatched public requests with a plain nginx 404 on some services
(observed on timetable/apphost/profile/classroom 2026-11-25 — admin's edge
tolerated the same mismatch), so hairpinning with `Host: $host` is
unreliable for this set; the mesh has no such check. Private names carry
no `-dev` suffix (unlike the core trio's regularized `campus-auth-dev`
aliases): `campus-admin.railway.internal`, `campus-apphost.railway.internal`,
`campus-classroom.railway.internal`, `campus-profile.railway.internal`,
`nyxchange-timetable-v2.railway.internal` — read each service's rendered
`RAILWAY_PRIVATE_DOMAIN` when wiring, don't guess.

**Known limitations (observed in the 2026-11-25 dev smoke, #1274).**

- **Signed-out flows hit unrouted auth paths.** The apps build redirects
  from the request host (not their `PUBLIC_URL`), so a signed-out visitor
  to `/timetable/`, `/profile/`, `/classroom/` or `/admin/dashboard` is
  sent to the app's **root-level** auth surface (`/login`, `/sign-in`,
  `/`) — none of which the gateway routes (four apps share those names,
  so they cannot be dispatched), and the gateway 404s them (timetable's
  `/?next=…` lands on the gateway-owned `/` → `/audit/`). Signing in
  happens on the app's own domain today; OAuth `redirect_uri`s are also
  registered per origin domain. Making flows self-contained under the
  gateway hostname is the per-app cutover recipe (distinct
  `SESSION_COOKIE_NAMES` + routable login surfaces + redirect-URI
  re-registration) — app-side work, out of scope for #1274.
- **Session cookies thrash across apps** on the shared gateway host:
  the downstream apps don't set per-service cookie names the way the
  core trio does (`SESSION_COOKIE_NAMES`), and four of them share
  Flask's default name — signing into two apps in one browser clobbers
  whichever share it. Same caveat as pre-#996.
- **`/apps/` is the anonymously usable surface today** (campus-apphost
  serves it signed-out); the other four namespaces behave exactly as
  they do on their own domains, which signed-out currently means a
  login redirect into the 404s described above.
- campus-admin's audit UI keeps its own domain: the gateway's `/audit/`
  stays pointed at campus.audit (its API lives at `/audit/v1/*`);
  re-pointing `/audit/` at admin would strand the API. Admin's
  namespaced surface (`/admin/dashboard`, …) is routed; its root-level
  home/sign-in/resources surfaces are not — bare `/admin/` and `/admin`
  404 faithfully (the origin 404s them too; the canonical entry is
  `/admin/dashboard`).

## Access logs carry no query strings (#1130)

The template defines a `campus_nosecrets` log format that logs
`$uri` (path only) instead of the default `combined` `$request` (full
request line **including the query string**): OAuth authorization codes
ride the query string on the provider callbacks
(`/auth/v1/<provider>/callback?code=…`, `/finalize_login?code=…`) and
are bearer-equivalent while live. `$http_referer` is dropped for the
same reason (a navigation away from a callback page carries the
callback URL, query string included). Environment-access-policy §3
(2026-11-17): Railway runtime logs must not contain sensitive secrets.
Query-string debugging belongs to the audit trail, not the gateway log.

## Arrival timestamp: `X-Request-Start` comes from Railway's edge

Railway's edge sets `X-Request-Start` on every public request: a Unix
milliseconds timestamp for when the request was received
([Specs & Limits](https://docs.railway.com/networking/public-networking/specs-and-limits)).
The gateway passes it through untouched and must not stamp its own:
`proxy_set_header` would overwrite the edge's value with a later time in a
different format. The stamp added for #1241 in PR #1242 was removed for
that reason (#1243). The header is also present on requests addressed to
the services' own domains, which never cross the gateway.

Consumers must accept both forms, because stored spans carry both:
`1795515478341` (the edge: epoch milliseconds) and `t=1795515478.341`
(the former gateway stamp: epoch seconds). campus.audit derives
`tags.queue_ms` from it at ingest (#1243). Rejecting stale requests with a
TTL check remains future work under #1241.

## Environment variables (set on the Railway service)

| Variable    | Value                                    | Purpose |
|-------------|------------------------------------------|---------|
| `PORT`      | `8080`                                   | gateway's own listen port — the service domain's target port must match |
| `NGINX_ENTRYPOINT_LOCAL_RESOLVERS` | `1`               | activates the stock `15-local-resolvers.envsh`, which exports `NGINX_LOCAL_RESOLVERS` |
| `AUTH_HOST` / `API_HOST` / `AUDIT_HOST` | e.g. `campus-auth-dev.railway.internal` | core-trio private mesh names (set per environment since the 2026-11-19 flip) |
| `AUTH_PORT` / `API_PORT` / `AUDIT_PORT` | `8080` | core-trio upstream ports |
| `TIMETABLE_HOST` / `APPHOST_HOST` / `ADMIN_HOST` / `PROFILE_HOST` / `CLASSROOM_HOST` (+`_PORT`) | e.g. `campus-admin.railway.internal` | downstream-app upstreams (#1274); unset = Dockerfile `.invalid` placeholder, path 502s |

## Upstream choice: private networking (flipped 2026-11-19)

The template proxies to the services' **private** mesh names
(`http://${*_HOST}:${*_PORT}`), not the public domains. The public
hairpin was the original form: private networking was investigated on
2026-10-29 and did not work then (mesh DNS returned dead addresses,
every connect `ECONNREFUSED`), so the gateway hairpinned over HTTPS
until the 2026-11-19 service-rename + private-domain regularization
made mesh names stable per environment. The hairpin also has a second,
disqualifying problem for the downstream apps (#1274): Railway's edge
rejects Host-mismatched public requests with a plain nginx 404 on some
services, and the gateway always sends `Host: $host` (the gateway's own
domain). One hairpin-era caveat that still applies and is solved here:
Railway's private DNS serves IPv6 nameservers and nginx's `resolver`
misparses bare IPv6 literals — the stock `15-local-resolvers.envsh`
brackets them.

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
