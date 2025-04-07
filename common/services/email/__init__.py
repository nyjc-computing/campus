"""common.services.email

Email sending services for Campus digital services.
"""
from .base import EmailSenderInterface


def create_email_sender() -> EmailSenderInterface:
    """Factory function to create an email sender service."""
    from .smtp import SMTPEmailSender
    return SMTPEmailSender(
        smtp_server="smtp.gmail.com",
        smtp_port=587
    )