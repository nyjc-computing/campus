"""campus.client.vault.vault

Main vault client interface for secrets management and access control.
"""

import logging
from campus.client.interface import Resource
from campus.common.http import JsonClient

from .access import VaultAccessResource
from .client import VaultClientResource

logger = logging.getLogger(__name__)


class VaultKeyResource(Resource):
    """Represents a specific key in a vault collection."""

    def get(self) -> dict:
        """Get the secret value."""
        logger.debug(f"Vault GET request: {self.path}")
        try:
            response = self.client.get(self.path)
            logger.debug(f"Vault GET response: {response.status_code}")
            return self._process_response(response)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Vault GET failed for {self.path}: {e}")
            raise

    def set(self, *, value: str) -> dict:
        """Set the secret value."""
        logger.debug(f"Vault SET request: {self.path}")
        data = {"value": value}
        try:
            response = self.client.post(self.path, data)
            logger.debug(f"Vault SET response: {response.status_code}")
            return self._process_response(response)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Vault SET failed for {self.path}: {e}")
            raise

    def delete(self) -> dict:
        """Delete the secret."""
        logger.debug(f"Vault DELETE request: {self.path}")
        try:
            response = self.client.delete(self.path)
            logger.debug(f"Vault DELETE response: {response.status_code}")
            return self._process_response(response)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Vault DELETE failed for {self.path}: {e}")
            raise


class Vault(Resource):
    """Represents a single vault, a collection of vault keys."""

    def __getitem__(self, key: str) -> VaultKeyResource:
        """Get a specific key in this vault collection.

        Args:
            key: The secret key name

        Returns:
            VaultKey: Object for accessing the specific secret
        """
        return VaultKeyResource(self, key)

    def list(self) -> dict:
        """List all keys in the vault.

        Returns:
            List of key names
        """
        logger.debug(f"Vault LIST request: {self.path}")
        try:
            response = self.client.get(self.path)
            logger.debug(f"Vault LIST response: {response.status_code}")
            return self._process_response(response)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Vault LIST failed for {self.path}: {e}")
            raise


class VaultResource(Resource):
    """Resource for Campus /vault endpoint."""

    def __init__(self, client: JsonClient, *, raw: bool = False):
        super().__init__(client, "vault", raw=raw)
        self._access_resource = None
        self._clients_resource = None

    def __getitem__(self, label: str) -> Vault:
        """Get a vault collection by label.

        Args:
            label: The vault label (e.g., "apps", "storage", "oauth")
        """
        return Vault(self, label)

    def list(self) -> dict:
        """List available vault labels.

        Returns:
            List of available vault labels
        """
        logger.debug(f"Vault LABELS request: {self.path}")
        try:
            response = self.client.get(self.path)
            logger.debug(f"Vault LABELS response: {response.status_code}")
            return self._process_response(response)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Vault LABELS failed for {self.path}: {e}")
            raise

    @property
    def access(self) -> VaultAccessResource:
        """Vault access resource."""
        if self._access_resource is None:
            self._access_resource = VaultAccessResource(self, "access")
        return self._access_resource

    @property
    def clients(self) -> VaultClientResource:
        """Vault clients resource."""
        if self._clients_resource is None:
            self._clients_resource = VaultClientResource(self, "clients")
        return self._clients_resource
