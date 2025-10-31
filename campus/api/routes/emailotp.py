"""campus.apps.api.routes.emailotp

API routes for the emailotp resource.
"""

import flask

from campus.common import flask as campus_flask
from campus.common.errors import api_errors
from campus.models import emailotp
from campus.services.email import create_email_sender

bp = flask.Blueprint('emailotp', __name__, url_prefix='/emailotp')

otpauth = emailotp.EmailOTPAuth()

EMAIL_PROVIDER = "smtp"


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise emailotp routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/request')
@campus_flask.unpack_request
def request_otp(email: str) -> campus_flask.JsonResponse:
    """Request a new OTP for email authentication."""
    # TODO: Validate email format
    # TODO: Check if email is already registered
    otp_code = otpauth.request(email)

    # Send OTP via email
    email_sender = create_email_sender(EMAIL_PROVIDER)
    error = email_sender.send_email(
        recipient=email,
        subject=emailotp.template.subject("Campus", otp_code),
        body=emailotp.template.body("Campus", otp_code),
        html_body=emailotp.template.html_body("Campus", otp_code)
    )
    if error:
        api_errors.raise_api_error(
            error["message"],
            status_code=500,
            error_message=str(error)
        )
    return {"message": "OTP sent"}, 200


@bp.post('/verify')
@campus_flask.unpack_request
def verify_otp(email: str, otp: str) -> campus_flask.JsonResponse:
    """Verify an OTP for email authentication."""
    # TODO: Validate email format
    # TODO: Validate OTP format
    otpauth.verify(email=email, otp=otp)
    return {"message": "OTP verified"}, 200
