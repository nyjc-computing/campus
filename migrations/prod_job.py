"""Production migration job entrypoint (break-glass; campus-deploy#4).

The campus-migrate Railway service's container command. The admin
Migrations view (#1169) is the primary production migration surface;
this job is the break-glass path for when a service cannot boot far
enough to serve its own routes — ledger surgery, stamping, baseline
bootstrap — and for the initial per-DB baselining.

Runs the migration runner for EVERY service scope in dependency order
(auth → api → audit), pointing the runner's context variables at each
service's databases in turn, so each scope's ledger lands in that
service's own DB (#1104 — the runner records into whatever
POSTGRESDB_URI its process holds). Configured by the campus-migrate
service's variables (Railway references to the DB services):

    MIGRATE_JOB_MODE                    plan | apply   (default: plan)
    MIGRATE_JOB_UP_TO                   optional apply bound (e.g. 008)
    MIGRATE_JOB_AUTH_POSTGRESDB_URI     ← ${{auth-postgres.DATABASE_URL}}
    MIGRATE_JOB_API_POSTGRESDB_URI      ← ${{api-postgres.DATABASE_URL}}
    MIGRATE_JOB_AUDIT_POSTGRESDB_URI    ← ${{audit-postgres.DATABASE_URL}}
    MIGRATE_JOB_AUTH_MONGODB_URI        optional, per scope, for the
    MIGRATE_JOB_API_MONGODB_URI         Mongo backfill migrations
    MIGRATE_JOB_AUDIT_MONGODB_URI

plan (the default) runs `status` per scope — read-only, the delta the
operator approves; apply runs `apply` per scope (`--up-to` honored).
A nonzero exit in any scope stops the job with that exit code, so the
Railway deployment goes CRASHED and the failure is visible. Envelope
backups upload when MIGRATION_BACKUP_BUCKET is set on the service
(#1170) — set it in production.

Run modes are selected by variable at trigger time (the deployment is
triggered explicitly by `scripts/prod_migrate.sh` in campus-deploy;
the service's deploy triggers are paused so nothing auto-runs it).
"""

import os
import sys

SCOPES = ("auth", "api", "audit")


def _runner_argv(mode: str, up_to: str | None) -> list[str]:
    """The runner argv for one scope under the job's mode."""
    if mode == "apply":
        argv = ["apply"]
        if up_to:
            argv += ["--up-to", up_to]
        return argv
    return ["status"]


def main() -> int:
    from migrations import runner

    mode = os.environ.get("MIGRATE_JOB_MODE", "plan")
    if mode not in ("plan", "apply"):
        print(
            f"error: MIGRATE_JOB_MODE {mode!r} is not plan|apply",
            file=sys.stderr,
        )
        return 2
    up_to = os.environ.get("MIGRATE_JOB_UP_TO") or None

    exit_code = 0
    for scope in SCOPES:
        uri = os.environ.get(f"MIGRATE_JOB_{scope.upper()}_POSTGRESDB_URI")
        if not uri:
            print(
                f"error: MIGRATE_JOB_{scope.upper()}_POSTGRESDB_URI is "
                "not set — the job cannot reach that service's DB "
                "(wire the campus-migrate service's variable references "
                "per deploy/migrate/README.md)",
                file=sys.stderr,
            )
            return 2
        mongo = os.environ.get(f"MIGRATE_JOB_{scope.upper()}_MONGODB_URI")
        # Swap the context per scope: the runner resolves POSTGRESDB_URI
        # at connect time, and Mongo-targeting migrations resolve the
        # Mongo URI through the storage layer at import (#1104).
        os.environ["POSTGRESDB_URI"] = uri
        if mongo:
            os.environ["MONGODB_URI"] = mongo
        else:
            os.environ.pop("MONGODB_URI", None)

        print(f"=== migrations job: {mode} {scope} ===", flush=True)
        code = runner.main(
            ["--db", scope, *_runner_argv(mode, up_to)])
        if code != 0:
            print(
                f"=== migrations job: {scope} exited {code} — stopping "
                f"the run ({len(SCOPES) - SCOPES.index(scope) - 1} scope(s) "
                "not run) ===",
                file=sys.stderr,
                flush=True,
            )
            return code
    print(f"=== migrations job: {mode} complete across {len(SCOPES)} "
          "scope(s) ===", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
