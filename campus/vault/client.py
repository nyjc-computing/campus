"""vault.client

Client authentication module for the vault service.

This module provides independent client storage and authentication for the vault
service to avoid circular dependencies with the main storage system. The vault
cannot rely on the main client model because it depends on storage, which may
depend on vault for secrets management.

This module implements its own client storage using direct database access
to the vault database, maintaining compatibility with the main client schema
where possible.

SECRET_KEY USAGE:
This module intentionally uses the SECRET_KEY environment variable rather than
retrieving it from the vault to maintain independence and avoid circular 
dependencies. The vault service must be able to authenticate its own clients
without depending on itself.
"""

import os
from typing import TypedDict, NotRequired, Unpack

from campus.common.utils import secret, uid, utc_time
from campus.common import devops
from . import db

CLIENT_TABLE = "vault_clients"


class ClientNew(TypedDict, total=True):
    """Request body schema for creating a new vault client."""
    name: str
    description: str


class ClientResource(TypedDict, total=True):
    """Response body schema representing a vault client."""
    id: str
    name: str
    description: str
    created_at: str
    secret_hash: NotRequired[str]


class ClientResourceWithSecret(TypedDict, total=True):
    """Response body schema for new client creation including the secret."""
    id: str
    name: str
    description: str
    created_at: str
    secret: str


class VaultClientSecretResponse(TypedDict, total=True):
    """Response body schema for client secret operations."""
    secret: str


class ClientAuthenticationError(Exception):
    """Custom error for client authentication failures."""

    def __init__(self, message: str, client_id: str | None = None):
        super().__init__(message)
        self.client_id = client_id


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the vault client table.

    This function is intended to be called only in a test environment or
    staging. The vault client table is separate from the main clients table
    to avoid circular dependencies.
    """
    with db.get_connection_context() as conn:
        with conn.cursor() as cursor:
            client_schema = f"""
                CREATE TABLE IF NOT EXISTS {CLIENT_TABLE} (
                    id TEXT PRIMARY KEY,
                    secret_hash TEXT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (name),
                    UNIQUE (secret_hash)
                )
            """
            cursor.execute(client_schema)


def create_client(**fields: Unpack[ClientNew]) -> tuple[ClientResource, str]:
    """Create a new vault client with authentication credentials.

    Args:
        **fields: Client creation fields (name, description)

    Returns:
        Tuple of (client_resource, client_secret)
        The client_secret should be securely provided to the client.

    Raises:
        Exception: If client creation fails (e.g., name already exists)
    """
    client_id = uid.generate_category_uid("client", length=12)
    client_secret = secret.generate_client_secret()
    secret_hash = secret.hash_client_secret(
        client_secret, os.environ["SECRET_KEY"])

    record = {
        "id": client_id,
        "created_at": utc_time.now(),
        "secret_hash": secret_hash,
        **fields,
    }

    with db.get_connection_context() as conn:
        db.execute_query(
            conn,
            f"""
            INSERT INTO {CLIENT_TABLE} (id, secret_hash, name, description, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (record["id"], record["secret_hash"], record["name"],
             record["description"], record["created_at"]),
            fetch_one=False,
            fetch_all=False
        )

    # Return client resource without secret_hash
    client_resource: ClientResource = {
        k: v for k, v in record.items() if k != "secret_hash"}  # type: ignore
    return client_resource, client_secret


def get_client(client_id: str) -> ClientResource:
    """Retrieve a vault client by its ID.

    Args:
        client_id: The client identifier

    Returns:
        Client resource without secret_hash

    Raises:
        VaultClientAuthenticationError: If client not found
    """
    with db.get_connection_context() as conn:
        client_record = db.execute_query(
            conn,
            f"SELECT id, name, description, created_at FROM {CLIENT_TABLE} WHERE id = %s",
            (client_id,),
            fetch_one=True
        )

        if not client_record:
            raise ClientAuthenticationError(
                f"Vault client '{client_id}' not found",
                client_id=client_id
            )

        return client_record


def list_clients() -> list[ClientResource]:
    """List all vault clients.

    Returns:
        List of client resources without secret_hash
    """
    with db.get_connection_context() as conn:
        client_records = db.execute_query(
            conn,
            f"SELECT id, name, description, created_at FROM {CLIENT_TABLE}",
            (),
            fetch_all=True
        )

        return client_records or []


def delete_client(client_id: str) -> None:
    """Delete a vault client by its ID.

    Args:
        client_id: The client identifier

    Raises:
        VaultClientAuthenticationError: If client not found
    """
    # Check if client exists first
    get_client(client_id)  # This will raise if not found

    with db.get_connection_context() as conn:
        db.execute_query(
            conn,
            f"DELETE FROM {CLIENT_TABLE} WHERE id = %s",
            (client_id,),
            fetch_one=False,
            fetch_all=False
        )


def replace_client_secret(client_id: str) -> str:
    """Replace a client's secret with a new one.

    Args:
        client_id: The client identifier

    Returns:
        The new client secret

    Raises:
        VaultClientAuthenticationError: If client not found
    """
    # Check if client exists first
    get_client(client_id)  # This will raise if not found

    new_secret = secret.generate_client_secret()
    secret_hash = secret.hash_client_secret(
        new_secret, os.environ["SECRET_KEY"])

    with db.get_connection_context() as conn:
        db.execute_query(
            conn,
            f"UPDATE {CLIENT_TABLE} SET secret_hash = %s WHERE id = %s",
            (secret_hash, client_id),
            fetch_one=False,
            fetch_all=False
        )

    return new_secret


def authenticate_client(client_id: str, client_secret: str) -> None:
    """Authenticate a client using their ID and secret.

    Args:
        client_id: The client identifier
        client_secret: The client secret

    Raises:
        VaultClientAuthenticationError: If authentication fails
    """
    with db.get_connection_context() as conn:
        client_record = db.execute_query(
            conn,
            f"SELECT secret_hash FROM {CLIENT_TABLE} WHERE id = %s",
            (client_id,),
            fetch_one=True
        )

        if not client_record:
            raise ClientAuthenticationError(
                f"Vault client '{client_id}' not found",
                client_id=client_id
            )

        if not client_record["secret_hash"]:
            raise ClientAuthenticationError(
                f"Vault client '{client_id}' has no secret configured",
                client_id=client_id
            )

        expected_hash = secret.hash_client_secret(
            client_secret, os.environ["SECRET_KEY"])
        if client_record["secret_hash"] != expected_hash:
            raise ClientAuthenticationError(
                f"Invalid secret for vault client '{client_id}'",
                client_id=client_id
            )


def update_client(client_id: str, **updates: Unpack[ClientNew]) -> None:
    """Update a vault client's information.

    Args:
        client_id: The client identifier
        **updates: Fields to update (name, description)

    Raises:
        VaultClientAuthenticationError: If client not found
    """
    if not updates:
        return

    # Check if client exists first
    get_client(client_id)  # This will raise if not found

    # Build dynamic update query
    set_clauses = []
    values = []

    for field, value in updates.items():
        if field in ("name", "description"):
            set_clauses.append(f"{field} = %s")
            values.append(value)

    if not set_clauses:
        return

    values.append(client_id)

    with db.get_connection_context() as conn:
        db.execute_query(
            conn,
            f"UPDATE {CLIENT_TABLE} SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(values),
            fetch_one=False,
            fetch_all=False
        )
