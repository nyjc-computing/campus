"""campus.api.routes.emailotp

API routes for the emailotp resource.
"""

import re

import flask

from campus import flask_campus
from campus.common.errors import api_errors
from campus.common.errors.validation import FieldError, ValidationError
from campus.services.email import create_email_sender

bp = flask.Blueprint('emailotp', __name__, url_prefix='/emailotp')

EMAIL_PROVIDER = "smtp"

# Minimal RFC-ish shape check: one @, non-empty local part, dotted
# domain with a non-empty TLD. Deliberately permissive — deep email
# validation is a known rabbit hole and not this endpoint's job.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> None:
    """Reject empty or malformed emails with a 422 VALIDATION_FAILED."""
    if not _EMAIL_RE.match(email):
        raise ValidationError(
            "email must be a valid email address",
            errors=[FieldError(
                field="email",
                code="INVALID_FORMAT",
                message="email must be a non-empty address of the form "
                        "local@domain.tld"
            )]
        )


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise emailotp routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/request')
@flask_campus.unpack_request
def request_otp(email: str) -> flask_campus.JsonResponse:
    """Request a new OTP for email authentication."""
    from campus.api import resources
    from campus.model.emailotp import template

    _validate_email(email)
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
        raise api_errors.ServiceUnavailableError(
            message="Failed to send OTP email; try again later",
            error_message=str(error),
        )
    return {"message": "OTP sent"}, 200


@bp.post('/verify')
@flask_campus.unpack_request
def verify_otp(email: str, otp: str) -> flask_campus.JsonResponse:
    """Verify an OTP for email authentication."""
    from campus.api import resources

    _validate_email(email)
    resources.emailotp.verify(email=email, otp=otp)
    return {"message": "OTP verified"}, 200
