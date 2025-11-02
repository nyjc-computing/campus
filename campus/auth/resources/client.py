"""campus.auth.resources.client

Client resource for Campus API.
"""

import typing

import flask

from campus.common import env, schema
from campus.common.errors import auth_errors
from campus.common.utils import secret
import campus.model
import campus.storage

from . import access

client_storage = campus.storage.get_table("clients")
access_storage = campus.storage.get_table("client_access")


def _from_record(
        record: dict[str, typing.Any],
        permissions: dict[str, int] | None = None
) -> campus.model.Client:
    """Convert a storage record to a Client model instance."""
    return campus.model.Client(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
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


def init_storage() -> None:
    """Initialize storage for client authentication."""
    client_storage.init_from_model("clients", campus.model.Client)
    access_storage.init_from_model("client_access", campus.model.ClientAccess)


def authenticate(client_id: schema.CampusID, client_secret: str) -> None:
    """Authenticate a client using their ID and secret.
    Pushes the authenticated client into flask.g.current_client if
    successful, otherwise raises an authentication error.

    Args:
        client_id: The client identifier
        client_secret: The client secret

    Raises:
        UnauthorizedError: If client not found or client secret is invalid
    """
    client = get(client_id)
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
    if flask.has_request_context():
        flask.g.current_client = get(client_id)


def get(client_id: schema.CampusID) -> campus.model.Client:
    """Get a client by ID.

    Args:
        client_id: The vault client ID

    Returns:
        Client instance
    """
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


def new(**kwargs: typing.Any) -> campus.model.Client:
    """Create a new Campus client.

    Args:
        **kwargs: Additional fields for client creation
    
    Returns:
        Client instance
    """
    client = _from_record(kwargs)
    client_storage.insert_one(client.to_storage())
    return client


def revoke(client_id: schema.CampusID) -> str:
    """Revoke a vault client's secret and regenerate it.

    Args:
        client_id: The client identifier

    Returns:
        The generated client secret
    """
    # Check if client exists first
    get(client_id)
    new_secret = secret.generate_client_secret()
    secret_hash = secret.hash_client_secret(new_secret, env.SECRET_KEY)
    client_storage.update_by_id(client_id, {"secret_hash": secret_hash})
    return new_secret


def update(client_id: schema.CampusID, **updates: typing.Any) -> None:
    """Update a vault client's information.

    Args:
        client_id: The client identifier
        **updates: Fields to update (name, description)

    Raises:
        NotFoundError: If client not found
    """
    campus.model.Client.validate_update(updates)
    client_storage.update_by_id(client_id, updates)


def check_vault_access(
        client_id: str,
        vault_label: str,
        required_permission: int
) -> None:
    """Check if client has required permission for vault label.

    Args:
        client_id: The authenticated client ID
        vault_label: The vault label to check access for
        required_permission: The permission bitflag required (READ,
        CREATE, UPDATE, DELETE)

    Raises:
        VaultAccessDeniedError: If client lacks the required permission
    """
    client = get(client_id)
    vault_access = client.permissions.get(vault_label, 0)
    if not vault_access & required_permission:
        reqd_perms = access.access_to_permissions(required_permission)
        raise auth_errors.AccessDeniedError(
            (
                f"Client '{client_id}' does not have "
                f"{reqd_perms} permission for vault '{vault_label}'"
            ),
            client_id=client_id,
            label=vault_label,
            permission=reqd_perms
        )


class ClientsResource:
    """Represents the clients resource in Campus API Schema."""

    def __getitem__(self, client_id: schema.CampusID) -> "ClientResource":
        """Get a client record by client ID.

        Args:
            client_id: The vault client ID

        Returns:
            ClientRecord instance
        """
        return ClientResource(client_id)


class ClientResource(ClientsResource):
    """Represents a single client in Campus API Schema."""

    def __init__(self, client_id: schema.CampusID):
        self._client_id = client_id

    def get(self) -> campus.model.Client:
        """Get the client record.

        Returns:
            ClientRecord instance
        """
        return get(self._client_id)

    def new(self, **kwargs: typing.Any) -> campus.model.Client:
        """Create a new client and return it.

        Args:
            **kwargs: Additional fields for client creation

        Returns:
            Client instance
        """
        return new(**kwargs)

    def revoke(self) -> str:
        """Revoke the client by deleting its secret."""
        return revoke(self._client_id)

    def update(self, **updates: typing.Any) -> None:
        """Update the client record.

        Args:
            **updates: Fields to update (name, description)
        """
        update(self._client_id, **updates)
