#!/usr/bin/env python3
"""
WSGI Entry Point for Campus Suite

Production deployment entry point for Gunicorn and other WSGI servers.
This module provides the WSGI application instance that deployment platforms expect.

Usage with Gunicorn:
    DEPLOY=vault gunicorn --bind "0.0.0.0:$PORT" wsgi:app
    DEPLOY=apps gunicorn --bind "0.0.0.0:$PORT" wsgi:app

The deployment mode is determined by the DEPLOY environment variable.
"""

from main import create_app

# WSGI application instance for production deployment
app = create_app()

if __name__ == "__main__":
    # Fallback for direct execution (though main.py is preferred for development)
    print("⚠️  Running WSGI module directly. For development, use: python main.py")
    app.run(host="0.0.0.0", port=5000, debug=False)
