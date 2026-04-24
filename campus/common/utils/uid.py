"""campus.common.utils.uid

Utility functions for generating unique identifiers (UIDs).
"""

import uuid

from campus.common import schema

def generate_uid(length: int = 16) -> str:
    """Generate a unique identifier of specified length (default: 16 bytes).

    Args:
        length: Length of the UID (default: 16).

    Returns:
        A string containing the generated UID.
    """
    return str(uuid.uuid4())[:length]


def generate_category_uid(
        category: str,
        *,
        length: int = 16
) -> schema.CampusID:
    """Generate a unique identifier of specified length (default: 16 bytes).

    Args:
        length: Length of the UID (default: 16).

    Returns:
        A string containing the generated UID.
    """
    return schema.CampusID(f"uid-{category}-{generate_uid(length)}")


def generate_user_uid(email: str) -> schema.UserID:
    """Generate a unique identifier for a user based on their email.

    User UIDs are different from other UIDs since they are not arbitrarily
    generated and benefit from a consistent, recognisable, user-readable format.

    Args:
        email: The user's email address.

    Returns:
        A string containing the generated UID.
    """
    user_id, _ = email.split('@')
    return schema.UserID(user_id)


def generate_trace_id() -> str:
    """Generate a 32-char hex trace ID (OpenTelemetry-compatible).

    OpenTelemetry trace IDs are 128-bit values represented as 32 lowercase hex characters.

    Returns:
        A 32-character hexadecimal string.
    """
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a 16-char hex span ID (OpenTelemetry-compatible).

    OpenTelemetry span IDs are 64-bit values represented as 16 lowercase hex characters.

    Returns:
        A 16-character hexadecimal string.
    """
    return uuid.uuid4().hex[:16]
