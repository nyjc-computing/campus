# The cleanup deployment (`campus.cleanup`)

The fleet's **one scheduled deployment**. Railway cron starts it on a
schedule; it runs every registered cleanup job against the service
databases and exits. Nothing on the app services (campus.auth,
campus.api, campus.audit) ever runs periodic work: an inbound request
wakes a serverless deployment and resets its idle timer, so a timer
inside a service would keep it awake forever (#1249, the Sleep rule in
`docs/railway-architecture.md`).

The job implementations live in `campus/cleanup/jobs.py` and reuse the
stack's own layers — the resource layer and the storage API
(`get_collection` / `get_table` / `delete_by_id`). No raw drivers, no
HTTP calls. That keeps one implementation for each cleanup: the same
code the services use is what the schedule runs.

## What runs, in order

| Job | Scope | Deletes | Formerly |
|---|---|---|---|
| `audit.rate_limit_buckets` | audit Postgres | ingest rate-limit buckets idle for `BUCKET_TTL_SECONDS` (1 h) | ran inline on every ingest (`_maybe_cleanup`) |
| `auth.auth_sessions` | auth Mongo | sessions whose model predicate says expired | only via `POST /auth/v1/sessions/sweep` |
| `auth.device_codes` | auth Mongo | expired device codes | nothing — codes accumulated forever (#1253) |

Not here, on purpose: the email-OTP cleanup and yapper's unsubscribe
event cleanup are not time-based (#1253 tracks what joins next —
spans/telemetry retention and the auth housekeeping rulings).

Add a job: write the sweep in `campus/cleanup/jobs.py` (idempotent,
chunked, counted), register it in `campus.cleanup.JOBS`, and — if it
needs a new database — add the scope mapping to `campus.cleanup.SCOPES`
and the `CLEANUP_JOB_*` variable to `campus/bootstrap.py` +
`docs/required-env-vars.md` (regenerate; the drift test fails CI
otherwise).

## The guarantees

- **One run, one ledger row** in the `cleanup_runs` table (audit
  Postgres): `started_at`, `finished_at`, `status` (running/success/
  failed), `triggered_by`, per-job `rows_affected` and errors in a
  `jobs` JSONB column, total `rows_affected`, `duration_ms`.
  Read it with any SQL client against the audit DB, or the admin UI's
  SQL surface:
  `SELECT * FROM cleanup_runs ORDER BY started_at DESC LIMIT 20;`
- **Runs never overlap.** The run holds a session-level Postgres
  advisory lock (its own key; the migration runner's apply lock is a
  different one). A run that finds the lock held skips without
  writing anything and exits 0 — the holder covers the work.
- **Nothing to do is a success**: a job that finds no expired rows
  returns 0 and the run is `success`.
- **Failures are visible and contained**: a job that raises is
  recorded in the ledger row (its error text in `jobs` and `error`),
  the remaining jobs still run, and the deployment exits 1 — Railway
  shows CRASHED.
- **Idempotent**: every job deletes only rows matching its expiry
  predicate, so a re-run (or an overlapping tick) converges.

## Railway setup (superadmin, development first)

1. **Service**: create `campus-cleanup` explicitly into the target
   environment (never by duplicating an environment — #1109). Source:
   this repo, branch `weekly` (autodeploy on, like the app services).
2. **Build**: Dockerfile, path `Dockerfile.cleanup` — NOT railpack
   (railpack ignores start commands; the entrypoint must be the image
   CMD, like `Dockerfile.migrate` for the break-glass job).
3. **Cron**: add the cron schedule on the service (Railway native
   cron; scheduled runs must be at least 5 minutes apart). A daily or
   hourly cadence suits the current jobs — nothing here is urgent
   (the cadence decision lives on #1249). `railway cron run` triggers
   one off-schedule run.
4. **Instance limits**: **1 vCPU / 2 GB RAM** — set on development
   2026-11-25 and expected to match on production at wiring time. The
   jobs are short, sequential sweeps; the default 32 vCPU / 32 GB
   entitlement would be idle capacity the deployment is billed for on
   every run (each replica is a dedicated microVM sized to these
   limits — see `docs/railway-architecture.md` "What a deployment can
   measure about itself"). API recipe (ids inside the input; the
   Railway-usage UI shows GB-minutes as GB):
   `railway api 'mutation($e:String!,$s:String!){ serviceInstanceLimitsUpdate(input:{environmentId:$e, serviceId:$s, vCPUs:1, memoryGB:2}) }'`.
5. **Variables** (Railway references resolve per environment):

   | Variable | Value |
   |---|---|
   | `CLEANUP_JOB_AUDIT_POSTGRESDB_URI` | `${{campus.audit-postgres.DATABASE_URL}}` |
   | `CLEANUP_JOB_AUTH_POSTGRESDB_URI` | `${{campus.auth-postgres.DATABASE_URL}}` |
   | `CLEANUP_JOB_AUTH_MONGODB_URI` | `${{campus.auth-mongodb.MONGODB_URI}}` |
   | `CLEANUP_JOB_AUTH_MONGODB_NAME` | `campus_auth` (literal — the Mongo database name; the backend resolves it separately from the URI) |

   `DEPLOY=campus.cleanup` for self-documentation. Credentials-before-
   first-boot rules apply (#1105): wire the references before the
   first deploy. `bootstrap.REQUIRED_ENV_VARS` validates them on
   production boots (#1108).

6. **No domain, no healthcheck**: it is a batch job. A failed run
   exits nonzero → the deployment goes CRASHED → visible in the
   deploy history, like the break-glass migration job.

## Run it by hand

From the service's context (its variables make the URIs resolve):

```bash
python -m campus.cleanup                 # every registered job
python -m campus.cleanup --list          # what is registered
python -m campus.cleanup --job auth.auth_sessions --triggered-by manual:owner
```

Locally, with the URIs in the environment, the same commands work;
`--job` and `--triggered-by` mark the ledger row so a hand-run is
never mistaken for a scheduled one.

## Why the storage env is swapped per scope

The storage layer resolves one `POSTGRESDB_URI` and one `MONGODB_URI`
per process, but this deployment reaches several databases. The
runner copies each scope's `CLEANUP_JOB_*` variable onto the name the
storage layer reads, one scope at a time — exactly how
`migrations/prod_job.py` selects a service's database (#1104). Job
functions import their resource modules lazily inside the call, so a
scope's binding always happens after the swap.
