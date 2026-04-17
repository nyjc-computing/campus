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

from campus.common import devops, env
from campus.logging_config import configure_logging

# Configure logging with OAuth debugging enabled
configure_logging(log_level=logging.INFO, enable_oauth_debug=True)
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
            f"Use {('campus.' + mode)!r} instead.", DeprecationWarning
        )
        mode = 'campus.' + mode

    try:
        module = importlib.import_module(mode)
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"Unable to create app for deployment mode '{mode}': {e}"
        )
    if not isinstance(module, devops.deploy.AppModule):
        raise TypeError(
            f"Module '{mode}' does not fulfill the AppModule protocol."
        )
    app = devops.deploy.create_app(module)
    return app


def main(deployment: str | None = None):
    """Development server entry point for testing Campus services locally"""
    from campus.common import devops
    assert env.ENV == devops.DEVELOPMENT, (
        "main() should only be called in development environment for "
        "testing purposes"
    )
    # Development server configuration
    if not env.get("DEPLOY"):
        env.set('DEPLOY', deployment)
    # Create app instance for development server
    app = create_app(deployment)
    devops.deploy.configure_for_development(app)

    print("📝 For production deployment, use wsgi.py with Gunicorn")
    host = "0.0.0.0"
    port = int(env.PORT)
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    import sys
    deployment = sys.argv[1] if len(sys.argv) >= 2 else None
    main(deployment=deployment)
