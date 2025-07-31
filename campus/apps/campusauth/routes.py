"""campus.apps.campusauth.routes

Routes for Campus authentication - clients and users.
"""

from typing import Unpack

from flask import Blueprint, Flask

from campus.common.errors import api_errors
import campus.common.validation.flask as flask_validation

# No url prefix because authentication endpoints are not only used by the API
bp = Blueprint('campusauth', __name__, url_prefix='/')


def init_app(app: Flask | Blueprint) -> None:
    """Initialise campusauth routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


## Campus authentication routes
from flask import jsonify

def not_implemented():
    return jsonify({"message": "Not implemented"}), 404

@bp.route('/authorize', methods=['POST'])
def authorize():
    return not_implemented()

@bp.route('/token', methods=['POST'])
def token():
    return not_implemented()

@bp.route('/login', methods=['POST'])
def login():
    return not_implemented()

@bp.route('/logout', methods=['POST'])
def logout():
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
