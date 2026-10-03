# Storage Migration Protocol

This document describes how Campus handles storage schema and data-shape
changes: what a migration looks like, when one is needed, how it is
applied to each environment, and how applied state is tracked.

> This is a description of **actual current practice** (written 2026-10-03).
> It supersedes the earlier design in PR #382 (a `campus-admin` package with
> its own database, state table, runner and CLI), which was closed unimplemented.
> The gaps that design intended to close are listed under
> [Known gaps](#known-gaps) and remain tracked by issue #27.

## Overview

A migration is a single numbered Python file in `migrations/` at the repo
root. Each file is self-contained: it carries its own `upgrade()` and
`downgrade()` functions and is executed directly by an operator — there is
no runner, no CLI command, and no automatic execution on deploy.

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
  environment. Fix-forward with a new migration instead.
- **Docstring**: every migration opens with a docstring stating the
  revision ID, creation date, the rationale (linking the relevant issue),
  and run instructions (including how to scope it to the right service).
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
manual, per-service run:

1. `railway ssh -s campus.auth` (add `-e <environment>` as needed).
   Service SSH must be enabled in the Railway dashboard.
2. The repo is at `/app`; credentials resolve from the service's
   environment variables.
3. Run the migration:
   `python migrations/NNN_slug.py` — for data backfills, dry-run first,
   then `--apply`.
   Some migrations are guarded by `@block_env(PRODUCTION)`; where a guard
   must be bypassed for a deliberate production run, use a per-process
   override (`ENV=development python migrations/NNN_slug.py`) and say so
   in the migration's docstring.
4. Verify by exercising the affected flow, then record the run in the
   [ledger](#applied-migrations-ledger) below in the same PR that ships
   the migration.

Alternatives when SSH is unavailable: `railway run -s campus.auth` locally
(needs the DB reachable), or a temporary `ENV` flip + redeploy (mutates
running-service config twice — last resort).

## Applied-migrations ledger

There is no in-database state table. **This ledger is the authoritative
record of what has been applied where.** Update it in the same PR that
adds the migration, and correct it whenever an environment's status
changes. Statuses below verified as of 2026-10-03.

| Migration | Target | Purpose | Dev | Prod |
|-----------|--------|---------|-----|------|
| 001_add_assignments_table | Postgres | `assignments` table | historical (predates tracking) | not stood up |
| 002_add_submissions_table | Postgres | `submissions` table | historical (predates tracking) | not stood up |
| 003_add_api_traces_table | Postgres | `spans` table for audit tracing | live (verified 2026-10-01) | not stood up |
| 004_add_vault_clients_public_columns | Postgres | public-client columns on `vault_clients` | self-healed (verified 2026-09-29) | not stood up |
| 005_backfill_scope_string | Mongo | RFC 6749 scope-string rewrite + token field backfill | applied (2026-09-30) | not stood up |
| 006_add_client_allowed_scopes | Postgres | per-client scope allowlists | applied (recorded 2026-10-02) | pending — run when service is stood up |
| 007_add_client_upstream_scopes | Postgres | per-client upstream scope config | applied (recorded 2026-10-02) | pending — run when service is stood up |
| 008_add_client_token_bridge | Postgres | token-bridge columns | applied (recorded 2026-10-02) | pending — run when service is stood up |
| 009_create_app_credentials | Postgres | `app_credentials` for client_credentials grant | auto-init at startup (non-production) | pending — required; prod blocks `init_from_model` |

Note: production currently has no `campus.auth` service (survey
2026-09-29); "pending" rows become actionable only when it is stood up.

## Known gaps

These were the goals of the superseded #382 design that current practice
does **not** meet; they are the remaining scope of issue #27:

- **Applied-state tracking in the database** — no `_migrations` table; the
  ledger above is maintained by hand and can drift from reality.
- **Runner / CLI** — nothing enforces ordering, checks what is pending, or
  wraps execution; each run is a hand-typed command with hand-checked
  preconditions.
- **Rollback tooling** — `downgrade()` exists in every file but has never
  been exercised as part of a process, and data rewrites (005-style)
  cannot restore overwritten values.
- **Execution audit** — who ran what, when, with what outcome is recorded
  nowhere; git history records intent, not events.
- **Deploy integration / pre-flight checks** — no automation gates a
  deploy on migration state.
