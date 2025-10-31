"""campus.common.env

An environment proxy.

The module is expected to be widely imported throughout Campus.
It should be lightweight and have minimal dependencies.
"""

import os
import sys
from typing import Iterator

# Expected environment variables (for type checking)

# Codespaces environment variables
CODESPACES: str  # 'true' if running in GitHub Codespaces
CODESPACE_NAME: str  # name of the Codespace
GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str  # domain for port forwarding in Codespaces

CLIENT_ID: str
CLIENT_SECRET: str
DEPLOY: str
HOSTNAME: str  # used for generating redirect_uris
PORT: str  # port for running development server
WORKSPACE_DOMAIN: str  # Google Workspace domain

CAMPUS_OAUTH_REDIRECT_URI: str  # redirect_uri for integration providers


class EnvironmentProxy:
    """Proxy object for environment variables.

    This class provides attribute-style access to environment variables.
    Getting, setting, deleting, and checking for attributes correspond
    to getting, setting, deleting, and checking for environment
    variables.
    """

    def __contains__(self, name: str) -> bool:
        """Check if environment variable is set.

        Args:
            name (str): Name of the environment variable.
        Returns:
            bool: True if the environment variable is set, False
            otherwise.
        """
        return name in os.environ

    def __delattr__(self, name: str) -> None:
        """Delete environment variable by name.

        Args:
            name (str): Name of the environment variable.
        """
        if name in os.environ:
            del os.environ[name]

    def __getattr__(self, name: str) -> str:
        """Get environment variable by name.

        Args:
            name (str): Name of the environment variable.

        Returns:
            str: Value of the environment variable.

        Raises:
            KeyError: If the environment variable is not set.
        """
        return os.environ[name]

    def __iter__(self) -> Iterator[str]:
        """Iterate over environment variable names.

        Returns:
            Iterator[str]: An iterator over the names of the environment variables.
        """
        return iter(os.environ)

    def __setattr__(self, name: str, value: str) -> None:
        """Set environment variable by name.

        Args:
            name (str): Name of the environment variable.
            value (str): Value to set.
        """
        os.environ[name] = value

    def get(self, name: str, default: str | None = None) -> str | None:
        """Get environment variable by name.

        Args:
            name (str): Name of the environment variable.
            default (str | None): Default value to return if not set.

        Returns:
            str | None: Value of the environment variable, or default if
            not set.
        """
        return os.getenv(name, default)

    def getsecret(self, name: str, vault_label: str) -> str:
        """Get environment variable by name, falling back to retrieval
        from campus.vault if not set.

        Args:
            name (str): Name of the environment variable.
            vault_label (str): Label to use when retrieving from vault.

        Returns:
            str: Value of the environment variable or vault secret.

        Raises:
            OSError: If neither environment variable nor vault secret is
            found.
            access.PermissionError: If access to the vault label is
            denied.
        """
        if name in self:
            return getattr(self, name)
        from campus.vault import access, get_vault
        access.raise_for_access(
            self.CLIENT_ID,
            vault_label,
            access.READ
        )
        vault = get_vault(vault_label)
        return vault.get(name)

    def keys(self) -> list[str]:
        """Get a list of all environment variable names.

        Returns:
            list[str]: List of environment variable names.
        """
        return list(os.environ.keys())


sys.modules[__name__] = EnvironmentProxy()  # type: ignore
