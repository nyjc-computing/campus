#!/usr/bin/env python3
"""
Campus Deployment Orchestrator

Entry point for deploying Campus services (vault or apps).
The campus.client library can be used independently to communicate with these deployments.

Deployment mode is determined by the content of the 'deploy' file:
- 'vault': Deploys the vault service only  
- 'apps': Deploys the full apps service

Clients use campus.client library to make HTTP requests to these deployed services.
"""

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
    """Start the appropriate Campus service based on deployment mode"""
    # Configuration
    host = "0.0.0.0"
    port = 5000

    # WSGI entry point for Gunicorn
    app = create_app()

    print(f"Starting service on {host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
