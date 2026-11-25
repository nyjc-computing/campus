"""CLI entry point for the cleanup deployment.

    python -m campus.cleanup                 # run every registered job
    python -m campus.cleanup --job auth.auth_sessions
    python -m campus.cleanup --list

The Railway cron schedule is the trigger in production; `--job` and
`--triggered-by` support a deliberate hand-run (docs/
cleanup-deployment.md). Required-variable validation (#1108
semantics) runs before anything else: in production a missing
CLEANUP_JOB_* variable refuses the boot loudly; elsewhere it logs at
debug and proceeds.
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m campus.cleanup",
        description="Run the campus cleanup jobs (the fleet's one "
                    "scheduled deployment).",
    )
    parser.add_argument(
        "--job",
        action="append",
        metavar="NAME",
        help="run only this registered job (repeatable; default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the registered jobs and exit",
    )
    parser.add_argument(
        "--triggered-by",
        default="cron",
        help="ledger attribution for this run (default: cron; use "
             "manual:<name> for a hand-run)",
    )
    args = parser.parse_args(argv)

    from campus.cleanup import JOBS, run

    if args.list:
        for job in JOBS:
            print(f"{job.name}\t({job.scope})")
        return 0

    from campus import bootstrap
    bootstrap.validate_required_env(
        "campus.cleanup", bootstrap.REQUIRED_ENV_VARS.get("campus.cleanup", ()))
    return run(selected=args.job, triggered_by=args.triggered_by)


if __name__ == "__main__":
    sys.exit(main())
