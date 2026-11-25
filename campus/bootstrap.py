"""campus.bootstrap

Shared startup policy for the suite services: storage initialization
convention + boot-time required-env validation (#1108).

The storage layer blocks `init_from_model` in production
(@env.block_env(PRODUCTION) in campus-core): production schema is owned
by migrations/ and the out-of-band bootstrap
(`python scripts/init_storage.py --service <svc>`), never by app
startup. Every service whose startup calls `init_storage()` therefore
needs the same two-part convention (#1103):

1. Skip initialization in production (the storage layer would raise,
   crash-looping the deployment — campus.audit's first prod boot did
   exactly that, #1100).
2. Outside production, run it self-healing: idempotent
   CREATE TABLE IF NOT EXISTS / collection setup, loud but non-fatal on
   failure, with the recovery path spelled out in the log line.

`run_init_storage` is that convention, stated once. Service startup
paths (campus.auth._init_auth_tables, campus.api._init_api_tables,
campus.audit.init_app) route every guarded init through it, so a new
resource's init inherits correct behavior by construction instead of by
copy-paste.
"""

__all__ = ["REQUIRED_ENV_VARS", "run_init_storage", "validate_required_env"]

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def run_init_storage(init_fn: Callable[[], None], *,
                     what: str, recovery: str) -> None:
    """Run one startup storage init under the self-heal convention.

    Args:
        init_fn: Zero-argument callable performing the idempotent
            initialization (a resource's init_storage or a small
            wrapper combining related calls).
        what: What is being initialized, phrased for an operator,
            e.g. "the school calendar table".
        recovery: How to create the table/collection out-of-band when
            startup skipped or failed, phrased as a command or pointer,
            e.g. "python scripts/init_storage.py --service api".

    In production this logs (at debug) that initialization was skipped
    and never calls init_fn — the storage layer blocks init_from_model
    there, and schema is owned by migrations/ plus the out-of-band
    bootstrap. Anywhere else, init_fn runs inside a catch-all that
    logs the failure loudly with the recovery path and returns without
    raising: a broken init must not take down the rest of startup
    (other resources, seeding, blueprint registration), and a missing
    table surfaces at request time with its own error.
    """
    from campus.common import env

    if env.ENV == env.PRODUCTION:
        logger.debug(
            "ENV=production: skipping startup storage init for %s "
            "(schema is managed by migrations/ and "
            "scripts/init_storage.py, not app startup)",
            what,
        )
        return
    try:
        init_fn()
    except Exception:
        logger.exception(
            "Failed to initialize %s. Recover: %s", what, recovery
        )


# Per-DEPLOY-mode required env vars (#1108): validated at boot in
# main.create_app via validate_required_env, so a misconfigured
# deployment fails loudly instead of looking healthy and 500ing on
# the first affected request hours later (auth lost CLIENT_ID/
# CLIENT_SECRET during the 2026-11-16 prod standup and every
# device-flow request 500'd while the service showed healthy).
#
# Enforced in production only: outside production validation logs at
# debug and never raises, so dev/test boots and minimal fixtures are
# unchanged.
REQUIRED_ENV_VARS: dict[str, tuple[str, ...]] = {
    "campus.auth": (
        # yapper's notification DB client (#1108: removing these
        # silently broke the device flow)
        "CLIENT_ID",
        "CLIENT_SECRET",
        # HMAC key for client-secret hashing (also mirrored in the
        # vault; the env var wins and is the declared prod setup)
        "SECRET_KEY",
        # storage backends (mongo collections + postgres tables)
        "MONGODB_URI",
        "POSTGRESDB_URI",
        # trace emission credential
        "AUDIT_API_KEY",
        # deployment policy: operator clients + the Google Workspace
        # hostgate for identity logins. The production super-admin is
        # hardcoded as campus-admin@<WORKSPACE_DOMAIN> (2026-11-24
        # decision), so AUTH_SUPER_ADMIN is neither required nor
        # consulted on production — WORKSPACE_DOMAIN supplies the
        # domain for both the hostgate and the hardcoded identity.
        "AUTH_OPERATOR_CLIENT_IDS",
        "WORKSPACE_DOMAIN",
        # canonical public origin (#653: fallback removed)
        "PUBLIC_URL",
    ),
    "campus.api": (
        # SDK boot (campus_python.Campus()) validates these eagerly
        "CLIENT_ID",
        "CLIENT_SECRET",
        # storage backends
        "MONGODB_URI",
        "POSTGRESDB_URI",
        # objects storage (files endpoints; a bad reference resolves
        # EMPTY, which must not silently pass)
        "BUCKET_ENDPOINT",
        "BUCKET_NAME",
        "BUCKET_REGION",
        "BUCKET_ACCESS_KEY_ID",
        "BUCKET_SECRET_ACCESS_KEY",
        # trace emission credential
        "AUDIT_API_KEY",
        # canonical public origin (#653)
        "PUBLIC_URL",
    ),
    "campus.audit": (
        # the audit DB is postgres-only (no mongo)
        "POSTGRESDB_URI",
        # operator key auto-seeded into the audit DB at startup
        "AUDIT_OPERATOR_API_KEY",
        # session/token signing key
        "SECRET_KEY",
        # canonical public origin (#653)
        "PUBLIC_URL",
    ),
    "campus.cleanup": (
        # NOT an HTTP service: the cron-scheduled cleanup deployment
        # (python -m campus.cleanup, Dockerfile.cleanup) reaches several
        # service databases through per-scope variables, swapped per
        # scope exactly like the migrations break-glass job selects a
        # service DB. Setup: docs/cleanup-deployment.md.
        "CLEANUP_JOB_AUDIT_POSTGRESDB_URI",
        "CLEANUP_JOB_AUTH_POSTGRESDB_URI",
        "CLEANUP_JOB_AUTH_MONGODB_URI",
        "CLEANUP_JOB_AUTH_MONGODB_NAME",
    ),
}


def validate_required_env(mode: str, required: tuple[str, ...]) -> None:
    """Fail the boot when this deployment's required vars are missing.

    Called from main.create_app with the service module's
    REQUIRED_ENV_VARS. In production a missing (or EMPTY — an
    unquoted Railway reference resolves empty, playbook §7.7) variable
    raises OSError naming every gap: the deployment should crash-loop
    visibly, not serve 500s hours later. Anywhere else the check logs
    at debug and returns — dev/test boots with minimal env are
    unchanged.
    """
    from campus.common import env

    if not required:
        return
    missing = [var for var in required if not env.get(var)]
    if not missing:
        logger.debug("%s: all %d required env vars set", mode, len(required))
        return
    if env.ENV == env.PRODUCTION:
        raise OSError(
            f"{mode}: missing required environment variables: "
            f"{', '.join(missing)} — refusing to boot a production "
            f"deployment that cannot serve its core flows (#1108). "
            f"Set them on the service (see docs/required-env-vars.md) "
            f"and redeploy."
        )
    logger.debug(
        "%s: required env vars not set (only enforced in production): "
        "%s", mode, ", ".join(missing),
    )
