"""campus.common.env

An environment proxy.

The module is expected to be widely imported throughout Campus.
It should be lightweight and have minimal dependencies.
"""

import os
import sys
from typing import Iterator

from campus.common.errors import api_errors

# Expected environment variables (for type checking)

# Codespaces environment variables
CODESPACES: str  # 'true' if running in GitHub Codespaces
CODESPACE_NAME: str  # name of the Codespace
GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str  # domain for port forwarding in Codespaces

CLIENT_ID: str
CLIENT_SECRET: str
DEPLOY: str
ENV: str  # deployment environment (development, staging, production)
HOSTNAME: str  # used for generating redirect_uris
PORT: str  # port for running development server
SECRET_KEY: str  # secret key for signing sessions and tokens
VAULTDB_URI: str  # PostgreSQL connection URI for vault service
WORKSPACE_DOMAIN: str  # Google Workspace domain

CAMPUS_OAUTH_REDIRECT_URI: str  # redirect_uri for integration providers

_env_module = sys.modules[__name__]


# Stubs for type checking
def get(name: str, default: str | None = None) -> str | None: ...
def getsecret(name: str, vault_label: str) -> str: ...


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
        if name in os.environ:
            return os.environ[name]
        return getattr(_env_module, name)

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
        from campus.auth if not set.

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
        # To facilitate deployment abstraction, env needs to be useable
        # in campus.auth without campus.auth being imported in any other
        # deployment.
        # So we import campus.auth here only within the campus.auth
        # deployment.
        from campus.auth import resources
        from campus.model import ClientAccess
        client_resource = resources.client[self.CLIENT_ID]
        if not client_resource.access.check(
                vault_label=vault_label,
                permission=ClientAccess.READ,
        ):
            raise api_errors.ForbiddenError(
                f"Access denied to vault label '{vault_label}'"
            )
        return resources.vault[vault_label][name]

    def keys(self) -> list[str]:
        """Get a list of all environment variable names.

        Returns:
            list[str]: List of environment variable names.
        """
        return list(os.environ.keys())


sys.modules[__name__] = EnvironmentProxy()  # type: ignore
