"""campus.common.devops.deploy

This module handles deployment-related tasks for the Campus application.
"""

from typing import Protocol

from flask import Blueprint, Flask

from campus.common import introspect
import campus.common.errors

# Available deployment modes
MODES = ("apps", "vault")


# pylint disable=unnecessary-ellipsis

class AppModule(Protocol):
    """Interface for app modules.

    App modules must implement the `init_app` function.
    """

    @staticmethod
    def init_app(app: Flask | Blueprint) -> None:
        """Initialize the app module with the given Flask app."""
        ...


def configure_for_deployment(app):
    """Configure the Flask app for deployment.

    - adds health check route
    """
    # Health check route for deployments
    # Many services expect a 200 response from the root URL to verify the
    # service is running
    @app.route('/')
    def health_check():
        return {'status': 'healthy', 'service': 'campus-apps'}, 200


def create_app(*appmodules: AppModule) -> Flask:
    """Single entrypoint for creating a deployment app.

    AppModules are expected to initialise the app with the bare minimum
    routes/viewfunctions.

    This function adds other handlers, but does not carry out configuration.
    """
    app = Flask(introspect.get_caller_module().__name__)
    for module in appmodules:
        module.init_app(app)
    campus.common.errors.init_app(app)
    return app
