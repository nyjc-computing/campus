# Required environment variables per service

**Generated from `campus.bootstrap.REQUIRED_ENV_VARS`** — do not edit by hand; change the declarations and re-run `poetry run python scripts/generate_required_vars_doc.py` (tests/unit/test_required_env_vars_doc.py fails CI on drift).

`main.create_app` validates these at boot **in production**: a missing or empty variable refuses the boot (#1108 — an unquoted Railway reference resolves EMPTY, which counts as missing; docs/prod-rollout.md §7.7). Outside production the check logs at debug and never blocks, so dev/test boots with minimal env are unchanged.

## `campus.api`

- `CLIENT_ID` — The service's campus OAuth client id (vault access, yapper)
- `CLIENT_SECRET` — The service's campus OAuth client secret
- `MONGODB_URI` — Mongo connection URI (document collections: sessions, device codes, circles, …)
- `POSTGRESDB_URI` — Postgres connection URI (vault/clients/credentials/audit tables)
- `BUCKET_ENDPOINT` — Objects storage endpoint (files endpoints)
- `BUCKET_NAME` — Objects storage bucket name
- `BUCKET_REGION` — Objects storage bucket region
- `BUCKET_ACCESS_KEY_ID` — Objects storage access key
- `BUCKET_SECRET_ACCESS_KEY` — Objects storage secret key
- `AUDIT_API_KEY` — Trace-emission credential (traces:write) for the audit API
- `PUBLIC_URL` — Canonical public origin for absolute URL generation (#653)

## `campus.audit`

- `POSTGRESDB_URI` — Postgres connection URI (vault/clients/credentials/audit tables)
- `AUDIT_OPERATOR_API_KEY` — Operator API key auto-seeded into the audit DB at startup
- `SECRET_KEY` — HMAC key for client-secret hashing / session signing
- `PUBLIC_URL` — Canonical public origin for absolute URL generation (#653)

## `campus.auth`

- `CLIENT_ID` — The service's campus OAuth client id (vault access, yapper)
- `CLIENT_SECRET` — The service's campus OAuth client secret
- `SECRET_KEY` — HMAC key for client-secret hashing / session signing
- `MONGODB_URI` — Mongo connection URI (document collections: sessions, device codes, circles, …)
- `POSTGRESDB_URI` — Postgres connection URI (vault/clients/credentials/audit tables)
- `AUDIT_API_KEY` — Trace-emission credential (traces:write) for the audit API
- `AUTH_OPERATOR_CLIENT_IDS` — Client ids allowed on operator routes
- `WORKSPACE_DOMAIN` — Google Workspace hostgate for identity logins; also supplies the domain for the hardcoded production super-admin (campus-admin@<domain>)
- `PUBLIC_URL` — Canonical public origin for absolute URL generation (#653)

## `campus.cleanup`

- `CLEANUP_JOB_AUDIT_POSTGRESDB_URI` — The audit service's Postgres database (rate-limit bucket sweep; the cleanup_runs ledger)
- `CLEANUP_JOB_AUTH_POSTGRESDB_URI` — The auth service's Postgres database (future auth-scope jobs)
- `CLEANUP_JOB_AUTH_MONGODB_URI` — The auth service's Mongo database (auth_sessions and device_codes sweeps)
- `CLEANUP_JOB_AUTH_MONGODB_NAME` — The auth service's Mongo database name (campus_auth); the backend resolves it separately from the URI
