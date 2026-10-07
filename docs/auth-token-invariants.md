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

Campus has four base token providers, in two mechanically different
families, plus **namespaced integration providers** (#733) that extend
a third-party base with per-integration upstream OAuth clients.
Invariants are tagged accordingly; full parity between the families is
**not** a goal.

| Provider | Family | Role |
|----------|--------|------|
| `campus` | first-party | Campus's own OAuth 2.0 authorization server: authorization-code, client_credentials (RFC 6749 §4.4; confidential clients only, no user identity, no refresh token), device-code (RFC 8628), and refresh grants issuing Campus bearer tokens |
| `google` | third-party | OAuth proxy: browser login/consent with Google, custody of upstream credentials |
| `github` | third-party | OAuth proxy (same shape as google) |
| `discord` | third-party | OAuth proxy (same shape as google) |
| `google.<integration>` (e.g. `google.classroom`) | third-party, namespaced | a first-party integration backed by its **own** upstream OAuth client: separate consent (connect flow), separate credential rows, separate blast radius — login/identity paths are untouched |

Integration providers are declared in the in-code registry
(`campus/auth/integrations.py`, published read-only at
`GET /integrations/v1/`, #688); their upstream client credentials and
scope caps live in vault labels mirroring the provider string.

Note on client_credentials: the grant is userless by design — the
client itself is the resource owner, so the resulting bearer resolves
(via `/root/authenticate`) to the client with no user. Its scopes
follow A1 (validated against the client's registered allowlist; an
absent `scope` parameter defaults to the full allowlist), and its
single live token per client follows A5 supersession semantics when
replaced (`AppCredentialsResource.issue`).

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
  issuance stands). Campus is likewise the **sole custodian of the
  per-integration upstream clients** (#733): each integration's OAuth
  client id/secret/scope cap live in its vault label, never in
  downstream apps.
- **B2 — Refresh tokens never leave.** No HTTP response, log line, audit
  event, or error payload ever contains an upstream refresh token (or
  any upstream token value beyond the access token explicitly released
  by the bridge, per C2).
- **B3 — Upstream scope growth is browser-only.** Extra upstream scopes
  are requested by redirecting the user through a consent screen.
  Identity scopes grow through the login flow's Google incremental
  authorization (`include_granted_scopes=true`), capped by the
  per-client upstream allowlist vetted at registration. **Integration
  scopes grow only through the integration's connect flow** (#733:
  campus session required, target allowlisted against the
  integration's `CONNECT_TARGETS`, `prompt=consent` forced, ask capped
  at the integration's registered scope set) — never at login: the
  login-time `upstream_scope` parameter has been **removed** (#733
  Phase 2 retirement); requests carrying it fail validation with 422.
- **B4 — Workspace restriction.** Upstream logins remain bound to the
  configured workspace domain (existing `WORKSPACE_DOMAIN` check).
- **B5 — User-scoped reads.** Upstream credentials are readable only per
  `(provider, user)`; no endpoint exposes tokens across users.
- **B6 — The integration scope cap is a reviewed contract.** An
  integration's vault `SCOPES` value is the single cap behind three
  surfaces at once: the connect flow's consent ask, the broker's
  release-time scope gate, and the public catalog (`GET
  /integrations/v1/`). Consumers build feature gates on it —
  campus-classroom enforces `classroom.coursework.students` locally
  against the released grant for its Send-to-Classroom flow — so
  **changing a `SCOPES` value is an intentional, reviewed act**, not a
  deployment detail: keep the catalog endpoint the machine-readable
  source of truth, re-verify with at least one consumer after a change,
  and never narrow below what a shipped consumer feature requires
  without a coordinated plan. Silent drift below the documented set
  breaks consumer features for freshly connected accounts while existing
  grants keep working (observed live: campus#850 — the dev cap lost
  `classroom.coursework.students`, ungrantable by any fresh connect
  until restored; the missing write authorization that let the cap be
  rewritten by an unprivileged client is fixed by campus#854's
  management-authorization gate).

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
  error. **C3a is keyed by the (possibly namespaced) provider string**,
  and for integration providers a **non-empty allowlist entry is
  required even when no `min_scopes` are declared** — an absent key
  denies outright, fail-closed (an integration token inherently carries
  integration scopes, so there are no "base scopes" to fall back on).
  Integration releases are additionally capped by the integration's
  vault scope set. Denials on integration routes point at the connect
  flow for re-consent, never at a login-time growth path (login never
  carries upstream scopes).
- **C4 — Audited.** Every bridge release *and* denial emits an audit
  event recording (client, user, provider, requested/granted scopes;
  integration releases add the integration slug). Connect and
  disconnect flows emit `campus.integrations.*` events. Token values
  are never included in audit payloads.
- **C5 — Explicit revocation semantics.** Revoking a Campus token
  revokes that app's access, including bridge access, but not the
  user's upstream link itself. Destroying the upstream link is a
  separate, explicit action — the connections API
  (`DELETE /auth/v1/connections/...`, #733), which deletes the stored
  credential and token records and audits
  `campus.integrations.disconnect`. Both are documented and tested;
  neither is implied by the other.

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
| A1 | P1 | **enforced** | `campus/auth/scopes.py::validate_for_client`; `POST /clients/`, `PATCH /clients/{id}/`; `tests/contract/auth/test_scope_algebra.py` |
| A2 | P1 | **enforced** | refresh grant reissues granted scopes (`routes/oauth.py::_handle_refresh_token_grant`); reuse path in `provider.token` never shrinks a grant; `test_token_issuance.py::test_narrower_reauth_reuses_covering_token` |
| A3 | P1 | **enforced** | `provider.token` coverage check; `test_token_issuance.py::test_exchange_issues_session_scopes`, `::test_wider_reauth_unions_scopes` |
| A4 | P1 | **enforced** | `provider.token` union issuance; `test_token_issuance.py::test_wider_reauth_unions_scopes` |
| A5 | P1 | **enforced** | `provider.token` issues via `credentials.update()` (deletes superseded record, #678); `test_token_issuance.py::test_superseded_token_stops_authenticating` |
| A6 | P1 | **enforced** | `routes/sessions.py::_validated_campus_scopes` + `provider.authorize` scope-param check; `test_scope_algebra.py::test_authorize_scope_*` |
| A7 | P1 | **enforced** | `routes/oauth.py::device_authorize` + device grant re-check; `test_scope_algebra.py::test_device_authorize_respects_allowlist` |
| B1 | P2/P3 | **enforced** | `credentials.new()` provider assertion + credentials API refuses non-campus providers (`routes/credentials.py::_reject_non_campus_provider`); `test_token_broker.py::test_credentials_api_refuses_third_party_provider`. Integration clients custody: vault labels + in-code registry (`campus/auth/integrations.py`, #733) |
| B2 | P2/P3 | **enforced** | credentials API lockdown closes the token-embedding read path; broker responses are built explicitly without refresh tokens; no proxy path returns/logs refresh tokens |
| B3 | P2 | **enforced** | identity growth: `provider.authorize` upstream allowlist gate + google proxy scope merge; `tests/contract/auth/test_upstream_scopes.py`; release-time re-check in C3. Integration growth: connect flow guards (`routes/oauth_proxy/google` authorize + `oauth_proxy/google/proxy.py::_validate_connect_binding`, `prompt=consent` forced); `tests/contract/auth/test_integrations.py` |
| B4 | P2 | **preserved** | `WORKSPACE_DOMAIN` checks in `google/proxy.py::handle_auth_callback`, `provider.verify_login` |
| B5 | P2/P3 | **enforced** | credentials resource keying `(provider, user, client)`; broker releases keyed to the bearer token's own user |
| B6 | P3 | **enforced** | this invariant + the catalog endpoint (`routes/integrations.py`, `GET /integrations/v1/`); consumer-side gates (campus-classroom `CLASSROOM_SCOPES_SEND`) verify the cap end-to-end; vault write-path authorization is the operator/vault_access gate (`campus/auth/authz.py`, #854; `tests/contract/auth/test_management_authorization.py`) |
| C1 | P3 | **enforced** | `routes/broker.py::_authorize_bridge_call` (bearer user + confidential + token_bridge flag, fail-closed); `test_token_broker.py` unflagged/public/basic/missing-credential cases |
| C2 | P3 | **enforced** | broker response built explicitly (access token, expiry, scope only); `test_token_broker.py::test_release_returns_minimal_upstream_token` |
| C3 | P3 | **enforced** | `validate_upstream_for_client` (C3a, keyed by the provider string) + integration absent-key-deny (`routes/broker.py`, both routes) + stored-grant coverage check (C3b) with machine-readable `missing_scopes`; `test_token_broker.py::test_min_scopes_*`, `test_integrations.py` broker cases, `test_connections.py::TestBrokerNamespacedGuardContract` |
| C4 | P3 | **enforced** | `campus.broker.release` / `campus.broker.deny` emissions on every path; `campus.integrations.connect/connect_fail/disconnect` on the connect/disconnect flows; payloads carry scopes, never token values |
| C5 | P3 | **enforced** | campus-token revocation (`/oauth/revoke`) vs upstream-link disconnect (`/auth/v1/connections/`, `routes/connections.py` refuses `provider=campus` with 403) separated and tested; `test_connections.py` |
| D1 | P3 | **documented** | docs/token-broker.md (classroom switchover contract); enforced by review + audit deterrence |
| D2 | P3 | **documented** | docs/token-broker.md |

Additional P1 note: the authorization-code exchange now also binds the
code to the issuing client (RFC 6749 §4.1.3; was previously unchecked)
and mints a refresh token for confidential clients, matching the
documented response contract in `docs/auth-login-flow.md`.

## Verification protocol

- Every phase PR runs the full CI chain (`ci.yml`: ruff → sanity/type →
  unit → contract → integration). The contract suite is a blocking gate;
  any expectation change is deliberate and cited in the PR.
- New tests reference invariant IDs (e.g. "A3: stale token never
  returned for wider request") in docstrings so coverage is traceable.
- The status table above is updated in the same PR that implements or
  preserves each invariant, with the test or code location filled in.
