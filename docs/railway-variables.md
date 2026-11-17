# Railway environment variables (development)

Inventory of every user-set environment variable in the campus `development`
environment on Railway, classified by how its value is maintained:

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

> **Scope: `development` only.** Production is superadmin-only
> ([environment-access-policy.md](environment-access-policy.md)); audit it with
> the same recipe (below) and add a section from a superadmin session. The
> retired `staging` / `production-legacy` environments were deleted 2026-11-17
> (campus#1122).
>
> **Snapshot: 2026-11-17**, taken immediately after the fleet-wide templating
> pass of the same date (see [History](#history)).

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

## Shared variables (environment-level)

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

## Railway-provided variables (never user-set)

Injected into every deployment; avoid shadowing these names (user-set values
would override them):

- Networking: `RAILWAY_PUBLIC_DOMAIN`, `RAILWAY_PRIVATE_DOMAIN`
- Project/env/service metadata: `RAILWAY_PROJECT_NAME`, `RAILWAY_PROJECT_ID`,
  `RAILWAY_ENVIRONMENT`, `RAILWAY_ENVIRONMENT_ID`,
  `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_SERVICE_NAME`, `RAILWAY_SERVICE_ID`,
  `RAILWAY_STATIC_URL`
- Cross-service domain copies: `RAILWAY_SERVICE_<OTHER_SERVICE>_*_URL` —
  derived from every other service's public domain in the environment;
  Railway manages these (deleting a domain cascade-deletes its copies and
  redeploys the holders)
- Database services additionally: `RAILWAY_VOLUME_NAME`, `RAILWAY_VOLUME_ID`,
  `RAILWAY_VOLUME_MOUNT_PATH`
- `RAILWAY_TCP_PROXY_DOMAIN` / `RAILWAY_TCP_PROXY_PORT` /
  `RAILWAY_TCP_APPLICATION_PORT` — exist only while a TCP proxy is attached.
  **No dev service has one** (both DB proxies were deleted 2026-11-17).

## campus.auth

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `AUDIT_API_KEY` | `${{shared.AUDIT_API_KEY}}` | template | producer key shared with campus.api |
| `AUDIT_TRACING_ENABLED` | `1` | literal | audit span emission flag |
| `AUTH_OPERATOR_CLIENT_IDS` | `${{campus-admin.CLIENT_ID}}` | template | operator gate (#854); stored unquoted by Railway's normalizer |
| `AUTH_SUPER_ADMIN` | `campus-admin@nyjc.edu.sg` | literal | bootstrap superadmin email |
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

## campus.api

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

## campus.audit

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

## campus-gateway

The gateway reads upstreams from Railway-provided `RAILWAY_SERVICE_*_URL`
copies plus these five literals. No shared/templated values.

| Variable | Stored value | Kind | Notes |
|---|---|---|---|
| `API_PORT` / `AUTH_PORT` / `AUDIT_PORT` | `8080` | literal | internal upstream ports |
| `PORT` | `8080` | literal | public listen port |
| `NGINX_ENTRYPOINT_LOCAL_RESOLVERS` | `1` | literal | mesh resolver wiring (see deploy/gateway/README.md) |

## campus-admin

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

## campus-classroom

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

## campus-apphost

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

## campus-profile

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

## nyxchange-timetable-v2

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

## Databases (Railway-provisioned connect variables)

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
bucket name is dot-named, so quoting is load-bearing). Rotation:

```bash
railway bucket credentials -b campus.api-bucket -e development --reset
```

the exports update and every `BUCKET_*` reference follows on the next deploy.
Literal copies of bucket credentials rot silently on reset — dev has none;
production campus.api is still on literals (playbook docs/prod-rollout.md §2).

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
- Allowlists/emails (`AUTH_SUPER_ADMIN`, `AUDIT_ADMINS`, `AUTH_ADMINS`),
  feature flags, ports, `GUNICORN_CMD_ARGS`, image-init literals on DBs,
  test-account credentials (shared layer).
- `DEPLOY` on auth/api/audit — equals `RAILWAY_SERVICE_NAME`;
  `${{RAILWAY_SERVICE_NAME}}` would be equivalent (cosmetic, left literal).

## History

- **2026-10-30** — first reference wiring on dev (audit/auth/api DB URIs,
  bucket creds via #1020's renamed `campus.api-bucket`, self-domain refs).
- **2026-11-16/17** — the DB recreations and prod-standup work regressed parts
  of that wiring to literals and left the two DB TCP proxies attached.
- **2026-11-17** — full templating pass (this document's snapshot): shared
  layer created (`BASE_URL`, `AUDIT_API_KEY`, `EMBED_TOKEN_SECRET`), every
  cross-service URL and DB URI on references, DB connect variables recomposed
  from their built-in definitions, ghost/dead vars deleted, both TCP proxies
  removed. campus-profile and nyxchange-timetable-v2 have the new config
  stored; their running deployments carry identical values, with the new
  templates materializing on their next successful build (their repos had a
  pre-existing poetry.lock drift failure that day).
