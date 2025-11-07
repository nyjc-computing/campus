"""campus.apps.api.routes.emailotp

API routes for the emailotp resource.
"""

import flask

from campus.common import flask as campus_flask
from campus.common.errors import api_errors
from campus.services.email import create_email_sender

bp = flask.Blueprint('emailotp', __name__, url_prefix='/emailotp')

EMAIL_PROVIDER = "smtp"


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise emailotp routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/request')
@campus_flask.unpack_request
def request_otp(email: str) -> campus_flask.JsonResponse:
    """Request a new OTP for email authentication."""
    from campus.api import resources
    from campus.model.emailotp import template

    # TODO: Validate email format
    # TODO: Check if email is already registered
    otp_code = resources.emailotp.request(email)

    # Send OTP via email
    email_sender = create_email_sender(EMAIL_PROVIDER)
    error = email_sender.send_email(
        recipient=email,
        subject=template.subject("Campus", otp_code),
        body=template.body("Campus", otp_code),
        html_body=template.html_body("Campus", otp_code)
    )
    if error:
        raise api_errors.InternalError(
            message=error["message"],
            error_message=str(error),
        )
    return {"message": "OTP sent"}, 200


@bp.post('/verify')
@campus_flask.unpack_request
def verify_otp(email: str, otp: str) -> campus_flask.JsonResponse:
    """Verify an OTP for email authentication."""
    from campus.api import resources

    # TODO: Validate email format
    # TODO: Validate OTP format
    resources.emailotp.verify(email=email, otp=otp)
    return {"message": "OTP verified"}, 200
