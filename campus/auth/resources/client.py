"""campus.auth.resources.client

Client resource for Campus API.
"""

__all__ = []

import typing

from campus.common import env, schema
from campus.common.errors import auth_errors
from campus.common.utils import secret, uid
import campus.model
import campus.storage

client_storage = campus.storage.get_table("vault_clients")
access_storage = campus.storage.get_table("vault_access")


def _from_record(
        record: dict[str, typing.Any],
        permissions: dict[str, int] | None = None
) -> campus.model.Client:
    """Convert a storage record to a Client model instance."""
    return campus.model.Client(
        id=schema.CampusID(
            record.get("id", uid.generate_category_uid("client"))
        ),
        created_at=schema.DateTime(
            record.get("created_at", schema.DateTime.utcnow())
        ),
        name=record['name'],
        description=record['description'],
        permissions=permissions or {}
    )


def _get_client_permissions(client_id: schema.CampusID) -> dict[str, int]:
    """Get a client's vault access permissions.

    Args:
        client_id: The client identifier

    Returns:
        Dictionary mapping vault labels to permission bitflags
    """
    access_records = access_storage.get_matching({"client_id": client_id})
    permissions: dict[str, int] = {}
    for record in access_records:
        label = schema.String(record['label'])
        access_flag = schema.Integer(record['access'])
        permissions[label] = access_flag
    return permissions


class ClientsResource:
    """Represents the clients resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for client authentication."""
        client_storage.init_from_model("clients", campus.model.Client)
        access_storage.init_from_model(
            "vault_access", campus.model.ClientAccess
        )

    def __getitem__(
            self,
            client_id: schema.CampusID
    ) -> "ClientResource":
        """Get a client resource by client ID.

        Args:
            client_id: The vault client ID

        Returns:
            ClientResource instance
        """
        return ClientResource(client_id)

    def raise_for_authentication(
            self,
            client_id: schema.CampusID,
            client_secret: str
    ) -> None:
        """Authenticate a client using their ID and secret.
        Pushes the authenticated client into flask.g.current_client if
        successful, otherwise raises an authentication error.

        Args:
            client_id: The client identifier
            client_secret: The client secret

        Raises:
            UnauthorizedError: If client not found or client secret is invalid
        """
        client = self[client_id].get()
        if not client.secret_hash:
            raise auth_errors.ServerError(
                "Invalid configuration",
                client_id=client_id
            )
        expected_hash = secret.hash_client_secret(
            client_secret,
            env.getsecret("SECRET_KEY", env.DEPLOY)
        )
        if client.secret_hash != expected_hash:
            raise auth_errors.UnauthorizedClientError(
                "Invalid credentials",
                client_id=client_id
            )

    def list_all(self) -> list[campus.model.Client]:
        """List all clients.

        Returns:
            List of Client instances
        """
        records = client_storage.get_matching({})
        clients = []
        for record in records:
            client_id = schema.CampusID(record['id'])
            permissions = _get_client_permissions(client_id)
            client = _from_record(
                record=record,
                permissions=permissions
            )
            clients.append(client)
        return clients

    def new(
            self,
            **kwargs: typing.Any
    ) -> campus.model.Client:
        """Create a new client and return it.

        Args:
            **kwargs: Additional fields for client creation

        Returns:
            Client instance
        """
        client = _from_record(kwargs)
        client_storage.insert_one(client.to_storage())
        return client


class ClientResource:
    """Represents a single client in Campus API Schema."""

    def __init__(self, client_id: schema.CampusID):
        self.client_id = client_id

    @property
    def access(self) -> "ClientAccessResource":
        """Get the client access resource.

        Returns:
            ClientAccessResource instance
        """
        return ClientAccessResource(self)

    def delete(self) -> None:
        """Delete the client record."""
        client_storage.delete_by_id(self.client_id)

    def get(self) -> campus.model.Client:
        """Get the client record.

        Returns:
            ClientRecord instance
        """
        client_id = self.client_id
        record = client_storage.get_by_id(client_id)
        if not record:
            raise auth_errors.InvalidRequestError(
                f"Client '{client_id}' not found",
                client_id=client_id
            )
        return _from_record(
            record=record,
            permissions=_get_client_permissions(client_id)
        )

    def revoke(self) -> str:
        """Revoke the client by deleting its secret.

        Returns:
            The generated client secret
        """
        # Check if client exists first
        self.get()
        new_secret = secret.generate_client_secret()
        secret_hash = secret.hash_client_secret(
            secret=new_secret,
            key=env.SECRET_KEY
        )
        client_storage.update_by_id(
            self.client_id,
            {"secret_hash": secret_hash}
        )
        return new_secret

    def update(self, **updates: typing.Any) -> None:
        """Update the client record.

        Args:
            **updates: Fields to update (name, description)
        """
        campus.model.Client.validate_update(updates)
        client_storage.update_by_id(self.client_id, updates)


class ClientAccessResource:
    """Represents the client access resource in Campus API Schema."""

    def __init__(self, parent: "ClientResource"):
        self._parent = parent

    def check(
            self,
            vault_label: str,
            permission: int
    ) -> bool:
        """Check if client has required permission for vault label.

        Args:
            client_id: The authenticated client ID
            vault_label: The vault label to check access for
            required_permission: The permission bitflag required (READ,
            CREATE, UPDATE, DELETE)

        Raises:
            VaultAccessDeniedError: If client lacks the required permission
        """
        client = self._parent.get()
        vault_access = client.permissions.get(vault_label, 0)
        return bool(vault_access & permission)

    def get(
            self,
            vault_label: str
    ) -> int:
        """Get the client's permission bitflag for a vault label.

        Args:
            vault_label: The vault label to get access for

        Returns:
            The permission bitflag for the vault label
        """
        client = self._parent.get()
        return client.permissions.get(vault_label, 0)

    def grant(
            self,
            vault_label: str,
            permission: int
    ) -> None:
        """Grant the client access permission for a vault label.

        Args:
            vault_label: The vault label to grant access for
            permission: The permission bitflag to grant
        """
        client_id = self._parent.client_id
        records = access_storage.get_matching({
            "client_id": client_id,
            "label": vault_label,
        })
        if records:
            current_access = records[0]['access']
            new_access = current_access | permission
            access_storage.update_by_id(
                records[0]['id'],
                {"access": new_access}
            )
        else:
            access_storage.insert_one({
                "id": uid.generate_category_uid("vault_access"),
                "created_at": schema.DateTime.utcnow(),
                "client_id": client_id,
                "label": vault_label,
                "access": permission,
            })

    def list(self) -> dict[str, int]:
        """List all vault access permissions for the client.

        Returns:
            Dictionary mapping vault labels to permission bitflags
        """
        client_id = self._parent.client_id
        access_records = access_storage.get_matching(
            {"client_id": client_id}
        )
        permissions: dict[str, int] = {}
        for record in access_records:
            label = record['label']
            access_flag = record['access']
            permissions[label] = access_flag
        return permissions

    def revoke(
            self,
            vault_label: str,
            permission: int
    ) -> None:
        """Revoke the client access permission for a vault label.

        Args:
            vault_label: The vault label to revoke access for
            permission: The permission bitflag to revoke
        """
        client_id = self._parent.client_id
        records = access_storage.get_matching({
            "client_id": client_id,
            "label": vault_label,
        })
        if not records:
            return
        current_access = records[0]['access']
        new_access = current_access & ~permission
        if new_access == 0:
            access_storage.delete_by_id(records[0]['id'])
        else:
            access_storage.update_by_id(
                records[0]['id'],
                {"access": new_access}
            )
