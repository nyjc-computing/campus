# Production deployment playbook

Operational playbook for standing up and updating services in the Railway
**production** environment — the deployment sequence, the credentials map,
and the traps that have actually bitten (each with its root cause, so the
fix survives personnel changes).

> **Maintenance rule**: this document encodes the audit / authentication /
> authorization flows as they are wired today. Any change to those flows —
> new invariants in `docs/auth-token-invariants.md`, new client types, new
> vault labels, changes to the circles model — must update the matching
> section here in the same PR. The speedbump catalog (§7) is append-only:
> add every new trap you hit, with its root cause.

Project: `campus` (`76e0b6d0-0832-41dc-841f-e3bc758d3eca`).
Environments: `development` (weekly, autodeploys) and `production`
(`d5221f3b`). `staging` and the July-2025 fossil `production-legacy`
were deleted on 2026-11-17 — two environments only.

Railway API/CLI recipes and their sharpest edges live in the
`railway-ops` skill (`.zcode/skills/railway-ops/SKILL.md`); this document
is the playbook — what to do, in what order, and why.

## 1. Environment model (read first)

- A **service is a project-global entity** (name unique per project) with
  one **instance per environment**. Instance-scoped: source branch,
  variables, domains, volumes, deploy settings. Entity-scoped: name, repo.
  Renaming an entity renames it in **both** environments' canvases.
- **Naming convention**: suffix-less = prod. Services shared across
  environments keep the suffix-less name (it *is* the prod name). Services
  exclusive to dev carry `-dev` (`campus.auth-mongodb-dev`,
  `campus.api-mongodb-dev`, `campus.api-bucket-dev`, the consumer repos'
  dev deployments once their prod ghosts are removed). Volumes follow:
  `*-dev-volume` vs plain.
- **Prod instances track `main` (cutover executed 2026-11-16/17)** —
  campus.auth/api/audit/gateway deploy only on main pushes; weekly
  pushes touch dev alone. Note for cutover mechanics: a per-instance
  branch flip is dashboard-only (the API's `ServiceSourceInput` has no
  branch field, and `serviceConnect` is entity-level — it would move
  dev too). After a branch flip lands on a stale base, the first
  deploy is SKIPPED; force it with `deploymentRedeploy` of the ACTIVE
  deployment once the base is current.
- **Private endpoints are pinned per instance** (`campus-auth`,
  `auth-mongodb`, `postgres-94e0`, …). Renaming a service does **not**
  move its endpoint; two environments share endpoint *names* but not
  networks. Verify with `railway private-network status -s <svc> -e <env>`;
  rename with `railway private-network update … <short-name>`.
- **Public domains are pinned per instance** too. Renaming a service does
  not reassign its domain. Prod domains today: `campusauth.up.railway.app`,
  `campusapi.up.railway.app`, `campusaudit.up.railway.app`,
  `nyjc-campus.up.railway.app` (gateway; the clean `campus.up` and
  `campus-gateway.up` names were globally claimed and Railway silently
  appends random suffixes on conflict — always re-list domains after a
  rename).
- The master admin account is **`campus-admin@nyjc.edu.sg`**
  (`AUTH_SUPER_ADMIN` bypass on auth, `campus-admin` circle member,
  all `<resource>.admin` role circles, `AUDIT_ADMINS` on the admin
  portal).

## 2. Credentials map

| Credential | Lives in | How minted / rotated |
|---|---|---|
| Campus OAuth client rows | auth postgres `vault_clients` (name, redirect_uris, allowed_scopes, upstream_scopes, token_bridge, `secret_hash`) | direct row insert (HMAC via `secret.hash_client_secret(secret, key=auth SECRET_KEY)`) or the credentials API; client ids via `uid.generate_category_uid("client", 8)` |
| Client secrets (plaintext) | `CLIENT_SECRET` var on the consuming service's prod instance | generated once at mint (`secret.generate_client_secret()`); only the hash is stored — **losing the plaintext means rotating** |
| Operator wiring | `AUTH_OPERATOR_CLIENT_IDS` on prod auth (literal) | points at `campus-admin-production` (`uid-client-6ec13381`). **Intentionally a literal**, not the dev-style `${{campus-admin.CLIENT_ID}}` reference — prod's campus-admin instance carries the *dev* client id until that repo deploys to prod |
| `SECRET_KEY` (auth) | env var on prod auth **and** vault row `campus.auth/SECRET_KEY` (same value; env wins via `getsecret` precedence) | `token_urlsafe(48)`; HMAC key for client-secret hashing — rotating it invalidates every stored client secret hash |
| `SECRET_KEY` (api, audit, admin, classroom, apphost, profile, nyxchange) | `SECRET_KEY` env var per service (+ vault row `campus.api/SECRET_KEY`) | fresh `token_urlsafe(48)` per service |
| Postgres passwords | `POSTGRESDB_URI` on the consuming app (prod), `DATABASE_URL`/`POSTGRES_PASSWORD` on the DB service | `databasePasswordReset` mutation (`databaseType: "postgres"`). **Trap**: the response's `newPassword` is the real password; the `DATABASE_URL` it writes is **wrong** — after rotating, fix `DATABASE_URL`/`PGPASSWORD` vars to the truth *before* anything references them |
| Mongo credentials | `MONGO_INITDB_ROOT_USERNAME/PASSWORD` on the DB service (init-time only) + `MONGODB_URI` on consuming apps | initdb runs once on first boot of an empty volume — **credentials must exist at service creation**, not patched in after |
| Bucket keys | `BUCKET_*` on prod campus.api as references `${{campus.api-bucket.*}}` | `railway bucket credentials --bucket campus.api-bucket -e production`; bucket instances are per-environment (same entity, per-env keys) |
| Audit producer keys (`traces:write`) | `AUDIT_API_KEY` on each producer | minted via `POST /audit/v1/apikeys/` with the operator key bearer; response field `api_key` is the plaintext (shown once) |
| Audit UI key (`traces:read`, `apikeys:read`, `apikeys:write`) | `AUDIT_UI_API_KEY` on the admin portal | same mint route, name `campus-admin audit UI` |
| Audit operator key | `AUDIT_OPERATOR_API_KEY` on prod audit | auto-seeded at audit startup into the audit DB (`uid-apikey-operator-0000`); rotate = delete row + new env value + redeploy |
| Google identity / classroom | vault labels `google/CLIENT_ID,CLIENT_SECRET` and `google.classroom/CLIENT_ID,CLIENT_SECRET,SCOPES,CONNECT_TARGETS` | GCP console (user) + `scripts/seed_integration.py` (classroom; needs a vault-write client) / direct insert (identity) |
| GitHub / Discord OAuth apps | vault labels `github/CLIENT_ID,CLIENT_SECRET`, `discord/…` (seeded 2026-11-16 via the admin vaults UI) | user creates the OAuth apps; callbacks `https://campusauth.up.railway.app/auth/v1/{github,discord}/callback`. **Requires #1114's fix** — the proxies built authorize URLs from `env.CLIENT_ID` instead of the vault credentials; verify redirects carry the app ids after any proxy change |
| Yapper DB | vault `campus.yapper/YAPPERDB_URI` — a `yapper` role + database **inside the auth postgres**; yapper's tables self-create (raw DDL, not env-blocked) | create role+database in auth postgres, then the vault row |

Why literals vs references: DB/bucket/domain wiring uses **Railway
references** (`${{…}}`) where possible — they self-heal on rotation
(the auth-postgres password rotation incident proved literals rot).
Credentials that reference *other environments' state* (the operator
client id) stay literals. Client secrets are env vars by design — the
auth DB stores only HMAC hashes.

## 3. Deploying a NEW service to prod (staggered sequence)

Do these in order; each phase depends on the previous. "Blocked" items
are user-gated and called out.

### Phase 1 — data stores
1. Create the DB service **with credentials in the creation payload**
   (`serviceCreate(variables=…)` / `railway add --variables …`).
   *Why*: a volume attach on a fresh DB service triggers its first boot;
   if credentials land after that boot, the datadir initializes with
   generated passwords and the fix is painful (postgres needs
   `databasePasswordReset` — trust `newPassword`, its `DATABASE_URL`
   output lies — mongo needs full recreation; volumes are
   dashboard-delete-only). The traps + recovery paths are in the
   railway-ops skill, "Database bootstrap ordering" (#1105).
2. Attach the volume (`volumeCreate`, mount path per image) and set the
   start command (mongo: `docker-entrypoint.sh mongod --ipv6 --bind_ip
   ::,0.0.0.0 --setParameter diagnosticDataCollectionEnabled=false`).
3. Rename the private endpoint to the convention short-name if the
   default derivation doesn't match (`railway private-network update`).
4. Deploy, wait SUCCESS, then verify connectivity through a temporary
   `railway tcp-proxy create` (ping/auth with the intended credentials:
   `psql "$DATABASE_URL" -c 'select 1;'` / `mongosh "$MONGODB_URI"
   --eval 'db.runCommand({ping: 1})'`) — **delete the proxy
   afterwards**. Do not wire app URIs until this passes.

### Phase 2 — schema bootstrap (prod blocks `init_from_model`)
1. Run the service's storage init one-off with `ENV=development` for
   the *process only*: `ENV=development python
   scripts/init_storage.py --service <svc>` (the consolidated
   per-service entry point, #1103 — each target is the same idempotent
   init the service's startup self-heal runs, routed through
   `campus.bootstrap.run_init_storage`; the audit crash (#1100) is
   what happens when a service boots without this being understood).
   Reach the DB via `railway ssh` into the service or a temporary tcp
   proxy (**delete the proxy afterwards**).
2. Stamp the migration ledger per service DB (#1104): each migration
   declares `TARGET_DB` (auth|api|audit), every runner command takes
   `--db`, and the ledger read/written is the context's
   `POSTGRESDB_URI` — run `railway ssh -s campus.<svc>`, then
   `python migrations/runner.py --db <svc> ensure` +
   `stamp`/`apply` (api baseline: 001/002 `--as historical` + stamp
   011; audit baseline: stamp 003). Resolving a revision that targets
   another DB errors with the right `--db` instead of silently writing
   the wrong ledger (the trap that put 011 in the auth DB on
   2026-11-16). See docs/migration-protocol.md.
3. Seed bootstrap data: circles graph (see §5), vault labels the
   service reads, vault access grants for its client.

### Phase 3 — app service
1. Create the service instance (new entity for a genuinely new service;
   prod entities for cross-env services can't be re-materialized after
   instance deletion — see §7.6).
2. Set **all** variables with `skipDeploys` before any deploy. Minimum
   set per service: `DEPLOY`, `ENV=production`, `PUBLIC_URL`
   (`https://${{RAILWAY_PUBLIC_DOMAIN}}`), `HOSTNAME`
   (`${{RAILWAY_PUBLIC_DOMAIN}}`), `BASE_URL` (gateway origin),
   DB URIs as references (`${{"campus.auth-postgres".DATABASE_URL}}`
   — **quoted** service names; unquoted dotted names resolve empty),
   audit keys, client credentials.
3. Start command binds `[::]` (mesh is IPv6-only). Healthcheck path
   `/health` when the app implements it (most prod services don't yet,
   #1107).
4. Deploy. **Verify a non-SKIPPED deployment row appears** — see §7.4.

### Phase 4 — auth wiring
1. Mint the service's campus client (vault_clients row + HMAC secret
   under auth's `SECRET_KEY`), set `CLIENT_ID`/`CLIENT_SECRET` on the
   service, and add vault access grants it needs (mirror the dev
   client's grants; bits: 1 = read, 15 = full).
2. Browser-login consumers: set `redirect_uris` to their prod
   `…/finalize_login` (+ `http://localhost:5000/finalize_login` where
   dev has it). Token-bridge consumers (classroom): copy
   `upstream_scopes` + `token_bridge` verbatim from the dev client and
   add the `campus.yapper` read grant.
3. `AUTH_SUPER_ADMIN` / `AUTH_OPERATOR_CLIENT_IDS` / `AUDIT_ADMINS`
   are deployment-policy decisions (see §1 and §5) — not per-service.

### Phase 5 — login + audit wiring
1. Verify `/auth/v1/oauth/device_authorize` issues codes (exercises
   client lookup, mongo write, yapper) and `/auth/v1/google/authorize`
   redirects with the right client (needs the GCP client + vault label).
2. If the service emits traces: mint its `traces:write` producer key
   and set `AUDIT_API_KEY`. If it views traces (admin portal): mint the
   `traces:read` + `apikeys:read`+`write` UI key.
3. Full verification sweep: gateway `/health`, service `/health`s,
   `/api/openapi.json`, `/integrations/v1/`, one authenticated flow.

### Blocked / user-gated steps (current)
- **campus-profile and nyxchange-timetable-v2**: their `main` branches
  are stale releases (profile: pre-wheel-pin era with a git dependency
  on campus `weekly`; nyxchange: June 2026). Owners merge `dev` →
  `main`, then the prod instances (fully wired — clients, vars, audit
  key) deploy with one trigger.

## 4. Updating EXISTING services

1. Code changes ride **weekly** → autodeploy touches prod too (see §1).
   After a merge, poll the prod deployment row for the service and
   confirm it is not SKIPPED (§7.4).
2. Variable changes: `variableUpsert(skipDeploys: true)` for the batch,
   then ONE redeploy (`deploymentRedeploy` of the ACTIVE deployment —
   the reliable trigger). Prefer references over literals so future
   rotations don't need app redeploys.
3. Credential rotations: rotate → fix the *authoritative* var → fix
   everything that copied it → redeploy consumers. After a postgres
   `databasePasswordReset`, immediately correct `DATABASE_URL`/`PGPASSWORD`
   (they lie) — then any `${{…DATABASE_URL}}` references resolve true.
4. Domain changes: `serviceDomainUpdate` then update every var that
   embeds the domain, then redeploy those services. Client
   `redirect_uris` that embed the domain need a DB/API update too.

## 5. Bootstrap data on prod (what exists and why)

- **Circles** (api mongo `campus_api.circles`): meta doc + root circle
  `nyjc.edu.sg` → 7 resource circles (`circles`, `timetable`,
  `assignments`, `bookings`, `submissions`, `subjcombi`, `venues`),
  each with an `.admin` role circle whose member is
  `campus-admin@nyjc.edu.sg: 15`; the `campus-admin` circle (admin
  portal gate) also carries the master account; the meta doc points at
  the root. Members are keyed by **email string** (not uid). New
  resources add their pair on dev at startup — prod needs the manual
  pair (`python scripts/init_storage.py --service api` runs the same
  bootstrap, #1103).
- **Vault labels**: `campus.api/SECRET_KEY`, `campus.auth/SECRET_KEY`,
  `campus.yapper/YAPPERDB_URI`, `google/*`, `google.classroom/*`
  (SCOPES = canonical 9; CONNECT_TARGETS = profile-prod +
  classroom-prod). Vault access grants: api client `bits=1` on
  campus.api / campus.yapper / google / smtp; admin client `bits=15` on
  campus / google; classroom client `bits=1` on campus.yapper.
- **Clients**: guest (public), campus-auth-production,
  campus-api-production, campus-admin-production (operator),
  campus-classroom-production (token_bridge + upstream_scopes verbatim
  from dev), campus-profile-production, nyxchange-timetable-production.
  campus-apphost shares classroom-production's client.
- **Audit keys**: operator (auto-seeded), campus-admin tracing +
  campus-admin audit UI + classroom-tracing + profile-tracing (minted
  2026-11-16 via the audit API — mint requests require `owner_id`).
- **A10 amendment (#1110, 2026-11-16)**: the login-session
  re-acquisition route allows the operator **when it owns the session**
  — required because the admin portal doubles as operator and session
  owner; the previous unconditional operator bar 403'd every gated
  admin view on both environments. If the authz model changes again,
  re-check §2's operator row and this paragraph together.

## 6. Release flow (weekly → main) — cutover executed 2026-11-16/17

All four campus-suite prod instances now track `main`; a main push is
what deploys prod. Future releases:

1. PR `weekly` → `main` (CI runs on the PR).
2. Merge needs `--admin`: main's branch policy blocks normal merges
   even with every check green (#1115). Run `gh pr merge --merge
   --admin` once CI is green.
3. If main was reconciled into weekly directly (push), update the PR
   branch first (`gh pr update-branch`) or the policy will refuse
   again.
4. Prod auto-deploys the merge on all four instances; smoke: gateway
   `/health`, `/api/openapi.json`, `/integrations/v1/`,
   `/audit/v1/health`, auth `/health`, one device-flow + one browser
   login.

Executed-cutover notes (2026-11-16/17): the branch flips happened
*before* the merge, so Railway SKIPPED the stale-main deploys and kept
serving weekly content (a36eb258 — code-identical to main tip modulo a
docs commit). The release merge itself hit real conflicts
(devcontainer/gitignore/workflow, main's informal upstream commits vs
weekly) — resolved locally with `git merge -X theirs` in a worktree,
pushed straight to `main`, then `main` was reconciled back into
`weekly` (`merge -X ours`) so the next release PR stayed mergeable.
The now-merged devcontainer configuration was removed from both
branches (#1116/#1117) per the "main is old, discardable" ruling.

## 7. Speedbump catalog (append-only)

1. **Volume-attach race**: attaching a volume to a fresh DB service
   triggers its first boot; credentials landing after that are ignored
   (datadir initialized). Postgres recovery: `databasePasswordReset`;
   mongo: no reset — recreate the service. Prevention: credentials in
   the creation payload, before anything can boot.
2. **`databasePasswordReset` lies**: response `newPassword` is the real
   password; the `DATABASE_URL`/vars it writes are not. Fix them
   manually after rotating.
3. **No cross-env instance creation**: a service entity's instance
   cannot be (re-)added to another environment by API/CLI
   (`serviceCreate` refuses existing names; `serviceConnect` is
   entity-level). Cross-env splits: rename the dev entity (private
   endpoints/domains are pinned and unaffected), create a new entity in
   the target env, rename its private endpoint.
4. **SKIPPED deploy trap**: `serviceInstanceDeploy` can return true
   while the deployment row goes SKIPPED and nothing deploys; later
   triggers keep no-oping. Recovery: `deploymentRedeploy(id of the
   ACTIVE SUCCESS deployment, usePreviousImageTag:false)` — on SKIPPED
   rows it fails "without a snapshot"; on CRASHED rows it works.
5. **Prod boots block `init_from_model`**: unguarded `init_storage()`
   at startup = crash loop (#1100). Startup init goes through
   `campus.bootstrap.run_init_storage` (the guard + loud-failure
   convention stated once, #1103); fresh prod DBs need the one-off
   `ENV=development python scripts/init_storage.py --service <svc>` +
   ledger stamps.
6. **Ghost instances**: environment duplication copies every service
   (with dev variables); deleting a referenced service cascade-redeploys
   referrers and can silently START ghosts (classroom + apphost did
   exactly this). Instance removal is dashboard-only.
7. **Reference syntax**: dotted service names must be quoted —
   `${{"campus.auth-postgres".DATABASE_URL}}`; unquoted resolves empty
   (psycopg falls back to a unix socket — bizarre 500s).
   `${{RAILWAY_PUBLIC_DOMAIN}}` is the bare domain: `PUBLIC_URL` needs
   `https://` prefixed.
8. **Domain name conflicts are silent**: `serviceDomainUpdate` returns
   true while suffixing the name (or not applying it). Re-list domains
   after every rename. `*.up.railway.app` resolves at the edge for
   never-created names (`x-railway-fallback` 404 "Application not
   found") — a resolving hostname proves nothing.
9. **Mongo dotted keys**: `$set` with a dotted field path nests
   (`members."a@b.edu.sg"` → nested maps). Replace the whole document
   field instead.
10. **Network**: SSH (port 22) is blocked from the office network —
    use `railway tcp-proxy create/delete` for DB access (always delete
    after). Private mesh is IPv6-only: listeners bind `[::]`.
11. **Permission-refused operations** (workspace role): serviceDelete,
    volumeDelete, volume deletion on service deletion — dashboard-only.
12. **Windows/CLI traps**: `railway` cannot spawn from Windows-Python
    subprocess; `--kv` output can carry `\r` that poisons JSON and
    file-based loops (strip it); keep GraphQL mutation `.gql` files
    alive until every dependent call ran (a missing file silently
    no-ops the call).
13. **Required env vars fail lazily** (#1108): auth needs
    `CLIENT_ID`/`CLIENT_SECRET` (yapper), api needs them at boot (SDK).
    Removing a "seemingly unused" var can break a flow hours later —
    check the required-vars matrix before trimming.
14. **Migration ledgers are per service DB** (fixed #1104): every
    migration declares `TARGET_DB`; run the runner in that service's
    context with `--db <svc>`, and stamp each DB's ledger baseline at
    bootstrap (phase 2). The auth ledger still carries pre-#1104 rows
    for api/audit revisions — residue that `--db auth` skips, not
    drift.
15. **OpenAPI drift is version-coupled**: bumping the suite version
    drifts *every* committed artifact — regenerate all three services'
    `docs/openapi.json` on any spec-affecting change.

## 8. Current state (2026-11-17) and open items

Live on prod (all tracking `main`): campus.auth, campus.api,
campus.audit, campus-gateway, campus-admin (vaults view working),
campus-classroom, campus-apphost (+ 5 DBs, bucket). Sign-in paths live:
Google (identity + classroom callback registered), GitHub, Discord.

Waiting on their repos: campus-profile, nyxchange-timetable-v2 (stale
`main` branches — instances fully wired, one deploy trigger each after
release). Left offline: oauth-proxy (retired candidate, zero vars).

Open work items: #1106 (SKIPPED deploy), #1107 (healthchecks + alerting — most prod
services have no `/health` healthcheck configured and deploy-failure
alerting is off), #1108 (lazy env-var failures), #1109 (ghost
instances — largely superseded: classroom/apphost are intentional now;
the remainder is the oauth-proxy decision).

## References

- `docs/auth-token-invariants.md` — the invariants this playbook wires
  around (A10 amended by #1110).
- `docs/migration-protocol.md` — migration runner + mirror table
  (prod column = 2026-11-16 baseline).
- `docs/circles-access-control.md` — circles model.
- `docs/auth-login-flow.md` — browser login chain.
- `.zcode/skills/railway-ops/SKILL.md` — CLI/GraphQL recipes.
