"""campus.api.resources.emailotp

Email OTP resource for Campus API.
"""

import secrets
import typing

import bcrypt

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
import campus.model
import campus.storage

emailotp_storage = campus.storage.get_table("emailotp")


class _plainOTP(str):
    """Represents a plaintext OTP for authentication."""

    @classmethod
    def generate(cls, length: int = 6) -> "_plainOTP":
        """Generate a secure random OTP of specified length."""
        passcode: int = secrets.randbelow(10 ** length)
        return _plainOTP(f"{passcode:0{length}d}")

    def hash(self) -> str:
        """Hash the OTP using bcrypt for secure storage."""
        otp_bytes = self.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(otp_bytes, salt)
        return hashed.decode('utf-8')


def _verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify if a plaintext OTP matches the hashed OTP."""
    plain_bytes = plain_otp.encode('utf-8')
    hashed_bytes = hashed_otp.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.EmailOTP:
    """Convert a storage record to an EmailOTP model instance."""
    return campus.model.EmailOTP(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        email=schema.Email(record['email']),
        otp_hash=record['otp_hash'],
        expires_at=schema.DateTime(record['expires_at'])
    )


class EmailOTPResource:
    """Represents the email OTP resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for email OTP management."""
        emailotp_storage.init_from_model("emailotp", campus.model.EmailOTP)

    def request(self, email: str, expiry_minutes: int | float = 5) -> str:
        """Generate a new OTP for the given email and return it.

        Args:
            email: Email address to associate with the OTP
            expiry_minutes: Expiration time in minutes (default: 5)

        Returns:
            The plaintext OTP (to be sent to the user)

        Raises:
            ConflictError: If OTP conflict during insert
            InternalError: For other errors
        """
        # Generate a new OTP
        plain_otp = _plainOTP.generate()
        otp_hash = plain_otp.hash()

        # Set expiration and creation times
        now = schema.DateTime.utcnow()
        created_at = now
        expires_at = schema.DateTime.utcafter(now, minutes=expiry_minutes)

        try:
            # Delete any existing OTP for this email
            try:
                existing_otps = emailotp_storage.get_matching({"email": email})
            except campus.storage.errors.NotFoundError:
                existing_otps = []

            for otp_record in existing_otps:
                try:
                    emailotp_storage.delete_by_id(
                        otp_record[schema.CAMPUS_KEY])
                except campus.storage.errors.NotFoundError:
                    continue

            # Insert new OTP
            otp_id = uid.generate_category_uid("emailotp", length=16)
            otp = campus.model.EmailOTP(
                id=otp_id,
                email=schema.Email(email),
                otp_hash=otp_hash,
                created_at=created_at,
                expires_at=expires_at,
            )

            try:
                emailotp_storage.insert_one(otp.to_storage())
            except campus.storage.errors.ConflictError:
                raise api_errors.ConflictError(
                    "OTP conflict during insert",
                    email=email
                ) from None

            return plain_otp

        except api_errors.APIError:
            raise  # Re-raise API errors as-is
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e

    def verify(self, email: str, otp: str) -> None:
        """Verify if the provided OTP matches the one stored for the email.

        Args:
            email: Email address to check
            otp: Plaintext OTP to verify

        Raises:
            ConflictError: If OTP not found
            UnauthorizedError: If OTP is expired or invalid
            InternalError: For other errors
        """
        try:
            # Get the latest OTP for this email
            try:
                otp_records = emailotp_storage.get_matching({"email": email})
            except campus.storage.errors.NotFoundError:
                raise api_errors.ConflictError("OTP not found")

            # Get the most recent OTP record
            if not otp_records:
                raise api_errors.ConflictError("OTP not found")

            record = otp_records[0]
            hashed_otp = record['otp_hash']
            expires_at = schema.DateTime(record['expires_at'])

            # Check if OTP is expired
            if utc_time.is_expired(expires_at.to_datetime()):
                raise api_errors.UnauthorizedError("OTP expired")

            # Verify OTP
            if not _verify_otp(otp, hashed_otp):
                raise api_errors.UnauthorizedError("Invalid OTP")

        except api_errors.APIError:
            raise  # Re-raise API errors as-is
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e

    def revoke(self, email: str) -> None:
        """Delete all OTPs for the given email.

        Args:
            email: Email address to delete OTPs for

        Raises:
            ConflictError: If OTP not found
            InternalError: For other errors
        """
        try:
            # Find all OTPs for this email
            try:
                otp_records = emailotp_storage.get_matching({"email": email})
            except campus.storage.errors.NotFoundError:
                raise api_errors.ConflictError("OTP not found")

            # Delete all OTP records for this email
            for record in otp_records:
                try:
                    emailotp_storage.delete_by_id(record[schema.CAMPUS_KEY])
                except campus.storage.errors.NotFoundError:
                    continue

        except api_errors.APIError:
            raise  # Re-raise API errors as-is
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
