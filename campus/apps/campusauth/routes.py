"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.
"""

from typing import Unpack

from flask import Blueprint, Flask, jsonify

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')


def init_app(app: Flask | Blueprint) -> None:
    """Initialise campusauth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


## Campus authentication routes
def not_implemented():
    return jsonify({"message": "Not implemented"}), 404

@bp.get('/authorize')
def authorize():
    """
    Authorization endpoint for OAuth2.

    This ednpoint:
    - Validates the user's session or identity.
    - Presents a consent screen to the user (if necessary).
    - Issues an authorization code (for authorization code flow).
    - Redirects the user back to the client with the code.
    """
    return not_implemented()

@bp.post('/token')
def token():
    """Token endpoint for OAuth2.
    
    Used by the client to exchange:
    - An authorization code for an access token (and optionally a refresh token).
    - A refresh token for a new access token.
    - Credentials (in password or client credentials grant types) for tokens.
    """
    return not_implemented()

@bp.post('/login')
def login():
    """Login endpoint for user authentication.

    This endpoint is used to:
    - check if an authorised session exists,
    - redirect the user to authenticate (through Google Workspace) if not,
    - handle the callback from the authentication provider.
    - redirect to the authorization endpoint if the user is authenticated.
    """
    return not_implemented()

@bp.post('/logout')
def logout():
    """Logout endpoint for user authentication.
    
    This endpoint is used to:
    - Invalidate the user's session.
    - Optionally redirect the user to a logout confirmation or login page.
    """
    return not_implemented()

# @bp.post('/authorize')  # OAuth2 authorization endpoint for user consent and code grant
# @unpack_request_json
# @validate(
#     request=AuthorizeSchema.__annotations__,
#     response={"message": str},
#     on_error=api_errors.raise_api_error
# )
# def authorize(*_, **data: Unpack[AuthorizeSchema]) -> FlaskResponse:
#     """Handle a Campus OAuth authorization request."""
#     return {"message": "Not implemented"}, 501

# @bp.post('/token')  # OAuth2 token endpoint for exchanging authorization code for access token
# @unpack_request_json
# @validate(
#     request=TokenSchema.__annotations__,
#     response={"message": str},
#     on_error=api_errors.raise_api_error
# )
# def verify_otp(*_, **data: Unpack[TokenSchema]) -> FlaskResponse:
#     """Verify an OTP for email authentication."""
#     return {"message": "Not implemented"}, 501

# TODO: /login
# TODO: /logout
