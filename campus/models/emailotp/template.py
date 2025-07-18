"""apps.api.routes.emailotp.template

Email templates for OTP authentication.
"""

import os

from flask import render_template_string

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

# Defer template loading for quick instance startup
plaintext_template = ""
html_template = ""

def load_plaintext_template() -> None:
    """Load the plaintext email template from file."""
    global plaintext_template
    with open(os.path.join(TEMPLATE_DIR, "email.txt")) as f:
        plaintext_template = f.read().strip()

def load_html_template() -> None:
    """Load the HTML email template from file."""
    global html_template
    with open(os.path.join(TEMPLATE_DIR, "email.html")) as f:
        html_template = f.read().strip()


def subject(service: str, otp: str) -> str:
    """Email subject for OTP authentication."""
    return f"{service.title()}: Your OTP is {otp}"

def body(service: str, otp: str) -> str:
    """Plaintext email body for OTP authentication."""
    if not plaintext_template:
        load_plaintext_template()
    return render_template_string(
        plaintext_template,
        service=service,
        otp=otp
    )

def html_body(service: str, otp: str) -> str:
    """HTML email body for OTP authentication."""
    if not html_template:
        load_html_template()
    return render_template_string(
        html_template,
        service=service,
        otp=otp
    )
