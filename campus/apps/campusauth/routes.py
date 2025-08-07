"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.
"""

from typing import Unpack

from flask import Blueprint, Flask, redirect, url_for

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')


def init_app(app: Flask | Blueprint) -> None:
    """Initialise campusauth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


# OAuth2 endpoints
@bp.get('/oauth2/authorize')
def oauth2_authorize() -> flask_validation.JsonResponse:
    """OAuth2 authorization endpoint for user consent and code grant."""
    return {"message": "Not implemented"}, 501


@bp.post('/oauth2/token')
def oauth2_token() -> flask_validation.JsonResponse:
    """OAuth2 token endpoint for exchanging authorization code for access token."""
    return {"message": "Not implemented"}, 501


@bp.get('/login')
def login() -> flask_validation.JsonResponse:
    """Login endpoint."""
    return redirect(url_for('campus.oauth.google.authorize'))


@bp.post('/logout')
def logout() -> flask_validation.JsonResponse:
    """Logout endpoint."""
    return {"message": "Not implemented"}, 501
