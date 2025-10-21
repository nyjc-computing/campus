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

import os
import logging

from campus.common import devops

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_deployment_mode():
    """Get deployment mode from DEPLOY environment variable"""
    if "DEPLOY" not in os.environ:
        raise EnvironmentError(
            "Deployment mode not set. "
            "Set environment variable: export DEPLOY=<mode>"
        )
    mode = os.environ["DEPLOY"]
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
    mode = mode or get_deployment_mode()

    match mode:
        case "vault":
            import campus.vault
            logger.info("🔐 Creating Campus Vault Service")
            app = devops.deploy.create_app(campus.vault)
        case "apps":
            import campus.apps
            logger.info("🚀 Creating Campus Apps Service")
            app = devops.deploy.create_app(campus.apps)
        case _:
            raise ValueError(
                f"Unsupported deployment mode '{mode}'. "
                f"Valid modes are: {', '.join(devops.deploy.MODES)}"
            )
    return app


def main():
    """Development server entry point for testing Campus services locally"""
    # Development server configuration
    host = "0.0.0.0"
    port = 5000

    # Create app instance for development server
    app = create_app()

    print(f"🧪 Starting development server on {host}:{port}")
    print("📝 For production deployment, use wsgi.py with Gunicorn")
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
