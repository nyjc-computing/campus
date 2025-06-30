"""apps.api.models.otp

This module provides classes and utilities for handling one-time
passwords (OTPs) used in email authentication. It includes functionality
generating, hashing, verifying, and managing OTPs securely.
"""
import os
import secrets
from typing import TypedDict, Unpack

import bcrypt

from apps.api.models.base import BaseRecord, ModelResponse
from apps.common.errors import api_errors
from common import devops
from common.schema import Message, Response
from common.utils import uid, utc_time
if devops.ENV in (devops.STAGING, devops.PRODUCTION):
    from common.drum.postgres import get_conn, get_drum
else:
    from common.drum.sqlite import get_conn, get_drum

TABLE = "emailotp"


def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    # TODO: Refactor into decorator
    if os.getenv('ENV', 'development') == 'production':
        raise AssertionError(
            "Database initialization detected in production environment"
        )
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emailotp (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
    except Exception:  # pylint: disable=try-except-raise
        # init_db() is not expected to be called in production, so we don't
        # need to handle errors gracefully.
        raise
    else:
        conn.commit()
    finally:
        conn.close()


class _plainOTP(str):
    """
    Represents a plaintext OTP for authentication.

    Provides methods to generate a secure OTP and hash it for secure storage.
    """

    @classmethod
    def generate(cls, length: int = 6) -> "_plainOTP":
        """
        Generate a secure random OTP of specified length (default: 6 digits).

        Args:
            length: Length of the OTP (default: 6).

        Returns:
            A string containing the generated OTP.
        """
        passcode: int = secrets.randbelow(10 ** length)
        return _plainOTP(f"{passcode:0{length}d}")

    def hash(self) -> "_hashedOTP":
        """
        Hash the OTP using bcrypt for secure storage.

        Returns:
            A hashedOTP instance containing the hashed OTP.
        """
        otp_bytes = self.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(otp_bytes, salt)
        return _hashedOTP(hashed.decode('utf-8'))


class _hashedOTP(str):
    """
    Represents a hashed OTP for verification.

    Provides a method to verify if a plaintext OTP matches the hashed OTP.
    """

    def verify(self, plain_otp: "_plainOTP") -> bool:
        """
        Verify if a plaintext OTP matches this hashed OTP.

        Args:
            plain_otp: The plaintext OTP to verify.

        Returns:
            True if the plaintext OTP matches the hashed OTP, False otherwise.
        """
        plain_bytes = plain_otp.encode('utf-8')
        hashed_bytes = self.encode('utf-8')
        return bcrypt.checkpw(plain_bytes, hashed_bytes)


class OTPRequest(TypedDict, total=True):
    """Request body schema for an emailotp.new operation."""
    email: str


class OTPVerify(OTPRequest, total=True):
    """Request body schema for an emailotp.verify operation."""
    otp: str


class OTPRecord(OTPRequest, BaseRecord, total=True):
    """Schema for a complete OTP record.
    Currently unused in the API, provided for documentation purpose.
    """
    otp_hash: str
    expires_at: utc_time.datetime


class OTPAuth:
    """
    OTP model for handling database operations related to one-time passwords.

    Provides methods to create, verify, and delete OTPs associated with email addresses.
    """

    def __init__(self):
        """Initialize the OTP model with a storage interface.

        Args:
            storage: Implementation of StorageInterface for database operations.
        """
        self.storage = get_drum()

    def request(self, email: str, expiry_minutes: int | float = 5) -> ModelResponse:
        """
        Generate a new OTP for the given email, store or update it in the database, and return it.

        Args:
            email: Email address to associate with the OTP.
            expiry_minutes: Expiration time in minutes (default: 5).

        Returns:
            The plaintext OTP (to be sent to the user).
        """
        # Generate a new OTP
        plain_otp = _plainOTP.generate()
        # Hash the OTP for secure storage
        otp_hash = plain_otp.hash()
        # Set expiration and creation times
        created_at = utc_time.now()
        expires_at = utc_time.after(minutes=expiry_minutes)

        # Delete any existing OTP for this email
        resp = self.storage.delete_by_id('otp_codes', email)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
        # Insert new OTP
        otp_id = uid.generate_category_uid(TABLE, length=16)
        otp_code = OTPRecord(
            id=otp_id,
            email=email,
            otp_hash=otp_hash,
            created_at=created_at,
            expires_at=expires_at,
        )
        resp = self.storage.insert('otp_codes', otp_code)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.CREATED):
                return ModelResponse("ok", "OTP created", plain_otp)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def verify(self, **data: Unpack[OTPVerify]) -> ModelResponse:
        """
        Verify if the provided OTP matches the one stored for the email.

        Args:
            email: Email address to check.
            plain_otp: Plaintext OTP to verify.

        Returns:
            ModelResponse indicating the result of the verification.
        """
        # Get the latest OTP for this email
        resp = self.storage.get_by_id('otp_codes', data['email'])
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError("OTP not found")

        _, _, record = resp
        assert isinstance(record, dict)  # appeasing mypy gods
        hashed_otp = _hashedOTP(record['otp_hash'])
        expires_at = record['expires_at']

        # Convert expires_at to datetime if it's a string
        if isinstance(expires_at, str):
            expires_at = utc_time.from_rfc3339(expires_at)

        # Check if OTP is expired
        if utc_time.is_expired(expires_at):
            raise api_errors.UnauthorizedError("OTP expired")

        # Verify OTP
        if hashed_otp.verify(_plainOTP(data['otp'])):
            return ModelResponse("ok", "OTP verified")
        else:
            raise api_errors.UnauthorizedError("Invalid OTP")

    def revoke(self, email: str) -> ModelResponse:
        """
        Delete all OTPs for the given email (typically after successful verification).

        Args:
            email: Email address to delete OTPs for.
        """
        resp = self.storage.delete_by_id('otp_codes', email)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError("OTP not found")
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse("ok", "OTP deleted")
            case _:
                raise ValueError(f"Unexpected case: {resp}")
