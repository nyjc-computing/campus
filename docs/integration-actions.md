# Integration action proxies (#1221)

Admin-authorized endpoints that perform an upstream-provider verb on a
**target user's** stored integration credential — the custodial
complement to the token broker. The broker hands the *calling user*
their own credential; action proxies let a designated administrator
drive the user-bound upstream actions (e.g. Classroom `turnIn`)
without the provider's token ever crossing a service boundary
(campus#1221 custody decision: integration provider tokens are
internal to campus.auth and are never released to any caller here).

## Endpoint family

```
/auth/v1/integrations/{base_provider}/{integration}/users/{user_id}/{action}
```

Allowlisted actions (anything else answers 404 — no path passthrough):

| Action | Method | Body | Upstream verb (scope) |
|---|---|---|---|
| `turn-in` | POST | `{course_id, coursework_id[, submission_id]}` | `studentSubmissions:turnIn` (`classroom.coursework.me`) |
| `reclaim` | POST | `{course_id, coursework_id[, submission_id]}` | `studentSubmissions:reclaim` (`classroom.coursework.me`) |
| `modify-attachments` | POST | `{course_id, coursework_id, submission_id, attachments: [{link: {url}}]}` | `studentSubmissions:modifyAttachments` (`classroom.coursework.me`) |
| `submission` (read) | GET | `?course_id=&coursework_id=[&submission_id=]` | `studentSubmissions.get/list` (`classroom.coursework.me`) |

Behavior notes:

- `submission_id` may be omitted on `turn-in`/`reclaim`/`submission`;
  the target user's own studentSubmission is resolved via
  `studentSubmissions.list?userId=me` (the released credential IS the
  target user's).
- `turn-in` no-ops with `"already": true` when the submission is
  already `TURNED_IN`; `reclaim` treats Google's
  `FAILED_PRECONDITION` (nothing to reclaim) as success.
- Responses carry action outcomes and Classroom resource metadata —
  never token material (invariant B2/C2).

## Authorization

`authz.require_integration_action(provider, action)` composes two
independent authorities; both are required for a user principal
(either alone confers nothing, like every management vocabulary):

1. **Capability (#865)**: the caller's campus token carries the
   per-integration management scope
   `integrations.<provider>:admin`
   (e.g. `integrations.google.classroom:admin`). Who can hold it is
   curated by the operator through the minting client's
   `allowed_scopes`; token minting validates the ask against that
   allowlist. Request it at login:
   `campus auth login --scope "integrations.google.classroom:admin ..."`.
2. **Custody (#883/#889)**: vault access to the integration's vault
   label (`google.classroom`) — a per-label grant row and the
   `vaults:*` token scope, via `require_vault_permission`.

The operator client and the super-admin root bypass; any other client
principal is denied — proxies mutate user-bound upstream state and
must stay user-attributable (#881). For a designated administrator the
bootstrap is therefore:

1. (operator) add `integrations.google.classroom:admin` (and
   `vaults:read` if not already carried) to the minting client's
   `allowed_scopes`;
2. (operator) ensure the administrator holds a vault grant row on the
   `google.classroom` label;
3. (admin) re-login requesting the scope(s).

## Credential handling (custody invariants)

`integration_actions.credentials.load_released_credential` mirrors the
broker's release flow without ever emitting the token: load the stored
credential for the integration's own OAuth client, silently refresh
server-side (B2: the refresh token never leaves), and fail closed with
`403` + `missing_scopes` unless the stored grant covers every scope
the action needs (C3b, consent-bounded — a pre-widening grant answers
403 and the reconnect hint; the proxy never mints or widens). A
missing credential is `404` with the connect-flow hint. The C3a
caller-allowlist checks have no analogue here because required scopes
are server-defined constants per action, not caller-supplied asks.

## Audit

Every proxied call emits `campus.integrations.action` (success) or
`campus.integrations.action_fail` (any failure after authorization,
including credential denials) carrying actor principal, target
`user_id`, integration, action, and ids — never token values.
Journey context rides the standard `X-Journey-ID` adoption.
