"""apps/api/routes/auth

API routes for authentication.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.common.errors import api_errors
from apps.api.models.campusauth import authenticate_client
from common.validation.flask import FlaskResponse, unpack_request, validate

# No url prefix because many external integrations requiring oauth2 
bp = Blueprint('auth', __name__, url_prefix='/')
# All routes in this blueprint can be called by a client without token auth
# but must be authenticated with a client id and secret
bp.before_request(authenticate_client)


def init_app(app: Flask | Blueprint) -> None:
    """Initialise emailotp routes with the given Flask app/blueprint."""
    otp.init_db()
    app.register_blueprint(bp)


@bp.post('/request')
@unpack_request
@validate(
    request=otp.OTPRequest.__annotations__,
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def request_otp(*_, **data: Unpack[otp.OTPRequest]) -> FlaskResponse:
    """Request a new OTP for email authentication."""
    email = data['email']
    # TODO: Validate email format
    # TODO: Check if email is already registered
    resp = emailotp.request(email)
    otp_code = str(resp.data)

    # Send OTP via email
    email_sender = create_email_sender(EMAIL_PROVIDER)
    resp = email_sender.send_email(
        recipient=email,
        subject=template.subject("Campus", otp_code),
        body=template.body("Campus", otp_code),
        html_body=template.html_body("Campus", otp_code)
    )
    return {"message": "OTP sent"}, 200

@bp.post('/verify')
@unpack_request
@validate(
    request=otp.OTPVerify.__annotations__,
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def verify_otp(*_, **data: Unpack[otp.OTPVerify]) -> FlaskResponse:
    """Verify an OTP for email authentication."""
    # TODO: Validate email format
    # TODO: Validate OTP format
    resp = emailotp.verify(**data)
    return {"message": "OTP verified"}, 200
