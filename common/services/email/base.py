"""common.services.email.base.py

Base classes for email sending services.
"""

from abc import abstractmethod
from typing import Any, Literal, NamedTuple, Protocol, Sequence

EmailAddress = str


class EmailResponse(NamedTuple):
    """Represents a response from an email sending operation."""
    status: Literal["ok", "error"]
    message: str
    data: Any | None = None


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
    ) -> EmailResponse:
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
        pass