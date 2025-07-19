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

def main():
    """Start the appropriate Campus service based on deployment mode"""
    mode = get_deployment_mode()
    
    # Configuration
    host = "0.0.0.0"
    port = 5000
    
    if mode == "vault":
        print(f"🔐 Starting Campus Vault Service on {host}:{port}")
        from campus.vault import create_vault_app
        app = create_vault_app()
    else:
        print(f"🚀 Starting Campus Apps Service on {host}:{port}")
        from campus.apps import create_app
        app = create_app()
    
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()