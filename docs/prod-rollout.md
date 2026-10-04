# Production rollout — per-integration upstream OAuth clients

Runbook for the last open lane of the per-integration upstream OAuth work
(nyjc-computing/campus#733; design and decisions in #730). Everything below
is **user-gated**: it stands up new production services, creates Google
Workspace (GCP Internal) clients, and mutates production data.

## Current state (2026-10-03)

- The dev lane of #733 is complete: the integrations registry, connect
  flow, broker integration routes, the `/auth/v1/connections/` inventory +
  disconnect, and the full `upstream_scope` retirement are live on Railway
  dev and verified.
- **Production has no `campus.auth` service at all** (survey 2026-09-29;
  every row of the migration mirror in [migration-protocol.md](migration-protocol.md)
  reads "not stood up"). Step 1 below is therefore the real first step,
  not a formality.
- Production-style environments block `init_from_model`, so **every schema
  change is manual** per the
  [migration runbook](migration-protocol.md#staging--production-style-environments-manual-runbook).
  As of #747, a prod boot whose ledger shows outstanding migrations logs a
  startup WARNING naming them, so a deploy that skipped this runbook is
  visible in the deployment logs.

## Runbook (order matters)

1. **Stand up prod `campus.auth`** (plus `campus.auth-postgres`, and Mongo
   if used) in the Railway production environment. Mirror the dev service's
   variables (`railway variables --service campus.auth --json`), with
   `ENV=production` and the prod `PUBLIC_URL`.

2. **Apply migrations**: `railway ssh -s campus.auth -e production` →
   `python migrations/runner.py apply` — runs every pending revision in
   order and records each outcome in the ledger. Expected pending: 003–009;
   001/002 record as historical (their target tables predate the current
   service topology). Verify with `python migrations/runner.py status`,
   then update the mirror table in [migration-protocol.md](migration-protocol.md).

3. **Seed vault labels** via `scripts/seed_integration.py
   --base-url <prod-url>` (supports `--dry-run`): `google` (identity —
   the prod `campus` GCP client) and `google.classroom` (the prod
   `campus-classroom` GCP client). `google.calendar` stays a registry
   stub — no vault label until a consumer exists.

4. **GCP trio (Workspace console; Internal classification)**: `campus`
   (identity login), `campus-classroom`, and `campus-calendar` (only when
   that consumer exists). Redirect URIs follow the dev pattern — the
   classroom vault client needs
   `<prod-auth>/auth/v1/google/classroom/callback`; the identity client's
   callback is as registered on the dev `campus` GCP client with the prod
   origin (see [auth-login-flow.md](auth-login-flow.md)).

5. **Prod client allowlists**: PATCH each prod consumer client with
   `upstream_scopes: {"google.classroom": [<9 classroom scopes +
   userinfo.email + userinfo.profile>]}` and `token_bridge: true` — copy
   the verbatim value from dev's `uid-client-ef56f01c`, which carries ONLY
   the `google.classroom` key (the `google` key is retired; prod jumps
   straight to the end-state). The credentials API is campus-only (basic
   auth, invariant B1) — never expose it to consumer apps.

6. **Consumer prod deploys** (campus-classroom, campus-profile) ride their
   own repos' prod lanes, after prod `campus.auth` is live.

7. **Close out**: tick the prod box in #733 and update the migration
   mirror; #733 can then close.

## References

- [migration-protocol.md](migration-protocol.md) — migration runner, prod
  manual runbook, applied-migrations ledger and mirror
- [auth-login-flow.md](auth-login-flow.md) — login + integration connect
  flows
- [token-broker.md](token-broker.md) — broker routes and allowlist
  semantics
- [campus-api-schema.md](campus-api-schema.md) — provider naming grammar,
  envelope rules
