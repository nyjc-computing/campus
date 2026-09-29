"""campus.auth

This module contains the OAuth2 authentication hub for Campus.

campus-auth manages authentication and authorization for Campus
applications, as well as serving as a proxy for auth with third-party
integrations.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.auth only.
__all__ = ["init_app", "get_yapper"]

import logging

import flask
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from campus.yapper.base import YapperInterface

# Module-level yapper instance shared across all routes
_yapper_instance: "YapperInterface | None" = None

logger = logging.getLogger(__name__)


def get_yapper() -> "YapperInterface":
    """Get the module-wide yapper instance.
    
    Initializes yapper lazily if not already initialized.
    This should be called at app startup to avoid circular dependencies
    during request handling.
    """
    global _yapper_instance
    if _yapper_instance is None:
        import campus.yapper
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


def _auth_getsecret(name: str) -> str:
    """Get secret from vault for campus.auth deployment.

    This function is registered with env.register_getsecret() to provide
    deployment-specific vault access for campus.auth.

    When DEPLOY is campus.auth, uses direct database access to avoid
    circular dependency during initialization.

    Args:
        name: Name of the secret to retrieve

    Returns:
        The secret value from the vault

    Raises:
        OSError: If DEPLOY environment variable is not set
        api_errors.InternalError: If the secret is not found in the vault
    """
    from campus.common import env
    from campus.common.errors import api_errors

    deployment = env.get("DEPLOY")
    if deployment is None:
        raise OSError("Environment variable 'DEPLOY' required")

    # For campus.auth deployment, use direct database access to avoid
    # circular dependency (app trying to call its own HTTP API during init)
    if deployment == "campus.auth":
        from .resources import vault
        try:
            return vault[deployment][name]
        except KeyError:
            raise api_errors.InternalError(
                f"Vault secret '{name}' not found in label '{deployment}'"
            )

    # For other deployments, use HTTP client to call auth service
    import campus_python
    campus_auth = campus_python.Campus(timeout=60).auth
    try:
        return campus_auth.vaults[deployment][name]
    except KeyError:
        raise api_errors.InternalError(
            f"Vault secret '{name}' not found in label '{deployment}'"
        )


def init_app(app: flask.Blueprint | flask.Flask) -> None:
    """Initialize the Campus app with all modules.

    This function sets up all Campus apps components including API,
    authentication, and OAuth modules.

    Note: For creating new Flask applications, use the recommended
    pattern:
        from campus.common.devops.deploy import create_app
        import campus.apps
        app = create_app(campus.apps)

    This ensures proper error handling and deployment configuration.
    """
    from . import oauth_proxy, provider, routes
    from campus.common import env

    # Register deployment-specific getsecret function
    env.register_getsecret(_auth_getsecret)

    bp = flask.Blueprint("auth", __name__, url_prefix="/auth/v1")
    provider.init_app(bp)
    oauth_proxy.init_app(bp)
    routes.init_app(bp)

    if isinstance(app, flask.Flask):
        from campus.common import env
        app.secret_key = env.getsecret("SECRET_KEY")

    app.register_blueprint(bp)

    # Miscellaneous fixes

    # Enable strict slashes globally for this app
    # If disabled, routes not ending in slash are 308-redirected to
    # slash-ending routes, which results in stripped headers,
    # causing confusing 401 errors on authenticated endpoints.
    if isinstance(app, flask.Flask):
        app.url_map.strict_slashes = True

    # Ensure the public OAuth client ('guest') exists so device-flow
    # login works out of the box. Runs on every startup (idempotent) so
    # a database reset self-heals on the next deploy instead of silently
    # breaking the device flow with client-facing 400s (#605).
    _seed_public_client()


def _seed_public_client() -> None:
    """Seed the public OAuth client, logging loudly on failure.

    The public client cannot be created through the authenticated HTTP
    API (chicken-and-egg: authentication requires it to exist), so it
    must be seeded directly against storage at startup.

    Failure to seed is logged at ERROR level with the recovery command
    but does not abort startup, so an unrelated seed failure does not
    take down the rest of the auth service.
    """
    import campus.config
    from campus.common import devops

    # Ensure the clients tables exist and their schema is aligned for
    # public client support before seeding (both no-ops if up to date).
    # In production, schema management is handled by migrations/scripts,
    # so table initialization is blocked there.
    try:
        if devops.ENV != devops.PRODUCTION:
            from .resources.client import (
                ClientsResource,
                ensure_public_client_schema,
            )
            ClientsResource.init_storage()
            ensure_public_client_schema()
        from .resources.client import ensure_public_client
        if ensure_public_client():
            logger.info(
                "Seeded public OAuth client '%s'",
                campus.config.PUBLIC_OAUTH_CLIENT_ID
            )
    except Exception:
        logger.exception(
            "Failed to seed public OAuth client '%s': device-flow login "
            "will fail until the client exists. Recover with: "
            "python scripts/seed_public_oauth_client.py",
            campus.config.PUBLIC_OAUTH_CLIENT_ID
        )
