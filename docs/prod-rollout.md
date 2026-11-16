# Production rollout — per-integration upstream OAuth clients

Runbook for the last open lane of the per-integration upstream OAuth work
(nyjc-computing/campus#733; design and decisions in #730). Everything below
is **user-gated**: it stands up new production services, creates Google
Workspace (GCP Internal) clients, and mutates production data.

## Current state (2026-11-16 standup)

The production environment was stood up on 2026-11-16 (prep for the
`weekly` → `main` merge):

- **Fleet live and green**: campus.auth, campus.api, campus.audit,
  campus-gateway (+ their per-service databases). All `/health`
  endpoints return 200 and gateway dispatch is verified
  (`/api/openapi.json`, `/integrations/v1/`, `/audit/v1/`).
- **Topology**: a fresh `production` environment duplicated from
  development; the July-2025 fossil environment was kept as
  `production-legacy` (untouched; retirement is a separate decision).
  Services initially deploy from `weekly` with autodeploy off; the
  branch flip to `main` is the merge-moment cutover (below).
- **Databases**: per-service postgres x3 + mongodb x2 with fresh
  credentials; volumes attached. Prod blocks `init_from_model`, so
  tables were created by one-off `ENV=development` init runs and the
  auth migration ledger stamped (see the mirror in
  [migration-protocol.md](migration-protocol.md)). Migration 011
  (calendar) was applied to **campus.api's postgres** — where
  `campus.api` reads it (dev parity) — not the auth DB the runner
  runs in; the ledger records it in the auth DB either way.
- **Seeded**: `guest` public client; confidential clients
  `campus-api-production` (api service credential) and
  `campus-admin-production` (operator, `AUTH_OPERATOR_CLIENT_IDS`);
  vault records `campus.yapper`/`YAPPERDB_URI` (yapper role + database
  created in the auth postgres) and `campus.api`/`campus.auth`
  `SECRET_KEY`s; vault access grants for both clients; audit operator
  API key (auto-seeded at audit startup from
  `AUDIT_OPERATOR_API_KEY`).
- **Gateway**: nginx path-dispatch, same template as dev (private
  upstreams); domain `campus-gateway-production.up.railway.app`
  (port 8080). The audit/gateway domains claimed their clean names;
  auth/api were globally taken and carry Railway's random suffix
  (`campusauth-production-25f09d8e`, `campusapi-production-feab0369`).
- **Bucket**: `campus-api-bucket-prod` (sin) with literal
  `BUCKET_*` credentials on campus.api (dev pattern).
- **Known gap — mongodb**: the two mongo volumes initialized with
  Railway-generated root passwords that predate the credential vars
  (volume-attach race during standup). The wipe+reinit is
  user-gated (volume deletion is dashboard-only): see
  "Remaining user-gated steps" below. Until then every
  mongo-backed flow (login sessions, device codes, tokens, timetable
  entries, circles members, hosted apps) fails at the DB.

### Remaining user-gated steps

1. **Mongo credential repair** (blocking): delete the
   `campus.auth-mongodb-volume-*` and `campus.api-mongodb-volume-*`
   volumes of the production environment in the Railway dashboard,
   then redeploy both mongo services — fresh volumes re-run initdb
   with the `MONGO_INITDB_ROOT_*` variables already set.
2. **GCP trio** (Workspace console, Internal classification):
   `campus` (identity login) and `campus-classroom` clients, redirect
   URIs per the dev pattern with the prod origins. Seed the matching
   `google` / `google.classroom` vault labels in prod auth.
3. **campus-admin production** (consumer repo): needs the operator
   client secret — rotate `campus-admin-production`'s secret via the
   credentials API when wiring it (the standup-only secret was
   discarded). `AUDIT_ADMINS` for the audit UI lives on the
   campus-admin portal, not campus.audit.
4. **Legacy cleanup** (optional, non-blocking): retire
   `production-legacy` (fossil campus.api/vault + "Campus DB") and
   the CRASHED staging `campus.vault`; decide on the
   `*.campus.nyjc.app` custom domains (currently attached to the
   legacy instances).
5. **Weekly → main merge**: see "Cutover" below.

## Cutover: merging weekly → main

The production instances currently deploy from `weekly` with
autodeploy **off** (so weekly pushes touch only dev). At the merge:

1. Merge `weekly` into `main` (CI runs on the PR; keep the three
   devcontainer-only commits that only exist on `main`).
2. Flip each production instance's source branch `weekly` → `main`
   (service settings → Deploy → branch, for campus.auth, campus.api,
   campus.audit, campus-gateway) and re-enable autodeploy.
3. The merge commit's push to `main` then deploys the fleet. Watch
   the deploy queue; a first-boot WARN naming pending migrations
   means a new migration needs the manual runbook above.
4. Smoke: gateway `/health`, `/api/openapi.json`,
   `/integrations/v1/`, `/audit/v1/health`, direct auth `/health`.

## Runbook (order matters)

1. **Stand up prod `campus.auth`** (plus `campus.auth-postgres`, and Mongo
   if used) in the Railway production environment. Mirror the dev service's
   variables (`railway variables --service campus.auth --json`), with
   `ENV=production` and the prod `PUBLIC_URL`.

   > **Database topology caution (2026-10-27 dev lesson):** create each
   > database as its own real deployment and point each service's URI var
   > at *that service's* private endpoint — never attach a database
   > *reference* to another service's instance. Dev's `campus.auth-mongodb`
   > had been a reference into `campus.api-mongodb`, silently running auth
   > and api on one shared mongod until the endpoint regularization
   > (mongo:8.3.13) surfaced it. When mirroring dev variables, take the
   > endpoint from the owning service's `RAILWAY_PRIVATE_DOMAIN`, and
   > rotate each database's root password independently after standup.

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

   Also configure the **files object-storage credentials** as
   `campus.api` environment variables (keys `BUCKET_NAME`,
   `BUCKET_ENDPOINT`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`,
   `BUCKET_REGION`): create a prod Railway storage bucket, then set each
   variable as an internal reference to the bucket's own variables
   (dev pattern, 2026-10-30 — e.g.
   `BUCKET_NAME=${{"campus.api-bucket".BUCKET}}`; note the bucket's
   S3-name variable is `BUCKET`, and service names with dots need
   quoting in references). Environment variables are resolved before
   the deployment vault, so no vault seeding is needed. Production
   `ENV` forces the Railway bucket backend for
   `campus.storage.get_bucket`, so every file operation fails with a
   missing-credential `OSError` until these variables exist.

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
