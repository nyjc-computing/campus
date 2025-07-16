"""apps.api.routes.emailotp

API routes for the emailotp resource.
"""

from flask import Blueprint, Flask

import campus.common.validation.flask as flask_validation
from campus.apps.campusauth import authenticate_client
from campus.apps.errors import api_errors
from campus.apps.models import emailotp
from campus.services.email import create_email_sender

from campus.apps.models.emailotp import template

bp = Blueprint('emailotp', __name__, url_prefix='/emailotp')
# All routes in this blueprint can be called by a client without token auth
# but must be authenticated with a client id and secret
bp.before_request(authenticate_client)

otpauth = emailotp.EmailOTPAuth()

EMAIL_PROVIDER = "smtp"


def init_app(app: Flask | Blueprint) -> None:
    """Initialise emailotp routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/request')
def request_otp() -> flask_validation.JsonResponse:
    """Request a new OTP for email authentication."""
    payload = flask_validation.validate_request_and_extract_json(
        emailotp.OTPRequest.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    email = payload['email']
    # TODO: Validate email format
    # TODO: Check if email is already registered
    otp_code = otpauth.request(email)

    # Send OTP via email
    email_sender = create_email_sender(EMAIL_PROVIDER)
    error = email_sender.send_email(
        recipient=email,
        subject=template.subject("Campus", otp_code),
        body=template.body("Campus", otp_code),
        html_body=template.html_body("Campus", otp_code)
    )
    if error:
        api_errors.raise_api_error(
            error["message"],
            status_code=500,
            error_message=str(error)
        )
    return {"message": "OTP sent"}, 200

@bp.post('/verify')
def verify_otp() -> flask_validation.JsonResponse:
    """Verify an OTP for email authentication."""
    # TODO: Validate email format
    # TODO: Validate OTP format
    payload = flask_validation.validate_request_and_extract_json(
        emailotp.OTPVerify.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    otpauth.verify(**payload)
    return {"message": "OTP verified"}, 200
