#!/usr/bin/env python3
"""
WSGI Entry Point for Campus Suite

Production deployment entry point for Gunicorn and other WSGI servers.
This module provides the WSGI application instance that deployment platforms expect.

Usage with Gunicorn:
    DEPLOY=campus.auth gunicorn --bind "0.0.0.0:$PORT" wsgi:app
    DEPLOY=campus.api gunicorn --bind "0.0.0.0:$PORT" wsgi:app

The deployment mode is determined by the DEPLOY environment variable.
"""

import main
from campus.common.devops import deploy


# WSGI application instance for production deployment
app = main.create_app()
deploy.configure_for_deployment(app)


if __name__ == "__main__":
    # Fallback for direct execution (main.py is preferred for development)
    print("⚠️ Running WSGI module directly. For development, use: python main.py")
    app.run(host="0.0.0.0", port=5000, debug=False)
