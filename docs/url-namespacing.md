# URL namespacing: gateway mounts, root-first apps, canonical origins

Spec of record for how consumer apps are mounted under the campus
gateway's namespaces, how URLs are built and emitted at runtime, and
which absolute URLs must be registered where (OAuth callbacks, Google
federated callbacks). Written 2026-11-26 from the verified live state
(weekly `a51ba4da`, flask-campus 0.2.8, ttv2#194 deployed to both
environments). Supersedes the scattered decision notes in campus#1274 /
#1290 / #1291 / #1295 / #1306, flask-campus#47 / #50, ttv2#182 / #187 /
#194, and the 2026-11-25 "Known limitations" block in
[deploy/gateway/README.md](../deploy/gateway/README.md). Umbrella issue:
campus#1295.

## The one-hostname model

Each environment is served under **one gateway hostname**: prod
`https://campus.nyjc.app`, dev `https://campus-dev.nyjc.app` (Cloudflare
in front), plus the equivalent plain-DNS gateway origins
`https://nyjc-campus.up.railway.app` and
`https://campus-development.up.railway.app` — same gateway service, same
behavior, plainer DNS. Browser traffic should use the pretty origins.

The gateway path-dispatches
([campus-gateway.conf.template](../deploy/gateway/campus-gateway.conf.template)):

- **Core services** at fixed, namespace-free roots: `/auth/*`
  `/integrations/*` → campus.auth, `/api/*` → campus.api, `/audit/*` →
  campus.audit. Their paths (`/auth/v1/…`, `/api/v1/…`, `/audit/v1/…`)
  never carry a consumer namespace, and the gateway sets **no** prefix
  header on these locations.
- **Consumer apps** under one namespace each: `/timetable/`
  (nyxchange-timetable-v2), `/apps/` (campus-apphost), `/admin/`
  (campus-admin), `/profile/` (campus-profile), `/classroom/`
  (campus-classroom). The gateway forwards the **full path unchanged**
  (no rewrites) and sets `X-Forwarded-Prefix: /<ns>` on these
  locations only.

## The consumer contract: root-first

1. **Define unprefixed.** Every route, the static mount, and the
   flask_campus auth blueprint live at the host root:
   `Blueprint("timetable", url_prefix=None)`, `Flask(__name__)` with the
   default `/static`. No namespace string may appear in route rules,
   templates, or tests — every emitted URL goes through `url_for` or
   endpoint names. (A literal `/timetable/…` in a template is the
   doubled-URL bug.)
   The same ban covers the flask_campus blueprint paths themselves, with
   a different failure mode: **never hardcode `/login`, `/logout` or
   `/finalize_login` in a template or script.** A namespace literal
   doubles under `SCRIPT_NAME`; a root literal stays root behind the
   gateway, where it is unroutable — the Sign In button pointing at
   `</login>` on `campus-dev.nyjc.app/admin/` (campus-admin#108,
   campus-classroom#166/#167). `url_for('auth.login')` /
   `url_for('auth.logout')` is the only namespacing-aware spelling;
   client-side links can't call it, so the template injects the URL
   (`const CAMPUS_LOGIN_URL = {{ url_for('auth.login') | tojson }}`) and
   the JS composes `next` from `location`. App-section paths under the
   app's own namespace root (`/admin/auth/…`, `/apps/…`) are the
   exception: they resolve identically on origin and gateway and may
   stay literal.
2. **Receive unprefixed.** PrefixFix
   ([flask_campus.prefix](https://github.com/nyjc-computing/flask-campus),
   installed by `init_app` since 0.2.8) moves `X-Forwarded-Prefix` into
   `SCRIPT_NAME` and strips the namespace from `PATH_INFO` exactly once
   (the header is consumed, so nested forwarding middleware cannot
   double-strip; malformed values — no leading slash, `//`, `..` — are
   rejected outright, not sanitized). Trust model: the header is honored
   from the immediately preceding hop, the same exposure class as
   `X-Forwarded-Proto`/`-Host`; a client reaching the app directly can
   spoof it and only breaks the generated URLs of its own requests — the
   OAuth callback URL stays registry-validated by campus.auth (#1291).
3. **Emit namespace-aware.** `url_for` prepends `SCRIPT_NAME`: behind
   the gateway every emitted URL — links, static assets, redirects, the
   auth surface — is `/<ns>/…`, keeping the browser inside the namespace
   the gateway actually routes; on the origin domain `SCRIPT_NAME` is
   empty and everything is root-relative. No app-side code: emission
   follows arrival automatically.

Summary row per surface:

| Browser GETs | App receives | App emits |
|---|---|---|
| `campus.nyjc.app/timetable/menu` | `GET /menu` | `/timetable/menu` |
| `nyjc-campus.up.railway.app/timetable/menu` | `GET /menu` (same gateway, plainer DNS) | `/timetable/menu` |
| `nyxchange-timetable-v2.up.railway.app/menu` | `GET /menu` (no header, `SCRIPT_NAME=""`) | `/menu` |

The `/timetable` namespace does not exist on origin domains —
`/timetable/login` 404s there by design; `/login` is the origin's auth
surface.

## Canonical origins: `PUBLIC_URL`

Every service requires `PUBLIC_URL` (a bare origin — scheme://host,
no path; boot-validated in production, see
[required-env-vars.md](required-env-vars.md)).
`campus.common.utils.url.canonical_origin()` uses it for **all**
absolute URL generation; the legacy request-host fallback was removed
(campus#652). Consequence: absolute URLs the app constructs — the OAuth
authorize target it sends browsers to, the finalize `redirect_uri` it
requests, auth's Google federated callback — are **identical regardless
of which host the request arrived on**.

Flipping a service's `PUBLIC_URL` (e.g. from a `*.up.railway.app` origin
to the pretty origin) is **the** cutover act: register the new origins'
redirect URIs first (#1291 ordering), flip `PUBLIC_URL` together with
every entry-point URL other apps hold for it, verify end-to-end, then
retire the old registrations.

## OAuth URL registration matrix

Because the finalize callback's emitted shape depends on the **arrival
shape** (`SCRIPT_NAME` at emission time), each campus OAuth client must
register, for **every origin the app is reachable on**, both shapes:

- `{origin}/{ns}/finalize_login` — arrivals through the gateway (header set)
- `{origin}/finalize_login` — direct-to-origin arrivals (no header)

The Google federated leg has **one shape per environment**: campus.auth
emits `{auth PUBLIC_URL}/auth/v1/google/callback`, so each environment's
Google OAuth client (GCP) registers exactly that one callback origin.

Registrations are additive in effect but **replacing in mechanism**:
`campus client update --redirect-uri` replaces the whole list — always
pass the full set. Register before the deploy/flip that makes the new
shape live (#1291 ordering).

## Do not combine mount mechanisms

`login_prefix` (flask-campus#47) **statically** mounts the auth
blueprint under an app-declared namespace; PrefixFix derives the
namespace from the gateway header. Behind campus-gateway, use **neither
explicitly — PrefixFix handles it**. Combining `login_prefix` with a
header-setting gateway doubles the namespace: PrefixFix strips one
`/<ns>`, so the statically mounted `/<ns>/login` never matches, while
`url_for` emits `SCRIPT_NAME + mount`. `login_prefix` remains valid
**only for header-less deployments**: a foreign path-dispatching proxy
that does not set the header, or a standalone deployment that wants a
namespaced auth surface on its own origin.

## Session cookies

Fleet scheme (campus#1290): every consumer sets a **distinct** session
cookie name (e.g. `campus_timetable_session`) so sign-ins do not clobber
each other across the apps sharing a gateway hostname. Never ship
Flask's default `session` cookie name in a consumer.

## Clients and service-to-service traffic

Namespaces are a **browser-surface** construct. The CLI, the
`campus_python` SDK, and any machine-to-machine caller address services
directly by configured origin + unprefixed service paths
(`/auth/v1/…`, `/api/v1/…`, `/audit/v1/…`) and are never affected by
`X-Forwarded-Prefix`, `SCRIPT_NAME`, or `PUBLIC_URL` (which only shapes
generated browser-facing URLs).

## Consumer onboarding checklist

Adopting the pattern in a consumer app:

1. Pin flask-campus ≥ 0.2.8.
2. Remove any `login_prefix` / `static_url_path` namespace edits;
   declare routes root-first (drop the app's own `url_prefix`); sweep
   templates and tests for literal namespace strings — endpoint names
   and `url_for` only.
3. Set a fleet-distinct session cookie name.
4. Register the campus OAuth client's finalize URIs for every reachable
   origin-shape (matrix above) **before** deploying.
5. Add the app to the gateway template's consumer locations — they set
   the header; no path rewrites are involved.
6. Verify both surfaces before any `PUBLIC_URL` flip: browser-walk the
   gateway hostname end-to-end (landing → login → Google → finalize →
   app surface) and the origin domain (root paths).

## Adoption state (2026-11-26)

- **nyxchange-timetable-v2**: flask-campus 0.2.8; auth surface + static
  prefix-mounted (ttv2#194). Its own timetable blueprint still carries
  `url_prefix="/timetable"` — a half-state in which generated links
  double the namespace behind the gateway (`/timetable/timetable/…`)
  and single-prefixed deep links 404; root-first conversion in flight.
- **campus-admin / campus-profile / campus-classroom**: flask-campus
  0.2.7 — the gateway header is inert to them; sign-ins happen on their
  own domains. Adoption pending (opt-in per app).
- **campus-apphost**: serves `/apps/` anonymously; no flask-campus pin.

## History

Gateway consumer mounts campus#1274; fleet session cookies campus#1290;
callback-registration ordering campus#1291; gateway umbrella campus#1295;
superseded gateway-side rewrites campus#1306 (removed); namespaced login
blueprint flask-campus#47; PrefixFix flask-campus#50; ttv2 opt-in
ttv2#182/#187 and PrefixFix adoption ttv2#194.
