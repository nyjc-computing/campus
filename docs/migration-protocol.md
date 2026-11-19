# Storage Migration Protocol

This document describes how Campus handles storage schema and data-shape
changes: what a migration looks like, when one is needed, how it is
applied to each environment, and how applied state is tracked.

> This is a description of **actual current practice** (written 2026-10-03).
> It supersedes the earlier design in PR #382 (a `campus-admin` package with
> its own database, state table, runner and CLI), which was closed unimplemented.
> The gaps that design intended to close are listed under
> [Known gaps](#known-gaps); issue #27 closed all of them in five phases
> (completed 2026-10-03).

## Overview

A migration is a single numbered Python file in `migrations/` at the repo
root. Each file is self-contained: it carries its own `upgrade()` and
`downgrade()` functions, and a module-level `TARGET_DB` constant naming
the service whose database it writes (#1104). Execution is
operator-driven — nothing runs automatically on deploy.
`migrations/runner.py` is the tool for both halves of that: it applies
migrations in revision order (`apply`) and tracks applied state in the
`_migrations` ledger table (`ensure|stamp|status` — see
[Applied-migrations ledger](#applied-migrations-ledger)). Running a
single migration script directly still works for special cases (e.g.
a data backfill's dry-run mode).

Since the #970 split each service owns its own databases; a migration
targets one of them:

| TARGET_DB | Service DBs written | Used for | Access pattern |
|-----------|--------------------|----------|----------------|
| `auth` | `campus.auth-postgres` / `campus.auth-mongodb` | Auth, vault, clients, grants tables + auth document collections | `PostgreSQLTable` from `campus.storage.tables.backend.postgres` (raw DDL via `init_from_schema`), `campus.storage.get_collection` |
| `api` | `campus.api-postgres` / `campus.api-mongodb` | api tables (emailotp, timetable members, calendar) + api document collections | same |
| `audit` | `campus.audit-postgres` | Audit tables (spans, api keys, rate-limit buckets) | `PostgreSQLTable` |

Examples: `migrations/011_create_calendar_table.py` (`TARGET_DB =
"api"`, Postgres DDL) and `migrations/005_backfill_scope_string.py`
(`TARGET_DB = "auth"`, Mongo data backfill). Files predating #1104
declare `TARGET_DB` retroactively; the runner's default scope is
`auth`, which keeps every pre-#1104 invocation working verbatim.

## When a migration is needed

The two storage families behave differently on fresh environments, which
drives when a migration must be written and where it must be run:

- **Postgres-backed models**: in non-production environments, tables are
  initialized from the model at startup (`init_from_model` — this is
  blocked in production), and the startup seed applies additive schema
  changes such as new columns. A **fresh** dev database therefore often
  needs no manual run. An **existing** table (e.g. one that predates a
  column addition) and **any production deployment** need the migration
  applied explicitly.
- **Mongo documents**: nothing auto-heals document shapes. Changing what a
  collection stores (field renames, list→string rewrites, backfilling
  derived fields) always requires a data migration.

Write a migration whenever a committed schema/model change is not
self-healing for an existing environment.

## File conventions

- **Location and numbering**: `migrations/NNN_short_slug.py`, sequential
  from the highest existing number. Never reuse a number, even if a
  migration was reverted before release.
- **Target DB**: every migration declares `TARGET_DB = "auth" | "api" |
  "audit"` — the service whose database `upgrade()` writes (#1104). The
  runner scopes every command with `--db` and the startup pending-check
  compares each service against its own ledger; an undeclared file
  defaults to `auth`, so the constant must be explicit for anything
  targeting api or audit.
- **Immutability**: never edit a migration that has been applied to any
  environment. Fix-forward with a new migration instead. Since phase 3
  (#746) this is enforced: `apply` refuses to run when an applied
  revision's file hash no longer matches the ledger (`--allow-hash-mismatch`
  proceeds with a warning for conscious recovery).
- **Docstring**: every migration opens with a docstring stating the
  revision ID, creation date, the rationale (linking the relevant issue),
  and run instructions (including how to scope it to the right service);
  rewrite migrations also state their backup usage there (`--backup
  PATH`, and which collections the backup covers).
- **Structure**: module-level `upgrade()` and `downgrade()`. Both are
  required, even for one-way data rewrites where `downgrade()` can only
  drop or no-op — say so in its docstring.
- **Idempotency**: DDL must be safe to re-run (`CREATE TABLE IF NOT
  EXISTS`, `DROP TABLE IF EXISTS`, guarded `ALTER`s). Data backfills must
  detect already-migrated documents and skip them.
- **Imports**: import storage backends directly
  (`campus.storage.tables.backend.postgres.PostgreSQLTable`,
  `campus.storage.get_collection`). Migrations intentionally do **not** go
  through `campus.api.resources`; they run in contexts where only storage
  is available.
- **Data migrations get a CLI**: rewrite-style migrations expose an
  argparse entry point that **dry-runs by default** and writes only with
  `--apply` (see `005_backfill_scope_string.py` for the pattern). DDL
  migrations do not need this.
- **Rewrites back up first**: a Mongo rewrite dumps the documents it is
  about to touch before its first write — accept `--backup PATH` and,
  when given, hand the affected documents (per collection) to
  `migrations/_backup.py`'s `write_backup()` before writing; `--backup`
  without `--apply` is a valid backup-only run. `downgrade()` cannot
  restore overwritten values; the backup is the restore path (see
  [Backups and restore](#backups-and-restore)).

## Backups and restore

Mongo rewrites (005-style data migrations) are the one migration family
whose `downgrade()` cannot undo: overwritten values are gone. Since
phase 3 (#746) the protocol is backup-before-rewrite: the migration's
`--backup PATH` dumps every affected document to a local JSON envelope
BEFORE the first write, via the helpers in `migrations/_backup.py`:

```python
from migrations._backup import write_backup

# in upgrade(), after collecting the affected documents, before writing:
write_backup(args.backup, REVISION, __file__,
             {"tokens": token_docs, "auth_sessions": session_docs})
```

The envelope (`campus-migration-backup/1`) records the producing
migration, a UTC timestamp, the operator and the documents keyed by
collection. Restore from the same context a migration runs in (storage
secrets resolve):

```bash
python migrations/_backup.py show backup.json            # summarize
python migrations/_backup.py restore backup.json --dry-run
python migrations/_backup.py restore backup.json         # write back
python migrations/_backup.py restore backup.json --collection tokens
```

Restore fidelity follows `update_by_id`: every backed-up field is set,
fields whose backed-up value is `None` are unset, and fields the
rewrite added after the backup are left in place — they carry no old
value to restore. A rewrite's `downgrade()` docstring names those
(005's `scope` unset-sentinel is the pattern); the restore stops where
that guidance ends. The restore validates the whole file (every
document carries an `id`) before writing anything.

## Rollback

There is no rollback command, by decision (#27 phase 5, #748,
2026-10-03): rollback is **by composition** — the pieces already built
cover what a rollback tool would do, without a half-executed
`downgrade()` being the worst outcome of a bad day:

- **DDL rollback**: run the migration's `downgrade()` manually, from the
  same context as `apply` (storage secrets resolve). Every migration
  carries one, but none has been exercised as part of a process to
  date — acceptable for additive DDL (`CREATE TABLE IF NOT EXISTS`,
  guarded `ALTER`s), which is the only DDL shipped so far.
- **Data restore**: rewrite migrations back up affected documents
  before writing; `migrations/_backup.py restore` is the restore path
  (see [Backups and restore](#backups-and-restore)). `downgrade()` on a
  data rewrite cannot undo overwrites — the backup, not `downgrade()`,
  is the restore path.
- **Failure forensics**: the `_migrations` ledger records who ran what,
  when, how long it took, the file hash and the error text (see
  [Applied-migrations ledger](#applied-migrations-ledger)).

`runner.py rollback REV` (#1170) reverses one applied migration per its
declaration: modules set `ROLLBACK_SUPPORTED = "ddl"` (downgrade()
drops what upgrade() added — additive DDL only) or `"backup"` (the
rewrite is reversed by restoring its envelope via
`--from-backup <path|bucket://name/key>`); undeclared migrations
refuse. On success the ledger row is deleted — the revision is pending
again and the next apply re-runs it; on any failure the row stays
applied. Rollback is hash-guarded like apply, holds the same advisory
lock, and at runtime it is admin-gated (`migrations:admin`) behind the
#1169 routes. Backup durability (#1170): when `MIGRATION_BACKUP_BUCKET`
is set, every envelope is also uploaded to that bucket before the
migration's first write — fail-closed, so an upload failure aborts the
migration rather than run unbacked.

## Applying migrations

`apply` is exclusive per service database (#1166): the runner holds a
session-level Postgres advisory lock for the whole run, so a
management-route apply (#1169), the break-glass job and a manual shell
run cannot interleave — a second apply polls briefly, then refuses
without writing anything. Programmatic callers may pass a
`should_cancel` predicate to `runner.main()`; it is checked between
migrations (one migration is the atomic unit, so abort never interrupts
a running one), cancelled revisions simply stay pending, and the next
apply resumes them in order.

Boot gate (#1167): production app services may set `MIGRATIONS_ENFORCED`;
startup then refuses (RuntimeError from `runner.boot_gate()`) while
outstanding migrations remain, so a release merged before its migrations
cannot take traffic — the failed deployment never passes its
healthcheck, the previous deployment keeps serving, and the operator
applies the pending migrations (admin UI or break-glass job) and
redeploys. The gate never runs migrations; an unreachable ledger stays
fail-open (warn only).

### Development (Railway dev)

Usually nothing to do: deploy and let startup initialization apply schema
changes (see [When a migration is needed](#when-a-migration-is-needed)).
Verify self-heal landed by exercising the affected flow (this is how 004
was verified: a fresh device-authorize request succeeded and survived a
redeploy).

Manual runs are still needed on dev when startup init cannot produce the
change (e.g. destructive DDL or a Mongo backfill) — follow the manual
runbook below.

### Production-style environments (manual runs, admin-UI first)

Production blocks `init_from_model`, so every migration is a
deliberate, per-service run by a human holding the right grant. Since
phase 4 (#747, 2026-10-03) the app surfaces skipped runs itself:
`main.create_app` logs one WARNING at startup naming every revision the
ledger does not record as applied or historical. With the fail-closed
boot gate (#1167), a deployment whose `MIGRATIONS_ENFORCED` var is set
refuses to boot over outstanding migrations entirely — the healthcheck
never passes, Railway keeps the previous deployment live, and an
out-of-order release merge therefore cannot take traffic over stale
schema (it self-heals: apply the migrations, redeploy).

**Who may run migrations.** Admins designated in the access-grant store
(#1168): a `migrations:write` grant for a service DB may apply and
abort that service's migrations; `migrations:admin` may roll back.
Rows are per-service (`resource_id` names auth, api or audit) —
authority over one service's migration surface never covers the fleet.
Grant seeding and administration stay operator/superadmin-only; this
is the ratified relaxation of the superadmin-only production rule for
this surface (see
[environment-access-policy.md](environment-access-policy.md)).

**The loop (primary path — the campus-admin Migrations view):**

1. **Write** the migration on a task branch → PR to `weekly`; dev
   validates it (self-heal, or the dev manual path below when startup
   init cannot produce the change). Every prod-bound migration must be
   LIVE-SAFE against the currently deployed `main`: additive /
   expand-first, runnable while the previous release serves;
   destructive/contract steps go in a separate later migration that
   gates on the new code being live. Long backfills batch and may be
   staged across windows with `--up-to`. Data-touching migrations
   follow the dry-run-by-default convention, declare their backup
   scope, and declare `ROLLBACK_SUPPORTED` (#1170) — or explicitly
   cannot be rolled back.
2. **Plan and approve**: after the `weekly` PR merges, a
   grants-bearing admin opens the Migrations view and reviews the
   pending delta — revisions, file hashes, declared impact/backup
   scope. The plan delta is the approval artifact. Time the apply for
   the lowest-usage window (end of day).
3. **Apply**: trigger from the view. Backups upload to the object
   bucket (`MIGRATION_BACKUP_BUCKET`) before any data write —
   fail-closed (#1170); the advisory lock (#1166) serializes runs; a
   failure records the ledger `failed` row and stops; abort takes
   effect between migrations. Verify: the ledger (view or
   `runner.py status`) shows applied, and the next app boots log no
   pending WARNING.
4. **Merge** `weekly` → `main` once pending migrations are applied
   (the orderly path: migrate → merge → green deploy). Update the
   doc ledger mirror table in the PR that shipped the migration.
5. **Recover** when needed: abort from the view (takes effect at the
   migration boundary); rollback per the migration's declared support
   — `ddl` via `downgrade()`, `backup` via the envelope restore
   (`--from-backup`, accepting `bucket://` URIs), both gated at
   `migrations:admin`.

**Break-glass paths** (when the admin surface is unavailable — e.g. a
service cannot boot far enough to serve its own routes):

- The dormant `campus-migrate` job service in the production
  environment (recipe: campus-deploy#4): explicit trigger only, builds
  from `weekly` (migrations run BEFORE the release merge), plan/apply
  modes selected at trigger time; `scripts/prod_migrate.sh plan|apply`
  wraps the trigger-verify-poll loop.
- The direct runner: `railway ssh -s campus.<svc> -e production`; the
  repo is at `/app`; credentials resolve from the service's
  environment variables; `python migrations/runner.py --db <svc>
  status|apply`. The `--db` scope matters (#1104): without it the
  runner silently operates on the wrong DB's ledger (011/calendar's
  docstring once said "run in the campus.auth context" and the
  2026-11-16 prod standup created the table in the auth DB). For data
  backfills, run the migration's own dry-run first. Note `railway
  ssh` needs port 22 egress AND account-token auth — blocked on the
  office network (work from any network where SSH egress is open).
- Emergency-only: a temporary `ENV` flip + redeploy (mutates
  running-service config twice — reserved for superadmin recovery,
  never routine).

> **DB reachability.** The DB hosts sit on Railway's restricted internal
> network and are not directly reachable from dev machines — including
> via `railway ssh` when off-network or when service SSH is not enabled
> for the target service (it is enabled per service in the Railway
> dashboard). When a local tool needs a direct DB connection, open a
> temporary public TCP proxy on the DB service with the Railway CLI
> (`railway tcp-proxy create -s <db-service> -p <port>`), connect through
> the proxy address it prints, and **delete the proxy afterwards**
> (`railway tcp-proxy delete`); a public proxy on a database is a
> stopgap, not a fixture.

## Applied-migrations ledger

Applied state is tracked in a `_migrations` table **per service
database** (#1104): each service's Postgres carries its own ledger,
recording the migrations whose `TARGET_DB` matches that service. The
table is the authoritative record wherever it exists; the table below
is a human-readable mirror and the record of history that predates it.
The table is created by the runner, not by a migration file, and
records both storage families (Postgres DDL and Mongo backfills)
targeting that service. The auth ledger is the oldest and carries
rows for api/audit-era revisions stamped before per-DB scoping existed
— those rows are residue, not drift: `status --db auth` skips
revisions whose files target another DB.

Runner commands (from a context where the target service's
`POSTGRESDB_URI` resolves, e.g. `railway ssh` into that service — the
ledger read/written is the one in the context's DB):

```bash
python migrations/runner.py ensure                  # create _migrations (idempotent)
python migrations/runner.py status                  # applied/pending per scoped migration file
python migrations/runner.py stamp 005               # record one migration as applied (no run)
python migrations/runner.py stamp all               # record every scoped migration as applied
python migrations/runner.py stamp 001 --as historical   # record as never applicable here
python migrations/runner.py apply                   # run pending scoped migrations in order
python migrations/runner.py apply --up-to 008       # run pending scoped migrations up to 008
python migrations/runner.py apply --allow-hash-mismatch  # run despite an edited applied file (warn)
```

Append `--db api` / `--db audit` to scope any command to that
service's migrations (default `auth`). Resolving a revision that
targets another DB errors with the right `--db` to pass, so a
wrong-context run cannot silently write the row into the wrong ledger.

Each row records the revision, filename, `status`, the stamp/run time
and operator (`applied_at`, `applied_by`), the error text for
failures, and — since phase 3 (#746, 2026-10-03) — the wall-clock
`duration_ms` of an actual run (NULL for stamped rows, which run
nothing) and `file_hash`: the sha256 of the migration file at write
time. `apply` runs a hash guard before anything else: an
already-applied revision whose file hash no longer matches the ledger
(the file was edited after it was applied) refuses the run;
`--allow-hash-mismatch` proceeds with a warning for conscious
recovery. Rows stamped before phase 3 (the dev baseline below) carry a
NULL `file_hash` and are not guarded; a fresh environment's first
apply anchors hashes from day one. Statuses:

- `applied` — `upgrade()` ran to completion (or the row was stamped for
  a baseline bootstrap)
- `failed` — `upgrade()` raised; the error is recorded and `apply`
  stops there (later migrations are not run). The next `apply` retries
  the failed revision first — a success overwrites the failure row.
- `historical` — recorded as never applicable to this environment
  (e.g. 001–002 on dev: the migration predates the current topology and
  its tables do not exist here). `apply` never runs a historical
  revision.

`stamp` records a status WITHOUT running anything — the baseline
bootstrap and ledger-correction tool. **Update the mirror below in the
same PR that adds a migration**, and correct it whenever an
environment's status changes.

Dev was baselined on 2026-10-03: `ensure` + `stamp 003`–`009`. 001–002
could not be stamped applied: their target tables (`assignments`,
`submissions`) are absent from both dev Postgres databases (verified by
`to_regclass` against `campus.auth-postgres` and `campus.api-postgres`
on 2026-10-03) — they predate the current service topology. With the
phase-2 runner they are recorded `--as historical`, so `status` reads
up to date and `apply` is a no-op on dev. Statuses below verified as of
2026-10-03.

| Migration | Target | Purpose | Dev | Prod |
|-----------|--------|---------|-----|------|
| 001_add_assignments_table | Postgres (api) | `assignments` table | historical — tables absent from both dev Postgres DBs (verified 2026-10-03); recorded `historical` in ledger | historical — fresh DB (2026-11-16 standup), recorded `historical` |
| 002_add_submissions_table | Postgres (api) | `submissions` table | historical — tables absent from both dev Postgres DBs (verified 2026-10-03); recorded `historical` in ledger | historical — fresh DB (2026-11-16 standup), recorded `historical` |
| 003_add_api_traces_table | Postgres (audit) | `spans` table for audit tracing | applied (verified 2026-10-01; stamped 2026-10-03) | applied — stamped 2026-11-16; audit spans live in the audit service's own postgres, so this legacy table is not recreated |
| 004_add_vault_clients_public_columns | Postgres (auth) | public-client columns on `vault_clients` | applied (self-healed, verified 2026-09-29; stamped 2026-10-03) | applied — stamped 2026-11-16 (fresh DB initialized from current model) |
| 005_backfill_scope_string | Mongo (auth) | RFC 6749 scope-string rewrite + token field backfill | applied (2026-09-30; stamped 2026-10-03) | applied — stamped 2026-11-16 (no legacy rows to backfill) |
| 006_add_client_allowed_scopes | Postgres (auth) | per-client scope allowlists | applied (recorded 2026-10-02; stamped 2026-10-03) | applied — stamped 2026-11-16 (fresh DB initialized from current model) |
| 007_add_client_upstream_scopes | Postgres (auth) | per-client upstream scope config | applied (recorded 2026-10-02; stamped 2026-10-03) | applied — stamped 2026-11-16 (fresh DB initialized from current model) |
| 008_add_client_token_bridge | Postgres (auth) | token-bridge columns | applied (recorded 2026-10-02; stamped 2026-10-03) | applied — stamped 2026-11-16 (fresh DB initialized from current model) |
| 009_create_app_credentials | Postgres (auth) | `app_credentials` for client_credentials grant | applied (auto-init at startup, non-production; stamped 2026-10-03) | applied — stamped 2026-11-16 (table created by `CredentialsResource.init_storage`) |
| 010_create_access_grants | Postgres (auth) | `access_grants` store (#883/#884), backfilling and retiring `vault_access` | applied (2026-10-10, 1.2s; backfill verified — 48 vault grant rows) | applied — stamped 2026-11-16 (fresh grants seeded directly; nothing to backfill) |
| 011_create_calendar_table | Postgres (api) | `calendar` table (school calendar, timetable-v2) | applied (self-healed by `campus.api` startup init) | applied 2026-11-16 (232 ms) — created in **campus.api's postgres** (where `campus.api` reads it, dev parity); the standup first created it in the auth DB per this row's pre-#1104 docstring and dropped it again (#1104) |
| 012_add_apikey_trace_binds | Postgres (audit) | `apikeys.trace_user_id`/`trace_client_id` — nullable TEXT bind columns for #944 trace-read scoping (NULL = unscoped; no backfill wanted) | applied — 003 stamped as the audit-dev baseline + 012 applied 2026-11-17 via the runner over a tcp proxy; dev columns had been added by hand hours earlier, `IF NOT EXISTS` made the re-run a no-op | applied — same path on prod 2026-11-17 (user-authorized one-off tcp proxy); 003 stamped as baseline first (neither audit ledger had been baselined), 154 ms; 5 existing keys, all unscoped |

Per-DB ledger baselines (#1104): the **auth** ledger keeps the rows it
has — its pre-#1104 rows for 001/002/003/011 are residue that
`--db auth` commands skip (their files target api/audit). The **api**
and **audit** ledgers are baselined at first scope run, in each
service's context:

```bash
# campus.api context:   ensure + stamp 001,002 --as historical + stamp 011
# campus.audit context: ensure + stamp 003
```

(the spans/calendar tables exist there via the out-of-band storage
bootstrap, docs/prod-rollout.md §3 phase 2 — the stamps record that
reality so the startup pending-check reads clean).

Prod baseline (2026-11-16 standup, see docs/prod-rollout.md): the
production databases were initialized from the current model and the
auth ledger stamped to match — `apply` is a no-op until a new migration
ships. New migrations run via the manual runbook above.

## Known gaps

These were the goals of the superseded #382 design that current practice
did not meet. Issue #27 closed all five in phases, completed
2026-10-03:

- **Applied-state tracking in the database** — CLOSED by phase 1
  (#744, 2026-10-03): the `_migrations` table and the
  `migrations/runner.py` `ensure|stamp|status` commands; dev is stamped
  and `status` matches the mirror above.
- **Runner / CLI** — CLOSED by phase 2 (#745, 2026-10-03): `apply`
  enforces revision ordering, reports/records pending state, wraps each
  migration with success/failure ledger rows, and stops on failure;
  `--up-to` bounds deliberate partial runs.
- **Rollback tooling** — CLOSED by phase 5 (#748, 2026-10-03): rollback
  is by composition, not a rollback command — manual `downgrade()` for
  DDL, phase-3 backups for data, the ledger for forensics
  ([Rollback](#rollback)). The data-restore half landed in phase 3
  (#746, 2026-10-03): rewrite migrations back up affected documents
  before writing ([Backups and restore](#backups-and-restore)).
- **Execution audit** — CLOSED by phase 3 (#746, 2026-10-03): every
  ledger row records the operator, the duration and the file hash;
  the hash guard makes the immutability rule enforceable rather than
  aspirational.
- **Deploy integration / pre-flight checks** — CLOSED by phase 4
  (#747, 2026-10-03): production-style boots log a WARNING when the
  ledger shows outstanding migrations (fail-open; apps never auto-run
  migrations), so a deploy that skipped this runbook is visible in the
  deployment logs. A *blocking* deploy gate remains out of scope by the
  standing decision that Campus apps never touch migration state beyond
  reading the ledger.
