# Auth Token & Scope Invariants

Security and behavioral invariants for the Campus token and scope system,
written ahead of implementation so every phase builds against the same
contract. Part of the credential-management work tracked in issue #705.

**Why this exists.** Downstream apps in the Campus ecosystem (first- and
second-party, e.g. campus-classroom) must be able to call non-Campus APIs
(Google Classroom, etc.) on behalf of a signed-in user **without ever
storing the user's non-Campus tokens**. Campus is the custodian: it holds
the upstream credentials, grows their scopes through user consent, and
releases short-lived access tokens on demand. Platform developers are
expected to be students without the resources to manage OAuth tokens
safely; the safe path must be the default path.

Each invariant has an ID used in tests, PR descriptions, and code
comments. The status table at the bottom is re-checked and updated in
every phase PR.

## Provider taxonomy

Campus currently has four token providers, in two mechanically different
families. Invariants are tagged accordingly; full parity between the
families is **not** a goal.

| Provider | Family | Role |
|----------|--------|------|
| `campus` | first-party | Campus's own OAuth 2.0 authorization server: authorization-code, device-code (RFC 8628), and refresh grants issuing Campus bearer tokens |
| `google` | third-party | OAuth proxy: browser login/consent with Google, custody of upstream credentials |
| `github` | third-party | OAuth proxy (same shape as google) |
| `discord` | third-party | OAuth proxy (same shape as google) |

## Invariants

### A — Campus-token scope algebra `[campus]` (phase P1)

- **A1 — Fail-closed scope allowlist.** A Campus token may only carry
  scopes that are within the requesting client's registered
  `allowed_scopes`. A client with a missing or empty allowlist can be
  granted no scopes. Scope names outside the allowlist are rejected with
  `invalid_scope`, never silently dropped.
- **A2 — No silent widening.** Growing a grant requires a fresh
  authorization-code flow through the browser. The refresh grant
  reissues exactly the granted scopes; it never widens them.
- **A3 — Stale-token safety.** A token returned for an authorization
  must cover every scope of that authorization. If the existing
  user-client token does not, a new token with the union of (existing
  grant, requested scopes) is issued and the old token record is
  superseded — never return a narrower token for a wider request.
- **A4 — Grant accumulation.** The credential row for
  `(provider=campus, user, client)` is the grant record. Re-consent
  unions the newly consented scopes into it (Google-style incremental
  authorization semantics); scopes are never revoked by re-consent, only
  by explicit revocation or admin action.
- **A5 — Supersession is deletion.** When a token record is replaced,
  the superseded record is deleted from storage (#678 behavior), so a
  rotated or superseded refresh token cannot be replayed.
- **A6 — Enforcement at the boundary.** Scope validation happens when a
  session is created (an authenticated server-to-server call) and is
  re-checked at `/authorize` and at the device-authorization submission.
  The session API cannot be used to smuggle scopes past the allowlist.
- **A7 — Device flow uses the same algebra.** Device codes (RFC 8628)
  carry scopes validated against the client allowlist at
  `device_authorize`; token issuance from an approved device code
  follows A3/A4 like any other grant.

### B — Upstream credential custody `[upstream]` (phase P2)

- **B1 — Campus is the sole holder.** Upstream access and refresh tokens
  live only in Campus storage, keyed `(provider, user, client=Campus's
  own upstream client id)`. No Campus API writes third-party-provider
  tokens supplied by apps (the `provider == "campus"` assertion on token
  issuance stands).
- **B2 — Refresh tokens never leave.** No HTTP response, log line, audit
  event, or error payload ever contains an upstream refresh token (or
  any upstream token value beyond the access token explicitly released
  by the bridge, per C2).
- **B3 — Upstream scope growth is browser-only.** Extra upstream scopes
  (e.g. Google Classroom) are requested by redirecting the user through
  the provider's consent screen — Google incremental authorization
  (`include_granted_scopes=true`) unions the granted scopes into the
  stored credential. Requestable upstream scopes are capped by a
  per-client upstream allowlist, vetted at client registration.
- **B4 — Workspace restriction.** Upstream logins remain bound to the
  configured workspace domain (existing `WORKSPACE_DOMAIN` check).
- **B5 — User-scoped reads.** Upstream credentials are readable only per
  `(provider, user)`; no endpoint exposes tokens across users.

### C — Token bridge `[bridge]` (phase P3)

- **C1 — Authorized release only.** Upstream access tokens are released
  exclusively by the bridge endpoint, and only when all of the
  following hold: the caller presents a valid Campus bearer token for
  the user; the caller is a **confidential** client; and that client is
  flagged for bridge access (fail-closed default). Public clients
  (SPAs, CLIs, mobile) are never eligible.
- **C2 — Minimal exposure.** A bridge response carries the upstream
  access token, its expiry, and its scope — nothing else. Refresh
  tokens and provider-specific fields (e.g. `id_token`) never appear.
- **C3 — Scope ceiling.** A release must satisfy the scope minimum the
  caller declares, and is capped at (scopes granted by the user on the
  upstream link) ∩ (the client's registered upstream allowlist). A
  release that would exceed either is denied with a machine-readable
  error that points the app at the re-consent URL.
- **C4 — Audited.** Every bridge release *and* denial emits an audit
  event recording (client, user, provider, requested/granted scopes).
  Token values are never included in audit payloads.
- **C5 — Explicit revocation semantics.** Revoking a Campus token
  revokes that app's access, including bridge access, but not the
  user's upstream link itself. Destroying the upstream link is a
  separate, explicit action. Both are documented and tested; neither is
  implied by the other.

### D — Downstream client contract `[client]` (phase P3)

Enforced by review and audit deterrence rather than technically — stated
here so apps can be held to it and so campus-classroom's switchover has
a contract to sign up to.

- **D1 — No persistence.** Downstream apps hold Campus and upstream
  tokens in memory only, until expiry. No tokens on disk, in databases,
  or in long-lived session storage.
- **D2 — Treat tokens as secrets.** Bearer credentials and bridge
  responses are never logged, embedded in URLs, or echoed to browsers
  beyond the flow that needs them.

## Enforcement status

Re-checked at the end of every phase; updated in the phase's PR.

| ID | Phase | Status | Where enforced / tested |
|----|-------|--------|--------------------------|
| A1 | P1 | planned | client model + session/device validation |
| A2 | P1 | planned | refresh grant (`routes/oauth.py`) |
| A3 | P1 | planned | `provider.token` issuance path |
| A4 | P1 | planned | `provider.token` issuance path |
| A5 | P1 | preserved | `credentials.update()` (existing #678) |
| A6 | P1 | planned | `POST /sessions/{provider}/`, `/authorize` |
| A7 | P1 | planned | `device_authorize` / device grant |
| B1 | P2 | preserved | `credentials.new()` assertion |
| B2 | P2 | planned | proxy code paths + doc audit |
| B3 | P2 | planned | google proxy `scopes` param + allowlist |
| B4 | P2 | preserved | `WORKSPACE_DOMAIN` checks |
| B5 | P2 | preserved | credentials resource keying |
| C1 | P3 | planned | bridge endpoint guards |
| C2 | P3 | planned | bridge response shape |
| C3 | P3 | planned | bridge scope check |
| C4 | P3 | planned | bridge audit emissions |
| C5 | P3 | planned | docs + contract tests |
| D1 | P3 | documented | this doc; classroom switchover contract |
| D2 | P3 | documented | this doc |

## Verification protocol

- Every phase PR runs the full CI chain (`ci.yml`: ruff → sanity/type →
  unit → contract → integration). The contract suite is a blocking gate;
  any expectation change is deliberate and cited in the PR.
- New tests reference invariant IDs (e.g. "A3: stale token never
  returned for wider request") in docstrings so coverage is traceable.
- The status table above is updated in the same PR that implements or
  preserves each invariant, with the test or code location filled in.
