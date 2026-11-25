#!/usr/bin/env python3
"""
Campus Development Server

Development and testing entry point for Campus services.
For production deployment, use wsgi.py with Gunicorn or other WSGI servers.

Deployment mode is determined by the DEPLOY environment variable:
- DEPLOY=campus.auth: Deploys the authentication service
- DEPLOY=campus.api: Deploys the API service

Usage:
    DEPLOY=campus.auth python main.py     # Start auth development server
    DEPLOY=campus.api python main.py      # Start API development server
    gunicorn wsgi:app                     # Production deployment
"""

import logging

import flask

from campus import deploy
from campus.common import env
from campus.logging_config import configure_logging

# Configure logging with OAuth debugging enabled
configure_logging(log_level=logging.INFO)
logger = logging.getLogger(__name__)


def get_deployment_mode():
    """Get deployment mode from DEPLOY environment variable"""
    mode = env.DEPLOY
    if not mode:
        raise EnvironmentError(
            "Deployment mode not set. "
            "Set environment variable: export DEPLOY=<mode>"
        )
    return mode


def create_app(mode: str | None = None) -> flask.Flask:
    """Create the appropriate Campus app based on deployment mode.

    This factory only initialises the appropriate app.
    It does not configure for deployment or testing.
    """
    import importlib
    import warnings
    mode = mode or get_deployment_mode()
    if '.' not in mode or not mode.startswith('campus.'):
        warnings.warn(
            f"Deployment mode {mode!r} will be deprecated.\n"
            f"Use {('campus.' + mode)!r} instead.", DeprecationWarning, stacklevel=2
        )
        mode = 'campus.' + mode

    # Name the boot journey (#114): the worker's startup SDK calls
    # (boot-time vault reads) join one journey per process boot, and
    # the name is what journey cards render — "campus.auth.boot"
    # rather than a raw uid. Before the module import: boot-time vault
    # reads can happen at import time. Fail-open: boot must not depend
    # on observability.
    try:
        from campus_python import tracing
        tracing.set_process_journey(name=f"{mode}.boot")
    except Exception:  # noqa: BLE001 - fail-open: boot must not depend on observability
        logger.debug("boot journey naming unavailable", exc_info=True)

    try:
        module = importlib.import_module(mode)
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"Unable to create app for deployment mode '{mode}': {e}"
        ) from e
    if not isinstance(module, deploy.AppModule):
        raise TypeError(
            f"Module '{mode}' does not fulfill the AppModule protocol."
        )
    app = deploy.create_app(module)
    # Boot-time env validation (#1108): a deployment missing a required
    # var (or carrying one that a bad Railway reference resolved to
    # empty) must fail loudly here, not look healthy and 500 on the
    # first affected request hours later. Production raises; dev/test
    # boots log at debug and never block.
    from campus import bootstrap
    bootstrap.validate_required_env(
        mode, bootstrap.REQUIRED_ENV_VARS.get(mode, ()))
    # Migrations phase 4 (#747): warn at startup when the ledger shows
    # outstanding migrations. Production-style environments only, and
    # fail-open in the import: a deployment without migrations/ still
    # boots. #1167 layers the fail-closed gate on top: boot_gate keeps
    # the warn-always behavior and raises when MIGRATIONS_ENFORCED is
    # set and migrations are outstanding — that RuntimeError is
    # deliberately NOT swallowed here (fail-closed is the point).
    # #1256: on development boot_gate first applies this service DB's
    # pending migrations (fail-open, loud); production never auto-runs.
    try:
        from migrations import runner
    except Exception:  # noqa: BLE001 - fail-open: boot must not depend on the ledger
        logger.debug("migration pending-check unavailable", exc_info=True)
    else:
        runner.boot_gate()
    return app


def main(deployment: str | None = None):
    """Development server entry point for testing Campus services locally"""
    assert env.ENV == env.DEVELOPMENT, (
        "main() should only be called in development environment for "
        "testing purposes"
    )
    # Development server configuration
    if not env.get("DEPLOY"):
        env.set('DEPLOY', deployment)
    # Create app instance for development server
    app = create_app(deployment)
    deploy.configure_for_development(app)

    print("📝 For production deployment, use wsgi.py with Gunicorn")
    host = "0.0.0.0"
    port = int(env.PORT)
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    import sys
    deployment = sys.argv[1] if len(sys.argv) >= 2 else None
    main(deployment=deployment)
