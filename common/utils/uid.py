"""common.utils.uid.py

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

