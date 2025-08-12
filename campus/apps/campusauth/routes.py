"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.
"""

from typing import TypedDict, Unpack

from flask import Blueprint, Flask, redirect, request, url_for

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')


class AuthorizationCodeRequest(TypedDict):
    """Request data for OAuth2 authorization code request."""
    client_id: str
    response_type: str
    redirect_uri: str
    scope: str | None
    state: str | None


def init_app(app: Flask | Blueprint) -> None:
    """Initialise campusauth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


# OAuth2 endpoints
@bp.get('/oauth2/authorize')
def oauth2_authorize() -> flask_validation.HtmlResponse:
    """OAuth2 authorization endpoint for user consent and code grant.

    This endpoint:
    1. Validates the authorization request
    2. Authenticates the user (through Google Workspace)
    3. Verifies scope of consent
    4. Issues authorization code
    5. Redirects user to the specified redirect URI
    """
    req_json: AuthorizationCodeRequest = flask_validation.validate_request_and_extract_json(
        AuthorizationCodeRequest.__annotations__,
        on_error=api_errors.raise_api_error
    )  # type: ignore
    return {"message": "Not implemented"}, 501


@bp.post('/oauth2/token')
def oauth2_token() -> flask_validation.JsonResponse:
    """OAuth2 token endpoint for exchanging authorization code for access token."""
    # minor change for demo purposes
    return {"message": "Not implemented"}, 501


@bp.get('/login')
def login() -> flask_validation.HtmlResponse:
    """Login endpoint."""
    return redirect(url_for('campus.oauth.google.authorize'))


@bp.post('/logout')
def logout() -> flask_validation.HtmlResponse:
    """Logout endpoint."""
    return {"message": "Not implemented"}, 501
