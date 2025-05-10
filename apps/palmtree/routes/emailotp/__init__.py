from flask import Blueprint, request

from apps.palmtree.models import otp
from common.auth import authenticate_client
from common.services.email import create_email_sender

from . import template

bp = Blueprint('emailotp', __name__, url_prefix='/emailotp')
# All routes in this blueprint can be called by a client without a user token
# but must be authenticated with a client id and secret
bp.before_request(authenticate_client)

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
    resp = otp_auth.new(email)
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
    return {"message": "OTP verified"}, 200
