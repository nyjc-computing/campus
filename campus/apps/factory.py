"""app.factory

This module provides factory functions to create and configure the main Flask
application and its components. It initializes the API, OAuth, and other
necessary services.
"""

from flask import Flask

from campus.vault import Vault


def create_app_from_modules(*modules) -> Flask:
    """Factory function to create the Flask app.
    
    This is called if api is run as a standalone app.
    """
    app = Flask(__name__)
    for module in modules:
        module.init_app(app)
    app.secret_key = Vault('campus').get('SECRET_KEY')
    return app
