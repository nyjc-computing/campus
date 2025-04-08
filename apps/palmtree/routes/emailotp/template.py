"""apps.palmtree.routes.emailotp.template

Email templates for OTP authentication.
"""

from flask import render_template_string

with open("templates/email.txt") as f:
    plaintext_template = f.read().strip()

with open("templates/email.html") as f:
    html_template = f.read().strip()


def subject(service: str, otp: str) -> str:
    """Email subject for OTP authentication."""
    return f"{service.title()}: Your OTP is {otp}"

def body(service: str, otp: str) -> str:
    """Plaintext email body for OTP authentication."""
    return render_template_string(
        plaintext_template,
        service=service,
        otp=otp
    )

def html_body(service: str, otp: str) -> str:
    """HTML email body for OTP authentication."""
    return render_template_string(
        html_template,
        service=service,
        otp=otp
    )

