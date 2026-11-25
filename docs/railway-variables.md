# Railway environment variables

Inventory of every user-set environment variable in the campus Railway
environments, classified by how its value is maintained:

- **Template** — value contains `${{…}}` references. Railway resolves them at
  deploy time from other variables, other services, or the shared layer; they
  self-update when the source changes and need no manual maintenance.
- **Literal** — value stored verbatim; must be set and rotated by hand. Each
  entry notes what owns it and whether any reference source exists.
- **Railway-provided** — injected or derived by Railway itself; never user-set,
  never editable.

Secrets are shown as `<secret>`; this file intentionally contains no secret
material. OAuth client IDs (`uid-client-…`) are public identifiers and are
shown as-is.

> **Scope: both environments.** The `development` section is the primary
> inventory. Production is superadmin-only
> ([environment-access-policy.md](environment-access-policy.md)) — audit and
> change it only from a sanctioned superadmin session, using the same recipe;
> its inventory follows in [Production](#production-environment-superadmin-sessions).
> The retired `staging` / `production-legacy` environments were deleted
> 2026-11-17 (campus#1122).
>
> **Snapshots: 2026-11-17**, taken immediately after the fleet-wide templating
> passes of the same date (see [History](#history)).

## Auditing live state

The plain CLI view **renders templates before display**, so a reference looks
identical to a literal there — never audit with it. The stored values
(including templates) come from the unrendered GraphQL query:

```bash
# STORED values — source of truth for this document (one call per service):
railway api 'query($e:String!,$p:String!,$s:String!){ variables(environmentId:$e, projectId:$p, serviceId:$s, unrendered:true) }' \
  --var e=<environmentId> --var p=<projectId> --var s=<serviceId>
# Omit --var s for the shared (environment-level) layer.

# RENDERED view — what a deployment actually receives (verification only):
railway variables -s <service> -e development --kv
```

Writing values — gotchas (details in the `.zcode/skills/railway-ops` skill):

- Dot-named targets **must** be quoted when written:
  `${{"campus.auth-postgres".DATABASE_URL}}`. Unquoted dot-names resolve
  **silently to empty** at deploy time.
- Railway **normalizes on save**: quotes are stripped from references it
  resolves in the service namespace (`${{"campus-admin".CLIENT_ID}}` stores as
  `${{campus-admin.CLIENT_ID}}`), while bucket and dot-named references keep
  their quotes. Both forms resolve correctly; quoting is only load-bearing for
  dot-names.
- Inline `railway api` strings need the inner quotes GraphQL-escaped:
  `value:"${{\"svc\".VAR}}"`.
- Prefer `railway variable set 'KEY=value' --skip-deploys` (or
  `variableUpsert(input:{…, skipDeploys:true})`) for batched edits, then one
  redeploy wave via `scripts/railway_deploy.sh <svc> development`.

## Development environment

Environment `e954f5fa-1195-41af-b737-b5732028331b`; weekly autodeploys here.
Public domains carry the `-development` suffix; the gateway is
`campus-development.up.railway.app`. Mongo services are named
`campus.<svc>-mongodb-dev`.

### Shared variables (environment-level)

Referenced as `${{shared.<NAME>}}`. Set once, consumed by many services — the
preferred home for any value used by more than one service.

| Variable | Stored value | Kind | Consumed by |
|---|---|---|---|
| `AUDIT_API_KEY` | `<secret>` (`audit_v1_…`) | literal — campus.audit-issued producer key shared by auth+api | campus.auth, campus.api |
| `BASE_URL` | `https://campus-development.up.railway.app` | literal — the gateway's public URL | 8 app services (all but the gateway itself) |
| `EMBED_TOKEN_SECRET` | `<secret>` | literal — signing secret shared by the embed pair | campus-classroom, campus-apphost |
| `ENV` | `development` | literal — runtime environment flag | all 8 app services (not the gateway) |
| `PYTHON_VERSION` | `3.12` | literal — build pin | campus.auth, campus.api, campus.audit, campus-admin, campus-profile, nyxchange-timetable-v2 |
| `RAILPACK_PYTHON_VERSION` | `3.12` | literal — build pin | same six services |
| `WORKSPACE_DOMAIN` | `nyjc.edu.sg` | literal | campus.auth |
| `CAMPUS_TEST_STAFF_USERNAME` | `campus-test-staff@nyjc.edu.sg` | literal — test accounts (#767), need-to-share; never in CI | manual testing |
| `CAMPUS_TEST_STAFF_PASSWORD` | `<secret>` | literal | manual testing |
| `CAMPUS_TEST_STUDENT_USERNAME` | `campus-test-student@nyjc.edu.sg` | literal | manual testing |
| `CAMPUS_TEST_STUDENT_PASSWORD` | `<secret>` | literal | manual testing |

### Railway-provided variables (never user-set)

Injected into every deployment; avoid shadowing these names (user-set values
would override them):

- Networking: `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_PRIVATE_DOMAIN`
- Project/env/service metadata: `RAILWAY_PROJECT_NAME`, `RAILWAY_PROJECT_ID`,
  `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID`,
  `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_SERVICE_NAME`, `RAILWAY_SERVICE_ID`,
  `RAILWAY_STATIC_URL`
- Deployment/replica identity (fresh values per boot; probed 2026-11-24,
  #1239): `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_REPLICA_ID` (present even with a
  single replica), `RAILWAY_REPLICA_INCARNATION` (== the container hostname,
  `rep-<deployment8>-<uid>-<index>-<n>`), `RAILWAY_REPLICA_REGION`,
  `RAILWAY_SNAPSHOT_ID`; GitHub-triggered deploys also get
  `RAILWAY_GIT_COMMIT_SHA` / `RAILWAY_GIT_BRANCH` / `RAILWAY_GIT_AUTHOR` /
  `RAILWAY_GIT_REPO_NAME` / `RAILWAY_GIT_REPO_OWNER` / `RAILWAY_GIT_COMMIT_MESSAGE`.
  **No variable exposes the instance count** — count unique AAAA records for
  `$RAILWAY_PRIVATE_DOMAIN` from inside the deployment, or query GraphQL
  `deployment(id){ instances { id status } }` from outside (instance `id` ==
  `RAILWAY_REPLICA_ID`); see the railway-ops skill.
- Cross-service domain copies: `RAILWAY_SERVICE_<OTHER_SERVICE>_*_URL` —
  derived from every other service's public domain in the environment;
  Railway manages these (deleting a domain cascade-deletes its copies and
  redeploys the holders)
- Database services additionally: `RAILWAY_VOLUME_NAME`, `RAILWAY_VOLUME_ID`,
  `RAILWAY_VOLUME_MOUNT_PATH`
- `RAILWAY_TCP_PROXY_DOMAIN` / `RAILWAY_TCP_PROXY_PORT` /
  `RAILWAY_TCP_APPLICATION_PORT` — exist only while a TCP proxy is attached.
  **No dev service has one** (both DB proxies were deleted 2026-11-17).

### campus.auth

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_API_KEY` | `${{shared.AUDIT_API_KEY}}` | template | producer key shared with campus.api |
| `AUDIT_TRACING_ENABLED` | `1` | literal | audit span emission flag |
| `AUTH_OPERATOR_CLIENT_IDS` | `${{campus-admin.CLIENT_ID}}` | template | operator gate (#854); stored unquoted by Railway's normalizer |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `CLIENT_ID` | `uid-client-761d9293-f4bf-4e` | literal | auth's own first-party OAuth client (minted by campus.auth; no Railway source) |
| `CLIENT_SECRET` | `<secret>` | literal | pair of `CLIENT_ID`; rotate via campus CLI clients surface |
| `DEPLOY` | `campus.auth` | literal | vault label name (= `RAILWAY_SERVICE_NAME`; `${{RAILWAY_SERVICE_NAME}}` would be equivalent) |
| `ENV` | `${{shared.ENV}}` | template | |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `MONGODB_NAME` | `campus_auth` | literal | database name inside the shared mongo instance |
| `MONGODB_URI` | `${{"campus.auth-mongodb-dev".MONGO_URL}}` | template | dot-named target — quoting load-bearing |
| `POSTGRESDB_URI` | `${{"campus.auth-postgres".DATABASE_URL}}` | template | dot-named target — quoting load-bearing |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |
| `WORKSPACE_DOMAIN` | `${{shared.WORKSPACE_DOMAIN}}` | template | |

### campus.api

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_API_KEY` | `${{shared.AUDIT_API_KEY}}` | template | |
| `AUDIT_TRACING_ENABLED` | `1` | literal | |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `BUCKET_ACCESS_KEY_ID` | `${{"campus.api-bucket".ACCESS_KEY_ID}}` | template | bucket reference (see [Bucket](#bucket)) |
| `BUCKET_ENDPOINT` | `${{"campus.api-bucket".ENDPOINT}}` | template | |
| `BUCKET_NAME` | `${{"campus.api-bucket".BUCKET}}` | template | the bucket's S3 name is exported under the key `BUCKET` |
| `BUCKET_REGION` | `${{"campus.api-bucket".REGION}}` | template | |
| `BUCKET_SECRET_ACCESS_KEY` | `${{"campus.api-bucket".SECRET_ACCESS_KEY}}` | template | |
| `CLIENT_ID` | `uid-client-15b4a4cb-421` | literal | api's first-party OAuth client |
| `CLIENT_SECRET` | `<secret>` | literal | |
| `DEPLOY` | `campus.api` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `MONGODB_NAME` | `campus_api` | literal | |
| `MONGODB_URI` | `${{"campus.api-mongodb-dev".MONGO_URL}}` | template | |
| `POSTGRESDB_URI` | `${{"campus.api-postgres".DATABASE_URL}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |

### campus.audit

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_EVENTS_ENABLED` | `1` | literal | |
| `AUDIT_OPERATOR_API_KEY` | `<secret>` | literal | audit's own operator key (audit_v1_…); no Railway source |
| `AUDIT_UI_URL` | `https://${{campus-admin.RAILWAY_PUBLIC_DOMAIN}}` | template | stored unquoted by normalizer; cross-service link to the admin UI |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `DEPLOY` | `campus.audit` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `POSTGRESDB_URI` | `${{"campus.audit-postgres".DATABASE_URL}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | Flask secret; per-service by design (must differ between services) |

### campus-cleanup (cron job)

The scheduled cleanup deployment (`campus.cleanup`, `Dockerfile.cleanup`). Created on development 2026-11-25 (service id `c86b82af`, hourly cron `0 * * * *`, GitHub trigger `github@weekly` with auto-deploy on, restart NEVER, no domain/healthcheck); production wiring still pending (#1262).
Batch job: no domain, no healthcheck; Railway cron starts it (≥5-minute
minimum cadence, `railway cron run` for one-offs). Setup runbook:
[docs/cleanup-deployment.md](cleanup-deployment.md). Target matrix —
Railway references resolve per environment:

| Variable | Target value | Kind | Notes |
|---|---|---|---|
| `CLEANUP_JOB_AUDIT_POSTGRESDB_URI` | `${{"campus.audit-postgres".DATABASE_URL}}` | template | rate-limit bucket sweep; the `cleanup_runs` ledger home |
| `CLEANUP_JOB_AUTH_POSTGRESDB_URI` | `${{"campus.auth-postgres".DATABASE_URL}}` | template | future auth-scope jobs |
| `CLEANUP_JOB_AUTH_MONGODB_URI` | `${{"campus.auth-mongodb-dev".MONGO_URL}}` (prod: `campus.auth-mongodb`) | template | `auth_sessions` + `device_codes` sweeps |
| `CLEANUP_JOB_AUTH_MONGODB_NAME` | `campus_auth` | literal | the Mongo database name — the backend resolves it separately from the URI (#1262 first-run finding) |
| `DEPLOY` | `campus.cleanup` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |

### campus-gateway

The gateway reads upstreams from Railway-provided `RAILWAY_SERVICE_*_URL`
copies plus these five literals. No shared/templated values.

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `API_PORT` / `AUTH_PORT` / `AUDIT_PORT` | `8080` | literal | internal upstream ports |
| `PORT` | `8080` | literal | public listen port |
| `NGINX_ENTRYPOINT_LOCAL_RESOLVERS` | `1` | literal | mesh resolver wiring (see deploy/gateway/README.md) |

### campus-admin

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_ADMINS` | `campus-test-admin@nyjc.edu.sg` | literal | audit-UI gate (#722) |
| `AUDIT_API_KEY` | `<secret>` | literal | admin's own producer key (distinct from shared.AUDIT_API_KEY) |
| `AUDIT_TRACING_ENABLED` | `1` | literal | |
| `AUDIT_UI_API_KEY` | `<secret>` | literal | key the admin UI uses against campus.audit |
| `AUTH_ADMINS` | `ng_jun_siang@nyjc.edu.sg;campus-admin@nyjc.edu.sg` | literal | admin-UI gate |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `CLIENT_ID` | `uid-client-f293a42a` | literal | admin's OAuth client (referenced by campus.auth's operator gate) |
| `CLIENT_SECRET` | `<secret>` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |
| `GUNICORN_CMD_ARGS` | `--timeout 120 --workers 2 …` | literal | worker tuning |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | |

### campus-classroom

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_API_KEY` | `<secret>` | literal | classroom's own producer key |
| `AUDIT_TRACING_ENABLED` | `1` | literal | |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `CLIENT_ID` | `uid-client-ef56f01c` | literal | shared with campus-apphost (embed pair shares one OAuth client) |
| `CLIENT_SECRET` | `<secret>` | literal | shared with campus-apphost |
| `EMBED_ORIGIN` | `https://${{campus-apphost.RAILWAY_PUBLIC_DOMAIN}}` | template | cross-service; kept in sync by reference |
| `EMBED_TOKEN_SECRET` | `${{shared.EMBED_TOKEN_SECRET}}` | template | |
| `ENV` | `${{shared.ENV}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | |

No `PYTHON_VERSION`/`RAILPACK_PYTHON_VERSION` — railpack default applies.

### campus-apphost

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `CLIENT_ID` | `uid-client-ef56f01c` | literal | shared with campus-classroom |
| `CLIENT_SECRET` | `<secret>` | literal | shared with campus-classroom |
| `EMBED_MODE` | `1` | literal | |
| `EMBED_PARENT_ORIGIN` | `https://${{campus-classroom.RAILWAY_PUBLIC_DOMAIN}}` | template | cross-service |
| `EMBED_TOKEN_SECRET` | `${{shared.EMBED_TOKEN_SECRET}}` | template | |
| `ENV` | `${{shared.ENV}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | |

No `PYTHON_VERSION`/`RAILPACK_PYTHON_VERSION`; no audit vars (apphost does not
emit audit spans).

### campus-profile

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_API_KEY` | `<secret>` | literal | profile's own producer key |
| `AUDIT_TRACING_ENABLED` | `1` | literal | |
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `CLIENT_ID` | `uid-client-f2ca6010` | literal | |
| `CLIENT_SECRET` | `<secret>` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | |

### nyxchange-timetable-v2

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `BASE_URL` | `${{shared.BASE_URL}}` | template | |
| `BUCKET_ACCESS_KEY_ID` | `${{"campus.api-bucket".ACCESS_KEY_ID}}` | template | identical refs to campus.api's — single source for the shared bucket |
| `BUCKET_ENDPOINT` | `${{"campus.api-bucket".ENDPOINT}}` | template | |
| `BUCKET_NAME` | `${{"campus.api-bucket".BUCKET}}` | template | |
| `BUCKET_REGION` | `${{"campus.api-bucket".REGION}}` | template | |
| `BUCKET_SECRET_ACCESS_KEY` | `${{"campus.api-bucket".SECRET_ACCESS_KEY}}` | template | |
| `CLIENT_ID` | `uid-client-cd3ef100-afe` | literal | |
| `CLIENT_SECRET` | `<secret>` | literal | |
| `ENV` | `${{shared.ENV}}` | template | |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | template | |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | template | |
| `SECRET_KEY` | `<secret>` | literal | |

### Databases (Railway-provisioned connect variables)

Railway provisions the connect surface of each database
([postgres](https://docs.railway.com/databases/postgresql),
[mongo](https://docs.railway.com/databases/mongodb)): on postgres
`PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE/DATABASE_URL`; on mongo
`MONGOHOST/MONGOPORT/MONGOUSER/MONGOPASSWORD/MONGO_URL`. The public-URL
variants (`DATABASE_PUBLIC_URL`, `MONGO_PUBLIC_URL`) exist only while Public
Access (a TCP proxy) is enabled — none are set in dev since the proxies were
removed.

All connect variables are stored as **templates composed from the image-init
literals** — rotating a password means changing exactly one literal and every
URL updates through the reference chain.

### Postgres — campus.api-postgres, campus.auth-postgres, campus.audit-postgres

Identical shape on all three; only the secret differs.

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://${{PGUSER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{PGDATABASE}}` | template (chained) | consumed by the owning app via `${{"campus.<svc>-postgres".DATABASE_URL}}` |
| `PGHOST` | `${{RAILWAY_PRIVATE_DOMAIN}}` | template | |
| `PGDATABASE` | `${{POSTGRES_DB}}` | template | |
| `PGUSER` | `${{POSTGRES_USER}}` | template | |
| `PGPASSWORD` | `${{POSTGRES_PASSWORD}}` | template | |
| `PGPORT` | `5432` | literal | |
| `POSTGRES_USER` | `postgres` | literal | image-init |
| `POSTGRES_DB` | `railway` | literal | image-init |
| `POSTGRES_PASSWORD` | `<secret>` | literal | **the one credential to rotate**; set at creation payload (#1105) |
| `PGDATA` | `/var/lib/postgresql/data/pgdata` | literal | image-init |
| `SSL_CERT_DAYS` | `820` | literal | image config |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | `60` | literal | graceful-shutdown buffer |

Postgres rotation trap (railway-ops skill): `databasePasswordReset`'s response
`DATABASE_URL` carries a **wrong** password — trust `newPassword` only, and
update `POSTGRES_PASSWORD` (the refs cascade from there).

### Mongo — campus.api-mongodb-dev, campus.auth-mongodb-dev

Identical shape on both; only the secret differs.

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `MONGO_URL` | `mongodb://${{MONGOUSER}}:${{MONGOPASSWORD}}@${{MONGOHOST}}:${{MONGOPORT}}` | template (chained) | consumed by campus.auth/campus.api via `${{"campus.<svc>-mongodb-dev".MONGO_URL}}` |
| `MONGOHOST` | `${{RAILWAY_PRIVATE_DOMAIN}}` | template | |
| `MONGOUSER` | `${{MONGO_INITDB_ROOT_USERNAME}}` | template | |
| `MONGOPASSWORD` | `${{MONGO_PASSWORD}}` | template | |
| `MONGO_INITDB_ROOT_USERNAME` | `mongo` | literal | image-init |
| `MONGO_INITDB_ROOT_PASSWORD` | `${{MONGO_PASSWORD}}` | template | aligned 2026-11-17; read by the image only when initializing an **empty** datadir |
| `MONGO_PASSWORD` | `<secret>` | literal | **the one credential to rotate**; the credential consumers actually authenticate with |
| `MONGOPORT` | `27017` | literal | |
| `GLIBC_TUNABLES` | `glibc.pthread.rseq=1` | literal | image workaround |

Mongo has no password-reset mutation — recovery means recreating the service
with credentials in the creation payload (railway-ops skill, #1105).

## Bucket

`campus.api-bucket` is not a service — `railway variables -s <bucket>` reports
"not found", but its credentials **are** referenceable. It exports `BUCKET`
(the S3 bucket name), `ENDPOINT`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`,
`REGION`. Consumers must reference these (`${{"campus.api-bucket".…}}` — the
bucket name is dot-named, so quoting is load-bearing).

A Railway bucket has **per-environment instances**: each environment gets its
own S3 bucket name and credential set from the same resource (the dev instance
exports `campus-api-bucket-w7hhgec` in region `sin`; the production instance
exports `campusapi-bucket-pdxxria`, also region `sin`). References resolve
against the environment's own instance — the same template text works in both
environments. Rotation (per environment):

```bash
railway bucket credentials -b campus.api-bucket -e development --reset
railway bucket credentials -b campus.api-bucket -e production --reset   # superadmin
```

the exports update and every `BUCKET_*` reference follows on the next deploy.
Literal copies of bucket credentials rot silently on reset — both
environments are now fully on references (production converted 2026-11-17;
the literals row in docs/prod-rollout.md §2 predates that pass).

`campus-backups-prod` (production-only, created 2026-11-20) is the
**dedicated migration-backup bucket** (#1172 backup durability): its
instances hold only `migrations/<revision>/…` envelopes — no app data —
so restoring after a bad rewrite never depends on an app bucket's
lifecycle. campus.auth/audit reference it as their default `BUCKET_*`;
campus.api reaches it through `MIGRATION_BUCKET_*` overrides on
`migrations/_backup.py` (its default `BUCKET_*` stays the live objects
bucket). Region `sin`, like the rest of the fleet.

## Maintenance rules

1. **Anything consumed by 2+ services belongs in the shared layer**, not
   copied per service.
2. **Cross-service URLs are references, never literals**:
   `https://${{"other-svc".RAILWAY_PUBLIC_DOMAIN}}` (quote dot-named names).
3. **App → database URIs reference the DB service's composed connect variable**
   (`${{"campus.api-postgres".DATABASE_URL}}`), never a hand-built URI.
4. **Per-service secrets stay per-service** (`SECRET_KEY` must differ between
   services); genuinely-shared secrets go into the shared layer.
5. Batch edits with `--skip-deploys`, verify resolution with the unrendered +
   rendered views, then one redeploy wave via `scripts/railway_deploy.sh`.
6. After rotating anything, re-run the audit recipe above and update this
   document in the same PR.

## Accepted literals (deliberate, no reference source)

- `CLIENT_ID` / `CLIENT_SECRET` — minted by campus.auth and stored in its
  database; Railway has nothing to reference.
- `SECRET_KEY` — Flask signing secrets, unique per service by design.
- Audit producer/operator keys (`AUDIT_API_KEY` copies besides the shared one,
  `AUDIT_OPERATOR_API_KEY`, `AUDIT_UI_API_KEY`) — issued by campus.audit's API.
- Allowlists/emails (`AUDIT_ADMINS`, `AUTH_ADMINS`),
  feature flags, ports, `GUNICORN_CMD_ARGS`, image-init literals on DBs,
  test-account credentials (shared layer).
- `DEPLOY` on auth/api/audit — equals `RAILWAY_SERVICE_NAME`;
  `${{RAILWAY_SERVICE_NAME}}` would be equivalent (cosmetic, left literal).

## Production environment (superadmin sessions)

Environment `d5221f3b-b5c9-4d78-ac36-b0cb7b9d0a0e`; deploys from `main` only
(the weekly → main release PR is the sole path). Public domains are
suffix-less (`campusauth.up.railway.app`, gateway `nyjc-campus.up.railway.app`).
Mongo services are named `campus.<svc>-mongodb` (no `-dev` suffix). **Audit
and change only from a sanctioned superadmin session**; variable changes
redeploy the production fleet — batch with `skipDeploys`, verify rendered
values, then a deliberate redeploy wave.

Snapshot 2026-11-17, taken during the production templating pass (same day as
the development pass; the service inventory below reflects post-pass state).

### Shared variables (production environment-level)

| Variable | Stored value | Kind | Consumed by |
|---|---|---|---|
| `AUDIT_API_KEY` | `<secret>` (`audit_v1_…`) | literal — shared producer key | campus.auth, campus.api |
| `BASE_URL` | `https://nyjc-campus.up.railway.app` | literal — the gateway's public URL | 8 app services |
| `EMBED_TOKEN_SECRET` | `<secret>` | literal | campus-classroom, campus-apphost |
| `ENV` | `production` | literal — runtime environment flag | 8 app services (was `development` until 2026-11-17 — see History) |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `3.12` | literal | six app services |
| `WORKSPACE_DOMAIN` | `nyjc.edu.sg` | literal | campus.auth (pre-pass value; service-level refs now) |
| `CAMPUS_TEST_STAFF_USERNAME` / `_PASSWORD` | username literal / `<secret>` | literal | test accounts (#767) |
| `CAMPUS_TEST_STUDENT_USERNAME` / `_PASSWORD` | username literal / `<secret>` | literal | test accounts (#767) |

### Per-service inventory (production)

Template set common to the app services (identical text to development, with
production's own domains):

| Variable | Stored value | On services |
|---|---|---|
| `BASE_URL` | `${{shared.BASE_URL}}` | all 8 apps |
| `ENV` | `${{shared.ENV}}` | all 8 apps |
| `PUBLIC_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | all 8 apps |
| `HOSTNAME` | `${{RAILWAY_PUBLIC_DOMAIN}}` | auth, api, audit, admin, profile, nyxchange |
| `PYTHON_VERSION` / `RAILPACK_PYTHON_VERSION` | `${{shared.…}}` | auth, api, audit, admin, profile, nyxchange |

Service-specific variables:

| Service | Variable | Stored value | Kind | Notes |
|---|---|---|---|---|
| campus.auth | `AUDIT_API_KEY` | `${{shared.AUDIT_API_KEY}}` | template | |
| campus.auth | `AUDIT_TRACING_ENABLED` | `1` | literal | |
| campus.auth | `AUTH_OPERATOR_CLIENT_IDS` | `${{"campus-admin".CLIENT_ID}}` | template | stored unquoted by normalizer |
| campus.auth | `CLIENT_ID` | `uid-client-1a20f4a5` | literal | prod first-party client |
| campus.auth | `CLIENT_SECRET` | `<secret>` | literal | |
| campus.auth | `DEPLOY` | `campus.auth` | literal | vault label |
| campus.auth | `MONGODB_NAME` | `campus_auth` | literal | |
| campus.auth | `MONGODB_URI` | `${{"campus.auth-mongodb".MONGO_URL}}` | template | prod mongo names (no `-dev`) |
| campus.auth | `POSTGRESDB_URI` | `${{"campus.auth-postgres".DATABASE_URL}}` | template | |
| campus.auth | `SECRET_KEY` | `<secret>` | literal | |
| campus.auth | `WORKSPACE_DOMAIN` | `${{shared.WORKSPACE_DOMAIN}}` | template | |
| campus.auth | `AUTH_GRANT_CHECK_CLIENT_IDS` | `uid-client-11098893` | literal | api's prod client (#1172 rollout) |
| campus.auth | `MIGRATIONS_ENFORCED` | `1` | literal | fail-closed boot gate |
| campus.auth | `MIGRATION_BACKUP_BUCKET` | `campus-backups-prod` | literal | dedicated backups bucket |
| campus.auth | `BUCKET_*` (5) | `${{"campus-backups-prod".…}}` | template | default bucket = backups bucket (auth has no app object storage) |
| campus.api | `AUDIT_API_KEY` | `${{shared.AUDIT_API_KEY}}` | template | |
| campus.api | `AUDIT_TRACING_ENABLED` | `1` | literal | |
| campus.api | `BUCKET_*` (5) | `${{"campus.api-bucket".…}}` | template | resolve to the **production** bucket instance (`campusapi-bucket-pdxxria`) |
| campus.api | `CLIENT_ID` | `uid-client-11098893` | literal | |
| campus.api | `CLIENT_SECRET` | `<secret>` | literal | |
| campus.api | `DEPLOY` | `campus.api` | literal | |
| campus.api | `MONGODB_NAME` | `campus_api` | literal | |
| campus.api | `MIGRATIONS_ENFORCED` | `1` | literal | fail-closed boot gate |
| campus.api | `MIGRATION_BACKUP_BUCKET` | `campus-backups-prod` | literal | dedicated backups bucket |
| campus.api | `MIGRATION_BUCKET_*` (5) | `${{"campus-backups-prod".…}}` | template | override creds: default `BUCKET_*` is the live objects bucket |
| campus.api | `MONGODB_URI` | `${{"campus.api-mongodb".MONGO_URL}}` | template | |
| campus.api | `POSTGRESDB_URI` | `${{"campus.api-postgres".DATABASE_URL}}` | template | |
| campus.audit | `AUDIT_EVENTS_ENABLED` | `1` | literal | |
| campus.audit | `AUDIT_OPERATOR_API_KEY` | `<secret>` | literal | |
| campus.audit | `DEPLOY` | `campus.audit` | literal | |
| campus.audit | `POSTGRESDB_URI` | `${{"campus.audit-postgres".DATABASE_URL}}` | template | |
| campus.audit | `MIGRATIONS_ENFORCED` | `1` | literal | fail-closed boot gate |
| campus.audit | `MIGRATION_BACKUP_BUCKET` | `campus-backups-prod` | literal | dedicated backups bucket |
| campus.audit | `BUCKET_*` (5) | `${{"campus-backups-prod".…}}` | template | default bucket = backups bucket (audit has no app object storage) |
| campus.audit | `SECRET_KEY` | `<secret>` | literal | |
| campus-gateway | `API_PORT` / `AUTH_PORT` / `AUDIT_PORT` / `PORT` | `8080` | literal | |
| campus-gateway | `NGINX_ENTRYPOINT_LOCAL_RESOLVERS` | `1` | literal | |
| campus-admin | `AUDIT_ADMINS` | `campus-admin@nyjc.edu.sg` | literal | differs from dev (no test account in prod) |
| campus-admin | `AUDIT_API_KEY` / `AUDIT_UI_API_KEY` | `<secret>` | literal | |
| campus-admin | `AUDIT_TRACING_ENABLED` | `1` | literal | |
| campus-admin | `AUTH_ADMINS` | `ng_jun_siang@nyjc.edu.sg;campus-admin@nyjc.edu.sg` | literal | |
| campus-admin | `CLIENT_ID` | `uid-client-6ec13381` | literal | referenced by auth's operator gate |
| campus-admin | `CLIENT_SECRET` | `<secret>` | literal | |
| campus-admin | `GUNICORN_CMD_ARGS` | `--timeout 120 --workers 2 …` | literal | |
| campus-admin | `SECRET_KEY` | `<secret>` | literal | |
| campus-classroom | `AUDIT_API_KEY` | `<secret>` | literal | own producer key |
| campus-classroom | `AUDIT_TRACING_ENABLED` | `1` | literal | |
| campus-classroom | `CLIENT_ID` | `uid-client-38c9647e` | literal | shared with apphost |
| campus-classroom | `CLIENT_SECRET` | `<secret>` | literal | shared with apphost |
| campus-classroom | `EMBED_ORIGIN` | `https://${{campus-apphost.RAILWAY_PUBLIC_DOMAIN}}` | template | |
| campus-classroom | `EMBED_TOKEN_SECRET` | `${{shared.EMBED_TOKEN_SECRET}}` | template | |
| campus-classroom | `SECRET_KEY` | `<secret>` | literal | |
| campus-apphost | `CLIENT_ID` | `uid-client-38c9647e` | literal | shared with classroom |
| campus-apphost | `CLIENT_SECRET` | `<secret>` | literal | shared with classroom |
| campus-apphost | `EMBED_MODE` | `1` | literal | |
| campus-apphost | `EMBED_PARENT_ORIGIN` | `https://${{campus-classroom.RAILWAY_PUBLIC_DOMAIN}}` | template | |
| campus-apphost | `EMBED_TOKEN_SECRET` | `${{shared.EMBED_TOKEN_SECRET}}` | template | |
| campus-apphost | `SECRET_KEY` | `<secret>` | literal | |
| campus-profile | `AUDIT_API_KEY` | `<secret>` | literal | |
| campus-profile | `AUDIT_TRACING_ENABLED` | `1` | literal | |
| campus-profile | `CLIENT_ID` | `uid-client-25eb4681` | literal | |
| campus-profile | `CLIENT_SECRET` | `<secret>` | literal | |
| campus-profile | `SECRET_KEY` | `<secret>` | literal | |
| nyxchange-timetable-v2 | `BUCKET_*` (5) | `${{"campus.api-bucket".…}}` | template | re-pointed 2026-11-17 from stale dev-bucket literals — instance has no deployment yet; first deploy will read the production bucket correctly |
| nyxchange-timetable-v2 | `CLIENT_ID` | `uid-client-7f581eab` | literal | |
| nyxchange-timetable-v2 | `CLIENT_SECRET` | `<secret>` | literal | |
| nyxchange-timetable-v2 | `SECRET_KEY` | `<secret>` | literal | |

No `PYTHON_VERSION`/`RAILPACK_PYTHON_VERSION` on classroom/apphost (railpack
default). campus.audit has no `AUDIT_UI_URL`, `CLIENT_ID`/`CLIENT_SECRET` in
production (the dev audit's `AUDIT_UI_URL` has no prod counterpart — don't add
one without a code need). campus-profile's `HOSTNAME` is a self-reference.

### Databases (production)

Same canonical shapes as development. Root credential literals differ per
environment — values are `<secret>`; the api-postgres root is the
post-`databasePasswordReset` truth (the `POSTGRES_PASSWORD` literal was
re-rooted onto it in the 2026-11-17 pass), and the audit-postgres root is the
credential its pre-pass template had baked in.

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://${{PGUSER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{PGDATABASE}}` | template | all three postgres DBs |
| `PGHOST` | `${{RAILWAY_PRIVATE_DOMAIN}}` | template | |
| `PGDATABASE` | `${{POSTGRES_DB}}` | template | |
| `PGUSER` | `${{POSTGRES_USER}}` | template | |
| `PGPASSWORD` | `${{POSTGRES_PASSWORD}}` | template | |
| `POSTGRES_PASSWORD` | `<secret>` | literal | the rotation root per DB |
| `POSTGRES_USER` / `POSTGRES_DB` / `PGPORT` / `PGDATA` / `SSL_CERT_DAYS` / `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | `postgres` / `railway` / `5432` / `/var/lib/postgresql/data/pgdata` / `820` / `60` | literal | image config |
| `MONGO_URL` | `mongodb://${{MONGOUSER}}:${{MONGOPASSWORD}}@${{MONGOHOST}}:${{MONGOPORT}}` | template | both mongo DBs |
| `MONGOHOST` | `${{RAILWAY_PRIVATE_DOMAIN}}` | template | |
| `MONGOUSER` | `${{MONGO_INITDB_ROOT_USERNAME}}` | template | |
| `MONGOPASSWORD` | `${{MONGO_INITDB_ROOT_PASSWORD}}` | template | |
| `MONGO_INITDB_ROOT_USERNAME` | `mongo` | literal | |
| `MONGO_INITDB_ROOT_PASSWORD` | `<secret>` | literal | the rotation root per mongo |

No TCP proxies and no `*_PUBLIC_URL` variables exist on production databases
(the ghost TCP-proxy variable and dead `DATABASE_PUBLIC_URL` on the postgres
services were removed in the 2026-11-17 pass). Consumers reference
`${{"campus.auth-mongodb".MONGO_URL}}`-style templates; the `-dev` suffix is
absent from production service names.

## History

- **2026-10-30** — first reference wiring on dev (audit/auth/api DB URIs,
  bucket creds via #1020's renamed `campus.api-bucket`, self-domain refs).
- **2026-11-16/17** — the DB recreations and prod-standup work regressed parts
  of that wiring to literals and left the two DB TCP proxies attached.
- **2026-11-17 (development pass)** — full templating pass: shared layer
  created (`BASE_URL`, `AUDIT_API_KEY`, `EMBED_TOKEN_SECRET`), every
  cross-service URL and DB URI on references, DB connect variables recomposed
  from their built-in definitions, ghost/dead vars deleted, both TCP proxies
  removed. campus-profile and nyxchange-timetable-v2 have the new config
  stored; their running deployments carry identical values, with the new
  templates materializing on their next successful build (their repos had a
  pre-existing poetry.lock drift failure that day).
- **2026-11-17 (production pass, superadmin session)** — production matched to
  the development pattern: shared layer created and `shared.ENV` corrected
  `development → production` (a landmine: the prod shared layer had been
  seeded with the development value while services carried `ENV=production`
  literals), all app services converted to shared/self/cross-service
  references, both bucket consumers moved to bucket references (nyxchange's
  had pointed at the **development** bucket instance — a latent bug on the
  never-deployed instance), the three postgres services recomposed to the
  canonical shape (api-postgres and audit-postgres `POSTGRES_PASSWORD`
  re-rooted onto their true credentials), ghost/dead vars removed. All
  rendered values verified byte-identical except the intentional heals; seven
  apps redeployed SUCCESS through healthchecks and smoke-tested 200.
  Incident note: an intermediate state briefly set audit-postgres
  `POSTGRES_PASSWORD` to a self-reference (rendered empty) — caught in
  post-pass verification and corrected from the pre-change dump before any
  redeploy consumed it.
- **2026-11-24** — `AUTH_SUPER_ADMIN` unset on campus.auth in BOTH
  environments (the 2026-11-24 superadmin hardcode, PR #1234): production
  derives the super-admin from `WORKSPACE_DOMAIN` in code and no longer
  consults the nomination (also dropped from the production boot-gate
  required list), and on development the hardcoded identity's login is
  blocked outright, so the stored nomination had been inert. Variable
  delete does not redeploy: the then-running deployments carry the baked
  value until their next deploy, by which point the new code is live —
  no window where a deployment both reads the nomination and runs the
  old code.

- **2026-11-25** — campus.api gained an OPTIONAL runtime knob,
  `AUTH_INTROSPECTION_TTL_SECONDS` (PR #1258, the #1248 authenticate
  cache): authenticate results are cached per credential digest in a
  bounded per-worker LRU so a multi-span journey introspects its bearer
  once per TTL instead of once per call (~150–240 ms round trip each).
  **Unset on every service in both environments** — the inventories
  above reflect actual stored values, and this knob is deliberately
  absent from them. Code default is 30 s; `0` disables the cache. Only
  set it to tune revoke-latency (lower) or cache duration (higher);
  rejections are never cached, so a revocation is re-observed on every
  call regardless of TTL.
