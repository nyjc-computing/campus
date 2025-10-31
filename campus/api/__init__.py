"""campus.api

Web API for Campus services.
"""

__all__ = []

import flask

from campus.common.errors import auth_errors
from campus.models import token, user, webauth

from . import routes

tokens = token.Tokens()
users = user.User()


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise the API blueprint with the given Flask app."""
    # Organise API routes under api blueprint
    bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')
    # Users need to be initialised first as other blueprints
    # rely on user table
    routes.admin.init_app(bp)
    routes.circles.init_app(bp)
    routes.emailotp.init_app(bp)
    routes.session.init_app(bp)
    routes.users.init_app(bp)

    @bp.before_request
    def authorize_api_request():
        """Check request header for authorization credentials.

        Push credential information to flask.g for use in route
        handlers.
        """
        req_header = dict(flask.request.headers)
        auth = (
            webauth.http.HttpAuthenticationScheme
            .from_header(provider="campus", http_header=req_header)
            .get_auth(http_header=req_header)
        )
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
                access_token = auth.value
                # raises UnauthorizedError for invalid access_token
                token = tokens.get(access_token)
                flask.g.current_user = users.get(token.user_id)
                flask.g.current_client = vault.client.get(token.client_id)
    
    app.register_blueprint(bp)

    if isinstance(app, flask.Flask):
        from campus.client.vault import get_vault
        vault = get_vault()
        app.secret_key = vault["api"]["SECRET_KEY"].get()["value"]
