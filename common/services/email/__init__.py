"""common.services.email

Email sending services for Campus digital services.
"""
from .base import EmailSenderInterface


def create_email_sender(emailtype: str) -> EmailSenderInterface:
    """Factory function to create an email sender service."""
    match emailtype:
        case "smtp":
            from .smtp import SMTPEmailSender
            return SMTPEmailSender(
                smtp_server="smtp.gmail.com",
                smtp_port=587
            )
        case _:
            raise ValueError(f"Unknown email type: {emailtype}")

