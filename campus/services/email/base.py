"""campus.services.email.base

Base classes for email sending services.
"""

from abc import abstractmethod
from typing import Any, Protocol, Sequence

EmailAddress = str


class EmailSenderInterface(Protocol):
    """Base class for email sending services."""

    @abstractmethod
    def send_email(
            self,
            recipient: EmailAddress,
            subject: str,
            body: str,
            html_body: str | None = None,
            attachments: Sequence[Any] | None = None
    ) -> dict:
        """Send an email to a recipient.

        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            body: Plain text email body
            html_body: Optional HTML formatted email body
            attachments: Optional list of attachment objects

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        ...