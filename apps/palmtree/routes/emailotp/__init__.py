from flask import Blueprint, request

from apps.palmtree.models import otp
from common.schema import Message, Response
from common.services.email import create_email_sender

from . import template

bp = Blueprint('emailotp', __name__, url_prefix='/emailotp')

otp_auth = otp.OTPAuth()

EMAIL_PROVIDER = "smtp"


def init_app(app) -> None:
    otp.init_db()
    app.register_blueprint(bp)


@bp.post('/request')
def request_otp():
    """Request a new OTP for email authentication."""
    if not request.is_json:
        return {"error": "Request must be JSON"}, 400
    payload = request.get_json()
    if 'email' not in payload:
        return {"error": "Missing email"}, 400
    email = payload['email']
    # TODO: Validate email format
    # TODO: Check if email is already registered
    resp = otp_auth.create(email)
    match resp:
        case Response(status="error", message=msg, data=err):
            return {"error": f"{msg}: {err}"}, 500
        case Response(status="ok", message=Message.CREATED, data=otp_code):
            otp_code = str(otp_code)
        case _:
            raise ValueError(f"Unexpected case: {resp}")

    # Send OTP via email
    email_sender = create_email_sender(EMAIL_PROVIDER)
    resp = email_sender.send_email(
        recipient=email,
        subject=template.subject("Campus", otp_code),
        body=template.body("Campus", otp_code),
        html_body=template.html_body("Campus", otp_code)
    )
    match resp:
        case Response(status="error", message=msg, data=err):
            return {"error": f"{msg}: {err}"}, 500
        case Response(status="ok", message=Message.SUCCESS, data=_):
            return {"message": "OTP sent"}, 200
        case _:
            raise ValueError(f"Unexpected case: {resp}")

@bp.post('/verify')
def verify_otp():
    """Verify an OTP for email authentication."""
    if not request.is_json:
        return {"error": "Request must be JSON"}, 400
    payload = request.get_json()
    if 'email' not in payload or 'otp' not in payload:
        return {"error": "Missing email or otp"}, 400
    email = payload['email']
    otp_code = payload['otp']
    # TODO: Validate email format
    # TODO: Validate OTP format
    resp = otp_auth.verify(email, otp_code)
    match resp:
        case Response(status="error", message=msg, data=err):
            return {"error": f"{msg}: {err}"}, 500
        case Response(status="ok", message=Message.VALID, data=_):
            return {"message": "OTP verified"}, 200
        case _:
            raise ValueError(f"Unexpected case: {resp}")

