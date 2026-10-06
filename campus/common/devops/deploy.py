"""campus.common.devops.deploy

This module handles development- and deployment-related tasks for the Campus
application.
"""

from typing import Protocol, runtime_checkable

import flask
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import BuildError

import campus.common.errors
from campus.common import devops, env, introspect
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
    - sets PUBLIC_URL from the forwarded domain (Codespaces is always
      served over HTTPS)
    """
    env.set('PORT', env.get("PORT", "5000"))
    assert env.CODESPACE_NAME and env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN, \
        "CODESPACE_NAME and GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN must be set."
    env.set('HOSTNAME', f"{env.CODESPACE_NAME}-{env.PORT}.{env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}")
    env.set('PUBLIC_URL', f"https://{env.HOSTNAME}")


def has_rule(app: flask.Flask, rule: str) -> bool:
    """Check whether the app already maps the given URL rule."""
    return any(mapped.rule == rule for mapped in app.url_map.iter_rules())


def register_health(app: flask.Flask) -> None:
    """Register the health check endpoint at /health (#842).

    Campus convention: /health is the endpoint deployment platforms and
    monitors should ping. Idempotent, so development and deployment
    configuration can be applied to the same app in tests.
    """
    if has_rule(app, '/health'):
        return

    @app.get('/health')
    def health_check():
        return {
            'status': 'healthy',
            'deployment': env.DEPLOY,
            'environment': devops.ENV,
        }, 200


def register_generic_landing(app: flask.Flask) -> None:
    """Register a minimal landing page at / unless the service has one (#842).

    Campus convention: / is a landing page, not a 404 or a JSON blob.
    Services with a web UI (campus.audit) register their own root route;
    this generic page covers the API-only services. If deployments are
    later proxied under a single domain, landing pages move to subpaths.
    """
    if has_rule(app, '/'):
        return

    @app.get('/')
    def landing():
        return flask.render_template_string(
            """
            <!doctype html>
            <html lang="en">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>{{service}} — Campus</title>
            </head>
            <body>
                <h1>{{service}}</h1>
                <p>A Campus service. This service exposes a JSON API; there
                    is no web UI here.</p>
                <p><a href="/health">Health check</a></p>
            </body>
            </html>
            """,
            service=env.DEPLOY or "Campus service",
        )


def configure_for_development(app: flask.Flask) -> None:
    """Configure the Flask app for development.

    - enables debug mode
    - sets host and port from environment variables or defaults
    - configures for Codespaces if detected
    """

    app.debug = True
    # Configure hostname for various development environments
    if is_codespace():
        configure_for_codespace(app)

    register_health(app)

    # Services that own / (campus.audit, #842) keep their landing page
    # in development too; the route index below is for the API-only
    # services, where it doubles as the dev landing page.
    if has_rule(app, '/'):
        return

    @app.get('/')
    def index():
        # The login link only exists on deployments that register the
        # auth test_login route and set PUBLIC_URL; omit it elsewhere
        # instead of raising.
        try:
            login_url = url.full_url_for('auth.test_login')
        except (OSError, BuildError):
            login_url = None
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
                {% if login_url %}<a href="{{login_url}}">Click here to log in</a>{% endif %}
            </p>
            """,
            deploy=env.DEPLOY,
            hostname=env.get("HOSTNAME", "localhost"),
            port=env.get("PORT", "5000"),
            url_map=app.url_map,
            login_url=login_url
        )


def configure_for_deployment(app: flask.Flask) -> None:
    """Configure the Flask app for deployment.

    - adds health check and landing page routes (#842)
    """
    # HOSTNAME environment variable should be set in deployment platform

    # Health check endpoint (#842): deployment platforms and monitors
    # ping /health to verify the service is running.
    register_health(app)

    # Landing page (#842): every deployment serves HTML at /; services
    # with a web UI provide their own (registered during init_app,
    # before this runs).
    register_generic_landing(app)


def _is_tracing_enabled() -> bool:
    """Check if audit tracing middleware is enabled.

    Reads AUDIT_TRACING_ENABLED environment variable and validates it.
    Defaults to enabled (True) for safety - tracing is critical for observability.

    Returns:
        True if tracing is enabled, False if explicitly disabled

    Raises:
        OSError: If AUDIT_TRACING_ENABLED has an invalid value (not "0" or "1")
    """
    from campus.common import env

    # Use get_flag() for automatic "1"/"0" to bool conversion with validation
    # Default to enabled (True) for safety - tracing is critical for observability
    return env.get_flag("AUDIT_TRACING_ENABLED", True)


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

    # Fix scheme/redirect issues when behind reverse proxy (Railway, Nginx, etc.)
    # Railway sends X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-For headers
    # ProxyFix ensures Flask url_for() generates correct https URLs
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,          # X-Forwarded-For (client IP)
        x_proto=1,        # X-Forwarded-Proto (scheme) <-- fixes http/https
        x_host=1,         # X-Forwarded-Host (original host)
        x_prefix=1,       # X-Forwarded-Prefix (if using subpaths)
    )

    # Register tracing middleware for auth/api deployments
    # campus.audit handles ingestion but doesn't trace its own requests
    # Controlled by AUDIT_TRACING_ENABLED environment variable (default: enabled)
    if env.DEPLOY in ('campus.auth', 'campus.api'):
        from campus.audit import middleware

        # Check if tracing is enabled (default: enabled for safety)
        if _is_tracing_enabled():
            middleware.init_app(app)

    return app
