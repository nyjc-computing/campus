# Token Bridge — upstream access tokens on demand

The token bridge is how Campus-ecosystem apps (first- and
second-party, e.g. campus-classroom) call non-Campus APIs — Google
Classroom, and later other proxied providers — **on behalf of a
signed-in user, without ever storing the user's non-Campus tokens**.

Campus is the sole custodian of upstream credentials **and of the
upstream OAuth clients themselves**: each first-party integration has
its own upstream client (its own vault label, its own registered
Google client), so a token issued for one integration can never touch
another (#733). Campus holds the access *and refresh* tokens obtained
through its OAuth proxies, grows each integration's grant through its
hosted connect flow (see
[auth-login-flow.md](auth-login-flow.md), *Integration connect
flows*), and releases only short-lived access tokens on demand.
Platform developers are not expected to manage OAuth tokens at all.

Contract invariants: [auth-token-invariants.md](auth-token-invariants.md)
groups B (custody), C (bridge), D (downstream client contract).

## The endpoints

```
POST /auth/v1/broker/{provider}                        ← identity provider
POST /auth/v1/broker/{provider}/{integration}/          ← first-party integration
Authorization: Bearer <campus access token for the user>
Content-Type: application/json

{"min_scopes": ["https://www.googleapis.com/auth/classroom.rosters"]}
```

- `provider` — `google` for the identity client (github/discord follow
  the same shape once needed). Integrations use the two-segment form,
  e.g. `google/classroom`; the single-segment namespaced form
  (`google.classroom`) is not part of the surface and is refused with
  a pointer at the canonical route.
- `integration` — slug from the in-code registry; enumerate what is
  available (and connectable) via `GET /integrations/v1/`.
- `min_scopes` (optional) — upstream scopes the caller requires for
  the call it is about to make.

Success — `200` (same shape on both routes; `provider` is the
namespaced string on the integration route):

```json
{
  "provider": "google.classroom",
  "user_id": "user@nyjc.edu.sg",
  "access_token": "ya29....",
  "token_type": "Bearer",
  "expires_in": 1234,
  "scope": "email profile https://www.googleapis.com/auth/classroom.courses.readonly"
}
```

That is the entire payload: access token, expiry, scope. **No refresh
token is ever included** — Campus refreshes silently from its stored
credential when the upstream token has expired, so the value you
receive is always live. Use it in memory until `expires_in`, then ask
again; asking again is cheap (Campus-side refresh happens at most once
per upstream token lifetime, using the integration's own client).

## Who may call

Fail-closed — all of the following must hold
(invariant C1; denials are 403):

1. The request carries a **campus Bearer token bound to the user**
   (client-credentials/basic auth has no user and is denied).
2. The client that token was issued to is **confidential** (has a
   secret; browser/SPA/CLI public clients are never eligible).
3. That client is flagged **`token_bridge: true`** at registration
   (`POST /auth/v1/clients/` or `PATCH /auth/v1/clients/{id}/`,
   admin-reviewed).

The same guards apply to both routes. Apps that only host the connect
UX (e.g. campus-profile) hold **no** `upstream_scopes` entries and no
bridge flag — by design.

## Scope rules

- **Identity route** — `min_scopes` must be within the client's
  registered `upstream_scopes[provider]` allowlist → otherwise `400`
  `AUTH_INVALID_SCOPE` (invariant C3a). Non-identity asks on this
  route are deprecated (warned + audited) and slated for refusal.
- **Integration route** — the client's `upstream_scopes` must carry a
  **non-empty entry for the namespaced provider** (e.g.
  `"google.classroom": [...]`), **even when `min_scopes` is omitted**:
  an integration token inherently carries integration scopes, so an
  absent key denies outright (`400 AUTH_INVALID_SCOPE`, invariant
  C3a). Per-app integration allowlists are the app-side half of the
  blast-radius story: the vault cap is the other half.
- **Integration vault cap** — `min_scopes` are additionally capped by
  the integration's registered scope set (vault `SCOPES`); asking
  beyond it is a configuration error, not a re-consent situation
  (`400` listing the disallowed scopes).
- The user's actual upstream grant must cover `min_scopes` →
  otherwise `403` with `missing_scopes` listing the gap (invariant
  C3b).

Re-covering a `missing_scopes` gap:

- **Integration routes**: send the user through the integration's
  **connect flow** (from the app's integrations page, or directly
  `GET /auth/v1/google/<integration>/authorize?target=<your
  callback>`). Consent is forced, so the stored grant always grows to
  the integration's full cap. Never point users at the login
  `upstream_scope` path — integration scopes are not obtainable at
  login.
- **Identity route**: send the user through the normal login
  authorize flow with `upstream_scope` set to the missing *identity*
  scopes (deprecated mechanism, reserved for hypothetical
  identity-client growth):

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

Unknown provider/integration, an unconfigured integration (registry
stub with no vault client), or no stored credential for the user
→ `404`; the integration route's missing-credential hint points at
the connect flow.

## Connections — status + disconnect

Apps embed the connect UX and need to show it; the metadata surfaces
for that (invariant B1: the credentials HTTP API itself stays
campus-only):

- `GET /auth/v1/connections/` — the user's upstream connections:
  `{"connections": [{provider, integration, scopes, connected_at,
  expires_at}]}`. Campus bearer = self; basic auth + `user_id` =
  delegated (the server-mode pattern campus-profile uses). No token
  values, ever (C2).
- `DELETE /auth/v1/connections/google/classroom/` (or
  `/connections/{provider}/` for an identity provider) — explicit
  disconnect: deletes the stored credential rows and their token
  records, emits `campus.integrations.disconnect` (no token values).
  The next connect re-consents from scratch.

Disconnecting the upstream link is distinct from revoking a campus
token (C5): logout kills an app's bridge access but leaves the
connection; disconnect leaves all campus logins alone.

## Auditing

Every release *and* denial emits an audit event
(`campus.broker.release` / `campus.broker.deny`) recording the client,
user, provider (`integration` too, on integration routes), and
requested scopes — never token values (invariant C4). Connect flows
emit `campus.integrations.connect` / `connect_fail`; disconnects emit
`campus.integrations.disconnect`. Apps should assume bridge and
connection usage is visible to admins, by design.

## Rules for downstream apps (invariant D)

These are the conditions of using the bridge; they are the contract
campus-classroom signs up to:

- **D1 — No persistence.** Hold the released access token in memory
  only, until `expires_in`. Do not write it to disk, a database, or
  long-lived session storage. Do not cache it past expiry.
- **D2 — Treat it as a secret.** Never log it, never put it in URLs,
  never echo it to a browser that does not need it.

## The integration app pattern (campus-classroom)

First-party integration apps do not run their own OAuth flows and do
not hold `GOOGLE_CLIENT_ID/SECRET`:

1. **Connect** — the user clicks Connect on the app's card on the
   campus-profile integrations page (or the app links to the same
   `authorize_path` from `GET /integrations/v1/`). campus.auth runs
   the consent flow, binds the credential to the signed-in user, and
   stores it under the namespaced provider.
2. **Consume** — inside the app's session seam, release the token via
   `POST /auth/v1/broker/google/<integration>/` with `min_scopes` for
   the call about to be made. No caller changes; the token source is
   the broker, not local storage.
3. **Recover** — `404` (no credential) and `403` + `missing_scopes`
   both remediate through the integrations page connect flow.
