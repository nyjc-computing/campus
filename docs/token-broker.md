# Token Bridge — upstream access tokens on demand

The token bridge is how Campus-ecosystem apps (first- and second-party,
e.g. campus-classroom) call non-Campus APIs — Google Classroom, and
later other proxied providers — **on behalf of a signed-in user,
without ever storing the user's non-Campus tokens**.

Campus is the sole custodian of upstream credentials: it holds the
Google access *and refresh* tokens obtained through its OAuth proxy,
grows their scopes through user consent (see
[auth-login-flow.md](auth-login-flow.md), *Upstream (Google) scopes*),
and releases only short-lived access tokens on demand. Platform
developers are not expected to manage OAuth tokens at all.

Contract invariants: [auth-token-invariants.md](auth-token-invariants.md)
groups B (custody), C (bridge), D (downstream client contract).

## The endpoint

```
POST /auth/v1/broker/{provider}
Authorization: Bearer <campus access token for the user>
Content-Type: application/json

{"min_scopes": ["https://www.googleapis.com/auth/classroom.rosters"]}
```

- `provider` — currently `google` (github/discord follow the same
  shape once needed).
- `min_scopes` (optional) — upstream scopes the caller requires for
  the call it is about to make.

Success — `200`:

```json
{
  "provider": "google",
  "user_id": "user@nyjc.edu.sg",
  "access_token": "ya29....",
  "token_type": "Bearer",
  "expires_in": 1234,
  "scope": "email profile https://www.googleapis.com/auth/classroom.rosters"
}
```

That is the entire payload: access token, expiry, scope. **No refresh
token is ever included** — Campus refreshes silently from its stored
credential when the upstream token has expired, so the value you
receive is always live. Use it in memory until `expires_in`, then ask
again; asking again is cheap (Campus-side refresh happens at most once
per upstream token lifetime).

## Who may call

Fail-closed — all of the following must hold
(invariants C1; denials are 403):

1. The request carries a **campus Bearer token bound to the user**
   (client-credentials/basic auth has no user and is denied).
2. The client that token was issued to is **confidential** (has a
   secret; browser/SPA/CLI public clients are never eligible).
3. That client is flagged **`token_bridge: true`** at registration
   (`POST /auth/v1/clients/` or `PATCH /auth/v1/clients/{id}/`,
   admin-reviewed).

## Scope rules

- `min_scopes` must be within the client's registered
  `upstream_scopes[provider]` allowlist → otherwise `400`
  `AUTH_INVALID_SCOPE` (invariant C3a).
- The user's actual upstream grant (grown through Campus's hosted
  Google consent) must cover `min_scopes` → otherwise `403` with
  `missing_scopes` listing the gap (invariant C3b).

When you get the C3b denial, send the user through the normal login
authorize flow with the additional scopes:

```
GET /auth/v1/authorize
    ?client_id=<your client>
    &redirect_uri=<registered redirect_uri>
    &state=<new session id>
    &upstream_scope=<space-delimited missing scopes>
```

Google's incremental consent (`include_granted_scopes=true`) means
already-granted scopes are not re-prompted; on completion the stored
grant has grown and the same broker call succeeds.

Unknown provider → `404`. No stored upstream credential for the user
(user never completed a Google login through Campus) → `404`.

## Auditing

Every release *and* denial emits an audit event
(`campus.broker.release` / `campus.broker.deny`) recording the client,
user, provider, and requested scopes — never token values (invariant
C4). Apps should assume broker usage is visible to admins, by design.

## Rules for downstream apps (invariant D)

These are the conditions of using the bridge; they are the contract
campus-classroom signs up to when it retires its own token management:

- **D1 — No persistence.** Hold the released access token in memory
  only, until `expires_in`. Do not write it to disk, a database, or
  long-lived session storage. Do not cache it past expiry.
- **D2 — Treat it as a secret.** Never log it, never put it in URLs,
  never echo it to a browser that does not need it.

Revocation semantics (invariant C5): revoking your campus token (or a
user logging out) ends *your app's* access, including bridge access,
but does not touch the user's Google link with Campus. Deleting the
upstream link itself is a separate, explicit admin/user action.

## Migration note for campus-classroom

The app-owned flow (own `GOOGLE_CLIENT_ID/SECRET`, Flask-session token
storage) is replaced by: campus login (already via Campus) → broker
call inside `with_classroom_session()`. No caller changes; the token
source swaps from local session storage to
`POST /auth/v1/broker/google/` with `min_scopes` set to the Classroom
scopes the request needs.
