"""services.email.smtp

SMTP email sending service.
"""

import smtplib
from email.message import EmailMessage
from typing import Any, Sequence

from services.vault import get_vault

from .base import EmailSenderInterface


class SMTPEmailSender(EmailSenderInterface):
    """SMTP email sending service."""

    def __init__(
            self,
            smtp_server: str,
            smtp_port: int
    ) -> None:
        """Initialize the SMTPEmailSender with server details."""
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[Any] | None = None
    ) -> dict:
        """Send an email to a recipient via SMTP.
    
        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            body: Plain text email body
            html_body: Optional HTML formatted email body
            attachments: Optional list of attachment objects
    
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        vault = get_vault("smtp")
        username = vault.get('SMTP_USERNAME')
        password = vault.get('SMTP_PASSWORD')
        host = vault.get('SMTP_HOST')

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = recipient
        msg.set_content(body)

        if html_body:
            msg.add_alternative(html_body, subtype='html')

        try:
            # Using with-statement to ensure the connection is closed after use
            with smtplib.SMTP(host) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

        except Exception as err:
            return {"message": err.args}
        else:
            return {}
