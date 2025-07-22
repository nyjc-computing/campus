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


def get_deployment_mode():
    """Get deployment mode from DEPLOY environment variable"""
    if "DEPLOY" not in os.environ:
        raise EnvironmentError(
            "Deployment mode not set. "
            "Set environment variable: export DEPLOY=vault or export DEPLOY=apps"
        )
    mode = os.environ["DEPLOY"]

    if mode not in ["vault", "apps"]:
        raise ValueError(
            f"Invalid deployment mode '{mode}'. "
            "Valid modes are: vault, apps. "
            "Set environment variable: export DEPLOY=vault or export DEPLOY=apps"
        )

    return mode


def create_app():
    """Create the appropriate Campus app based on deployment mode"""
    mode = get_deployment_mode()

    match mode:
        case "vault":
            print("🔐 Creating Campus Vault Service")
            from campus.vault import create_app
            return create_app()
        case "apps":
            print("🚀 Creating Campus Apps Service")
            from campus.apps import create_app
            return create_app()
    raise ValueError(
        f"Unsupported deployment mode '{mode}'. "
        "Valid modes are: vault, apps"
    )


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
