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
`downgrade()` functions. Execution is operator-driven — nothing runs
automatically on deploy. `migrations/runner.py` is the tool for both
halves of that: it applies migrations in revision order (`apply`) and
tracks applied state in the `_migrations` ledger table
(`ensure|stamp|status` — see
[Applied-migrations ledger](#applied-migrations-ledger)). Running a
single migration script directly still works for special cases (e.g.
a data backfill's dry-run mode).

Migrations target one of two storage families:

| Target | Used for | Access pattern |
|--------|----------|----------------|
| Postgres (`campus.auth-postgres` service) | Auth, vault, and audit tables | `PostgreSQLTable` from `campus.storage.tables.backend.postgres`, raw DDL via `init_from_schema` |
| Mongo (`campus.auth-mongodb`) | Auth document collections | `campus.storage.get_collection`, document-by-document rewrites |

Examples: `migrations/003_add_api_traces_table.py` (Postgres DDL) and
`migrations/005_backfill_scope_string.py` (Mongo data backfill).

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

A `runner.py rollback REV` subcommand — restricted to additive-DDL
migrations, refusing data rewrites — stays shelved until a production
database with real data exists; until then the manual `downgrade()` run
is the same operation with fewer moving parts to trust.

## Applying migrations

### Development (Railway dev)

Usually nothing to do: deploy and let startup initialization apply schema
changes (see [When a migration is needed](#when-a-migration-is-needed)).
Verify self-heal landed by exercising the affected flow (this is how 004
was verified: a fresh device-authorize request succeeded and survived a
redeploy).

Manual runs are still needed on dev when startup init cannot produce the
change (e.g. destructive DDL or a Mongo backfill) — follow the manual
runbook below.

### Staging / production-style environments (manual runbook)

These environments block `init_from_model`, so every migration is a
manual, per-service run. Since phase 4 (#747, 2026-10-03) the app
surfaces skipped runs itself: `main.create_app` logs one WARNING at
startup naming every revision the ledger does not record as applied or
historical (pending, failed, or a ledger row whose file is gone). The
check is fail-open — an unreachable ledger never blocks boot, and
non-production boots are unchanged (dev self-heals schema via
`init_from_model`) — and it never runs anything: migrations stay
manual, per this runbook:

1. `railway ssh -s campus.auth` (add `-e <environment>` as needed).
   Service SSH must be enabled in the Railway dashboard.
2. The repo is at `/app`; credentials resolve from the service's
   environment variables.
3. Run the migration:
   `python migrations/runner.py apply` runs every pending migration in
   revision order and records each outcome in the ledger; scope a
   deliberate partial run with `--up-to <rev>`.
   For data backfills, run the migration's own dry-run first
   (`python migrations/NNN_slug.py`, then `--apply` logic is what
   `runner.py apply` invokes).
   Some migrations are guarded by `@block_env(PRODUCTION)`; where a guard
   must be bypassed for a deliberate production run, use a per-process
   override (`ENV=development python migrations/runner.py apply`) and say
   so in the migration's docstring.
4. Verify by exercising the affected flow, then check the runner already
   recorded the run (`python migrations/runner.py status`); update the
   mirror table in the same PR that ships the migration.

Alternatives when SSH is unavailable: `railway run -s campus.auth` locally
(needs the DB reachable), or a temporary `ENV` flip + redeploy (mutates
running-service config twice — last resort).

## Applied-migrations ledger

As of 2026-10-03 (#27 phase 1), applied state is tracked in the
`_migrations` table of the auth Postgres (`campus.auth-postgres`) —
**the table is the authoritative record wherever it exists**. The table
below is a human-readable mirror and the record of history that predates
it. The table is created by the runner, not by a migration file, and
records both storage families (Postgres DDL and Mongo backfills), since
every migration runs in the campus.auth context where both secrets
resolve.

Runner commands (from a context where `POSTGRESDB_URI` resolves, e.g.
`railway ssh` into campus.auth):

```bash
python migrations/runner.py ensure             # create _migrations (idempotent)
python migrations/runner.py status             # applied/pending per migration file
python migrations/runner.py stamp 005          # record one migration as applied (no run)
python migrations/runner.py stamp all          # record every migration as applied
python migrations/runner.py stamp 001 --as historical   # record as never applicable here
python migrations/runner.py apply              # run pending migrations in revision order
python migrations/runner.py apply --up-to 008  # run pending migrations up to 008
python migrations/runner.py apply --allow-hash-mismatch  # run despite an edited applied file (warn)
```

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
| 001_add_assignments_table | Postgres | `assignments` table | historical — tables absent from both dev Postgres DBs (verified 2026-10-03); recorded `historical` in ledger | not stood up |
| 002_add_submissions_table | Postgres | `submissions` table | historical — tables absent from both dev Postgres DBs (verified 2026-10-03); recorded `historical` in ledger | not stood up |
| 003_add_api_traces_table | Postgres | `spans` table for audit tracing | applied (verified 2026-10-01; stamped 2026-10-03) | not stood up |
| 004_add_vault_clients_public_columns | Postgres | public-client columns on `vault_clients` | applied (self-healed, verified 2026-09-29; stamped 2026-10-03) | not stood up |
| 005_backfill_scope_string | Mongo | RFC 6749 scope-string rewrite + token field backfill | applied (2026-09-30; stamped 2026-10-03) | not stood up |
| 006_add_client_allowed_scopes | Postgres | per-client scope allowlists | applied (recorded 2026-10-02; stamped 2026-10-03) | pending — run when service is stood up |
| 007_add_client_upstream_scopes | Postgres | per-client upstream scope config | applied (recorded 2026-10-02; stamped 2026-10-03) | pending — run when service is stood up |
| 008_add_client_token_bridge | Postgres | token-bridge columns | applied (recorded 2026-10-02; stamped 2026-10-03) | pending — run when service is stood up |
| 009_create_app_credentials | Postgres | `app_credentials` for client_credentials grant | applied (auto-init at startup, non-production; stamped 2026-10-03) | pending — required; prod blocks `init_from_model` |

Note: production currently has no `campus.auth` service (survey
2026-09-29); "pending" rows become actionable only when it is stood up.

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
