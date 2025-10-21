"""campus.common.env

An environment proxy object.
"""

import os


def __getattr__(name: str) -> str | None:
    """Get environment variable by name.

    Args:
        name (str): Name of the environment variable.

    Returns:
        str | None: Value of the environment variable, or None if not set.
    """

    return os.getenv(name)
