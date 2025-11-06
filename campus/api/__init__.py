"""campus.api

Web API for Campus services.
"""

# Note: do not expose .resources directly here. It is meant for internal
# use within campus.api only.
__all__ = ["init_app"]

import flask

from campus.common import env
from campus.common.errors import auth_errors

# Other local imports are intentionally omitted to avoid circular
# dependencies.


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    from . import resources, routes
    from campus.auth import webauth

    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.users.init_app(bp)

    @bp.before_request
    def authorize_api_request():
        """Check request header for authorization credentials.

        Push credential information to flask.g for use in route
        handlers.
        """
        from campus.client.vault import get_vault
        vault = get_vault()

        req_header = dict(flask.request.headers)
        httpauth = (
            webauth.http.HttpAuthenticationScheme
            .from_header(provider="campus", http_header=req_header)
        )
        assert httpauth.header
        if not httpauth.header.authorization:
            raise auth_errors.InvalidRequestError(
                "Missing Authorization property in HTTP header"
            )
        auth = httpauth.header.authorization
        match auth.scheme:
            case "basic":
                client_id, client_secret = auth.credentials()
                # Raises API errors if auth fails
                auth_json = vault.clients.authenticate(
                    client_id,
                    client_secret
                )
                if "error" in auth_json:
                    auth_errors.raise_from_json(auth_json)
                flask.g.current_client = vault.client.get(client_id)
            case "bearer":
                access_token = auth.token
                # raises UnauthorizedError for invalid access_token
                token = resources.token[access_token].get()
                flask.g.current_user = resources.user[token.user_id].get()
                flask.g.current_client = vault.client.get(token.client_id)

    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        from campus.client.vault import get_vault
        vault = get_vault()
        app.secret_key = vault[env.DEPLOY]["SECRET_KEY"].get()["value"]
