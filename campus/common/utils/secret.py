"""campus.common.utils.secret

Utility functions for generating and hashing secrets.
"""

import base64
import hashlib
import hmac
import secrets

import bcrypt


def decode_http_basic_auth(header_value: str) -> tuple[str, str]:
    """Decode an HTTP Basic Auth header value into username and password.

    Args:
        header_value: The value of the Authorization header (e.g., 'Basic ...').

    Returns:
        A tuple of (username, password).
    Raises:
        ValueError: If the header is not a valid Basic Auth header.
    """
    if not header_value.lower().startswith("basic "):
        raise ValueError("Not a Basic Auth header")
    b64 = header_value[6:].strip()
    decoded = base64.b64decode(b64).decode("utf-8")
    if ':' not in decoded:
        raise ValueError("Invalid Basic Auth credentials")
    username, password = decoded.split(':', 1)
    return username, password

def encode_http_basic_auth(username: str, password: str) -> str:
    """Encode username and password into an HTTP Basic Auth header value.

    Args:
        username: The username (or client_id).
        password: The password (or client_secret).

    Returns:
        The value for the Authorization header (e.g., 'Basic ...').
    """
    credentials = f"{username}:{password}".encode("utf-8")
    b64 = base64.b64encode(credentials).decode("utf-8")
    return f"Basic {b64}"

def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key.

    The API key is URL-safe, unique, and uses a cryptographically secure random number generator.

    Args:
        length: Length of the API key (default: 32).

    Returns:
        A string containing the generated API key.
    """
    return secrets.token_urlsafe(length)

def generate_authorization_code() -> str:
    """Generate an OAuth2 authorization code"""
    return secrets.token_urlsafe(32)

def generate_client_secret(length: int = 64) -> str:
    """Generate a secure random client secret.

    The secret is URL-safe and uses a cryptographically secure random number generator.

    Args:
        length: Length of the client secret (default: 64).

    Returns:
        A string containing the generated client secret.
    """
    return secrets.token_urlsafe(length)

def generate_otp(length: int = 6) -> str:
    """Generate a secure random OTP of specified length (default: 6 digits).

    Args:
        length: Length of the OTP (default: 6).

    Returns:
        A string containing the generated OTP.
    """
    passcode: int = secrets.randbelow(10 ** length)
    return f"{passcode:0{length}d}"

def hash_client_secret(secret: str, key: str) -> str:
    """Hash the client secret using HMAC for secure storage.

    Args:
        secret: The client secret to hash.
        key: The HMAC key used for hashing (default: "default_hmac_key").

    Returns:
        A base64-encoded HMAC hash of the client secret.
    """
    hmac_key = key.encode('utf-8')
    secret_bytes = secret.encode('utf-8')
    hmac_hash = hmac.new(hmac_key, secret_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(hmac_hash).decode('utf-8')

def hash_otp(otp: str) -> str:
    """Hash the OTP using bcrypt for secure storage.

    Returns:
        A hashedOTP instance containing the hashed OTP.
    """
    otp_bytes = otp.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(otp_bytes, salt)
    return hashed.decode('utf-8')

def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify if a plaintext OTP matches this hashed OTP.

    Args:
        plain_otp: The plaintext OTP to verify.
        hashed_otp: The hashed OTP to compare against.

    Returns:
        True if the plaintext OTP matches the hashed OTP, False otherwise.
    """
    plain_bytes = plain_otp.encode('utf-8')
    hashed_bytes = hashed_otp.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)
