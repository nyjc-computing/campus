"""common.utils.uid

Utility functions for generating unique identifiers (UIDs).
"""

import uuid

def generate_uid(length: int = 16) -> str:
    """Generate a unique identifier of specified length (default: 16 bytes).

    Args:
        length: Length of the UID (default: 16).

    Returns:
        A string containing the generated UID.
    """
    return str(uuid.uuid4())[:length]


def generate_category_uid(category: str, *, length: int = 16) -> str:
    """Generate a unique identifier of specified length (default: 16 bytes).

    Args:
        length: Length of the UID (default: 16).

    Returns:
        A string containing the generated UID.
    """
    return f"uid-{category}-{generate_uid(length)}"


def generate_user_uid(email: str) -> str:
    """Generate a unique identifier for a user based on their email.

    User UIDs are different from other UIDs since they are not arbitrarily
    generated and benefit from a consistent, recognisable, user-readable format.

    Args:
        email: The user's email address.

    Returns:
        A string containing the generated UID.
    """
    user_id, _ = email.split('@')
    return user_id
