"""campus.common.devops.deploy

This module handles development- and deployment-related tasks for the Campus
application.
"""

from typing import Protocol, runtime_checkable

import flask

from campus.common import devops, env, introspect
import campus.common.errors
from campus.common.utils import url


# pylint disable=unnecessary-ellipsis

@runtime_checkable
class AppModule(Protocol):
    """Interface for app modules.

    App modules must implement the `init_app` function.
    """

    @staticmethod
    def init_app(app: flask.Flask | flask.Blueprint) -> None:
        """Initialize the app module with the given Flask app."""
        ...


def is_codespace() -> bool:
    """Check if running in a GitHub Codespace environment."""
    return (
        env.get("CODESPACES") is not None
        and env.CODESPACES.lower() == "true"
    )


def configure_for_codespace(app: flask.Flask) -> None:
    """Configure the Flask app for GitHub Codespaces.

    - sets HOSTNAME from Codespace environment variables
    """
    env.set('PORT', env.get("PORT", "5000"))
    assert env.CODESPACE_NAME and env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN, \
        "CODESPACE_NAME and GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN must be set."
    env.set('HOSTNAME', f"{env.CODESPACE_NAME}-{env.PORT}.{env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}")


def configure_for_development(app: flask.Flask) -> None:
    """Configure the Flask app for development.

    - enables debug mode
    - sets host and port from environment variables or defaults
    - configures for Codespaces if detected
    """
    import os

    app.debug = True
    # Configure hostname for various development environments
    if is_codespace():
        configure_for_codespace(app)

    @app.get('/')
    def index():
        return flask.render_template_string(
            """
            <h1>Campus Development Server</h1>
            <p>Deployment mode: {{deploy}}</p>
            <p>Hostname: {{hostname}}</p>
            <p>Port: {{port}}</p>
            <ul>
                {% for rule in url_map.iter_rules() %}
                <li>{{ rule }}</li>
                {% endfor %}
            </ul>
            <p>
                <a href="{{login_url}}">Click here to log in</a>
            </p>
            """,
            deploy=env.DEPLOY,
            hostname=env.HOSTNAME,
            port=env.PORT,
            url_map=app.url_map,
            login_url=url.full_url_for('auth.test_login')
        )


def configure_for_deployment(app: flask.Flask) -> None:
    """Configure the Flask app for deployment.

    - adds health check route
    """
    # HOSTNAME environment variable should be set in deployment platform
    
    # Health check route for deployments
    # Many services expect a 200 response from the root URL to verify the
    # service is running
    @app.route('/')
    def health_check():
        return {
            'status': 'healthy',
            'deployment': env.DEPLOY,
            'environment': devops.ENV,
        }, 200
    return


def create_app(*appmodules: AppModule) -> flask.Flask:
    """Single entrypoint for creating a deployment app.

    AppModules are expected to initialise the app with the bare minimum
    routes/viewfunctions.

    This function adds other handlers, but does not carry out configuration.
    """
    app = flask.Flask(introspect.get_caller_module().__name__)
    for module in appmodules:
        module.init_app(app)
    campus.common.errors.init_app(app)

    # Register tracing middleware for auth/api deployments
    # campus.audit handles ingestion but doesn't trace its own requests
    # Controlled by AUDIT_TRACING_ENABLED environment variable (default: enabled)
    if env.DEPLOY in ('campus.auth', 'campus.api'):
        from campus.audit import middleware

        # Check if tracing is enabled (default: enabled for safety)
        tracing_enabled = env.get("AUDIT_TRACING_ENABLED", "1")
        if tracing_enabled == "1":
            middleware.init_app(app)

    return app
