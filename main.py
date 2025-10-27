#!/usr/bin/env python3
"""
Campus Development Server

Development and testing entry point for Campus services.
For production deployment, use wsgi.py with Gunicorn or other WSGI servers.

Deployment mode is determined by the DEPLOY environment variable:
- DEPLOY=vault: Deploys the vault service only  
- DEPLOY=apps: Deploys the full apps service (default)

Usage:
    DEPLOY=vault python main.py     # Start vault development server
    DEPLOY=apps python main.py      # Start apps development server
    gunicorn wsgi:app               # Production deployment
"""

import logging

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
    if mode not in devops.deploy.MODES:
        raise ValueError(
            f"Invalid deployment mode '{mode}'. "
            f"Valid modes are: {', '.join(devops.deploy.MODES)}."
        )
    return mode


def create_app(mode: str | None = None) -> devops.deploy.Flask:
    """Create the appropriate Campus app based on deployment mode.

    This factory only initialises the apropriate app.
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


def main():
    """Development server entry point for testing Campus services locally"""
    # Development server configuration

    # Create app instance for development server
    app = create_app("campus.apps")
    devops.deploy.configure_for_development(app)

    print("📝 For production deployment, use wsgi.py with Gunicorn")
    host = "0.0.0.0"
    port = int(env.PORT)
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
