"""campus.deploy

This module handles development- and deployment-related tasks for the Campus
application: app creation (create_app), environment-specific configuration
(Codespaces, development, deployment) and the /health and / route
conventions (#842).

Deployments reached through a path-dispatching reverse proxy on a shared
hostname set PUBLIC_PREFIX (e.g. "/auth"): the health check registers
under the prefix and the service does not claim the shared root. Standalone
deployments keep /health and / at the hostname root.

It lives at the top level (moved out of campus.common.devops) because it
orchestrates whole services: it pulls in Flask and campus.audit middleware,
which environment-agnostic code in campus.common must not depend on.
"""

from typing import Protocol, runtime_checkable

import flask
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import BuildError

import campus.common.errors
import campus.config
from campus.common import env, introspect
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


def get_public_prefix() -> str:
    """Return this deployment's public path prefix, or "" if standalone.

    Set PUBLIC_PREFIX (e.g. "/auth") when requests reach the service
    through a path-dispatching reverse proxy under a shared hostname.
    Values are normalized to "/x" form (leading slash added, trailing
    slash stripped); unset, empty, or "/" means standalone.
    """
    prefix = (env.get("PUBLIC_PREFIX") or "").strip()
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix.rstrip("/")


def register_health(app: flask.Flask, prefix: str = "") -> None:
    """Register the health check endpoint (#842).

    Campus convention: /health is the endpoint deployment platforms and
    monitors should ping. Deployments behind a shared hostname set
    PUBLIC_PREFIX and expose it at PUBLIC_PREFIX + /health instead, so
    each service's health stays distinguishable on the shared host.
    Idempotent, so development and deployment configuration can be
    applied to the same app in tests.
    """
    rule = f"{prefix}/health"
    if has_rule(app, rule):
        return

    @app.get(rule)
    def health_check():
        return {
            'status': 'healthy',
            'deployment': env.DEPLOY,
            'environment': env.ENV,
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
    - honors PUBLIC_PREFIX for the health/route-index placement
    """

    app.debug = True
    # Configure hostname for various development environments
    if is_codespace():
        configure_for_codespace(app)

    register_health(app, get_public_prefix())

    # Services that own / (campus.audit, #842) keep their landing page
    # in development too; the route index below is for the API-only
    # services, where it doubles as the dev landing page. Behind a
    # shared hostname (PUBLIC_PREFIX set) the root belongs to the
    # gateway, so no index is registered.
    if get_public_prefix() or has_rule(app, '/'):
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
    - honors PUBLIC_PREFIX: health moves under the prefix and the
      landing page is skipped, since the gateway owns the shared root
    """
    prefix = get_public_prefix()

    # Health check endpoint (#842): deployment platforms and monitors
    # ping /health (standalone) or PUBLIC_PREFIX + /health (shared
    # hostname) to verify the service is running.
    register_health(app, prefix)

    # Landing page (#842): every standalone deployment serves HTML at /;
    # services with a web UI provide their own (registered during
    # init_app, before this runs). Behind a shared hostname the root is
    # the gateway's, so no landing page is registered.
    if not prefix:
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

    # Distinct session cookie per deployment (see SESSION_COOKIE_NAMES):
    # auth and audit both keep browser state in flask.session and would
    # clobber each other's cookies behind a shared hostname. Unlisted
    # deployments keep Flask's default.
    session_name = campus.config.SESSION_COOKIE_NAMES.get(env.DEPLOY or "")
    if session_name:
        app.config["SESSION_COOKIE_NAME"] = session_name

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
