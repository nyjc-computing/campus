"""campus.common.env

An environment proxy.
"""

import os
import sys


class EnvironmentProxy:
    """Proxy object for environment variables.

    This class provides attribute-style access to environment variables.
    Getting, setting, deleting, and checking for attributes correspond to
    getting, setting, deleting, and checking for environment variables.
    """

    def __contains__(self, name: str) -> bool:
        """Check if environment variable is set.

        Args:
            name (str): Name of the environment variable.
        Returns:
            bool: True if the environment variable is set, False otherwise.
        """
        return name in os.environ


    def __delattr__(self, name: str):
        """Delete environment variable by name.

        Args:
            name (str): Name of the environment variable.
        """
        if name in os.environ:
            del os.environ[name]


    def __getattr__(self, name: str) -> str | None:
        """Get environment variable by name.

        Args:
            name (str): Name of the environment variable.

        Returns:
            str | None: Value of the environment variable, or None if not set.
        """
        return os.getenv(name)


    def __iter__(self):
        """Iterate over environment variable names.

        Returns:
            Iterator[str]: An iterator over the names of the environment variables.
        """
        return iter(os.environ)


    def __setattr__(self, name: str, value: str):
        """Set environment variable by name.

        Args:
            name (str): Name of the environment variable.
            value (str): Value to set.
        """
        os.environ[name] = value


    def keys(self) -> list[str]:
        """Get a list of all environment variable names.

        Returns:
            list[str]: List of environment variable names.
        """
        return list(os.environ.keys())


sys.modules[__name__] = EnvironmentProxy()  # type: ignore
