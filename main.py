#!/usr/bin/env python3
"""
Campus Service Entry Point

Unified entry point for all Campus services.
Deployment mode is determined by the content of the 'deploy' file.
"""

import os
from pathlib import Path


def get_deployment_mode():
    """Get deployment mode from deploy file"""
    deploy_file = Path(__file__).parent / "deploy"

    if not deploy_file.exists():
        raise FileNotFoundError(
            "Deployment mode file 'deploy' not found. "
            "Create it with: echo 'vault' > deploy or echo 'apps' > deploy"
        )

    mode = deploy_file.read_text().strip().lower()
    if mode not in ["vault", "apps"]:
        raise ValueError(
            f"Invalid deployment mode '{mode}'. "
            "Valid modes are: vault, apps"
        )

    return mode


def create_app():
    """Create the appropriate Campus app based on deployment mode"""
    mode = get_deployment_mode()

    if mode == "vault":
        print(f"🔐 Creating Campus Vault Service")
        from campus.vault import create_vault_app
        return create_vault_app()
    else:
        print(f"🚀 Creating Campus Apps Service")
        from campus.apps import create_app
        return create_app()


def main():
    """Start the appropriate Campus service based on deployment mode"""
    mode = get_deployment_mode()

    # Configuration
    host = "0.0.0.0"
    port = 5000

    # WSGI entry point for Gunicorn
    app = create_app()

    print(f"Starting service on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
