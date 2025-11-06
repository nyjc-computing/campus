"""campus.model.emailotp

Email OTP model for the Campus API.

This module defines one-time password records for email authentication.
"""

from dataclasses import dataclass

from campus.common import schema

from .base import Model


@dataclass(eq=False, kw_only=True)
class EmailOTP(Model):
    """Dataclass representation of an email OTP record."""
    id: schema.CampusID  # type: ignore
    # created_at inherited from Model
    email: schema.Email
    otp_hash: str
    expires_at: schema.DateTime
