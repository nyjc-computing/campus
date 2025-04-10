"""
Client Models

This module provides classes and utilities for handling client applications
and API keys for Campus services.
"""
import os
from typing import Any, Literal, NamedTuple, NotRequired, TypedDict

from common.drum import sqlite
from common.schema import Message
from common.utils import secret, uid, utc_time
from common.validation import name as validname
from common.validation.record import validate_keys

APIName = str
APIKey = str
Email = str


def init_db():
    """Initialize the database with the necessary tables."""
    conn = sqlite.get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_requests (
            id TEXT PRIMARY KEY,
            requester TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_on TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'review',
            CHECK (status IN ('review', 'rejected', 'approved'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            client_secret TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_on TEXT NOT NULL
        )
    """)
    # Note that junction tables violate the assumption of a single-column
    # string primary key, as they are not expected to be directly queried
    # by end users.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_admins (
            client_id TEXT NOT NULL,
            admin_id TEXT NOT NULL,
            PRIMARY KEY (client_id, admin_email),
            FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            client_id TEXT NOT NULL,
            name TEXT NOT NULL,
            key TEXT NOT NULL,
            PRIMARY KEY (client_id, name),
            FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
        )
    """)
    conn.close()


class ClientRequest(TypedDict):
    """Data model for a client key request (apply for a client id)."""
    client_request_id: NotRequired[str]
    requester: Email
    name: str
    description: str
    created_on: NotRequired[utc_time.datetime]
    status: NotRequired[Literal["review", "rejected", "approved"]]


class ClientRecord(TypedDict):
    """Data model for a complete client record."""
    # client_id and secret_hash will be generated and need not be
    # provided
    client_id: NotRequired[str]
    secret_hash: NotRequired[str]
    name: str
    description: str
    admins: list[Email]
    created_on: NotRequired[utc_time.datetime]
    api_keys: NotRequired[dict[APIName, APIKey]]


class APIKeyRecord(TypedDict):
    """
    Data model for an API key.
    """
    client_id: str
    name: APIName
    # API key will be generated and need not be provided
    key: NotRequired[APIKey]


class ClientResponse(NamedTuple):
    """Represents a client operation response."""
    status: Literal["ok", "error"]
    message: str
    data: Any = None


class ClientIdRequest:
    """Model for database operations related to client id requests."""

    def __init__(self):
        """Initialize the Client model with a storage interface."""
        self.storage = sqlite.SqliteDrum()

    def submit_client_request(self, **fields) -> ClientResponse:
        """Submit a request for a new client id."""
        validate_keys(fields, ClientRecord.__required_keys__)
        client_request_id = uid.generate_category_uid("client_request")
        request = ClientRequest(
            client_request_id=client_request_id,
            **fields,
            created_on=utc_time.now(),
            status="review"
        )
        resp = self.storage.insert("client_requests", request)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, _):
                return ClientResponse("ok", Message.CREATED, request)
        raise ValueError(f"Unexpected response: {resp}")

    def get_client_request(self, client_request_id: str) -> ClientResponse:
        """Retrieve a client request by its ID."""
        resp = self.storage.get_by_id("client_requests", client_request_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.FOUND, result):
                return ClientResponse("ok", Message.FOUND, result)
        raise ValueError(f"Unexpected response: {resp}")

    def revoke_client_request(self, client_request_id: str) -> ClientResponse:
        """Revoke a client request by its ID."""
        resp = self.storage.delete_by_id("client_requests", client_request_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.DELETED, _):
                return ClientResponse("ok", Message.DELETED)
        raise ValueError(f"Unexpected response: {resp}")

    def reject_client_request(self, client_request_id: str) -> ClientResponse:
        """Reject a client request by its ID."""
        resp = self.storage.update_by_id(
            "client_requests",
            client_request_id,
            {"status": "rejected"}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.UPDATED, _):
                return ClientResponse("ok", Message.SUCCESS)
        raise ValueError(f"Unexpected response: {resp}")

    def approve_client_request(self, client_request_id: str) -> ClientResponse:
        """Approve a client request by its ID."""
        resp = self.storage.update_by_id(
            "client_requests",
            client_request_id,
            {"status": "approved"}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.UPDATED, _):
                return ClientResponse("ok", Message.SUCCESS)
        raise ValueError(f"Unexpected response: {resp}")

    def list_client_requests(self) -> ClientResponse:
        """List all client requests."""
        resp = self.storage.get_all("client_requests")
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.FOUND, result):
                return ClientResponse("ok", Message.FOUND, result)
            case ("ok", Message.EMPTY, _):
                return ClientResponse("ok", Message.EMPTY, [])
        raise ValueError(f"Unexpected response: {resp}")


class Client:
    """Model for database operations related to client applications.
    """

    def __init__(self):
        """Initialize the Client model with a storage interface."""
        self.storage = sqlite.SqliteDrum()

    def create_client(self, **fields) -> ClientResponse:
        """Create a new client with associated admins."""
        # Use Client model to validate keyword arguments
        validate_keys(fields, ClientRequest.__required_keys__)
        client_id = uid.generate_category_uid("client")
        client_secret = secret.generate_client_secret()
        record = ClientRecord(
            client_id=client_id,
            secret_hash=secret.hash_client_secret(
                client_secret,
                os.environ["PALMTREE_SECRET_KEY"]
            ),
            **fields,
            created_on=utc_time.now(),
        )

        # Registering a client involves multiple database operations
        # We use a transaction to ensure atomicity, i.e. all operations
        # are committed together, or none are.
        with self.storage.use_transaction():
            # admins are inserted in junction table and not in clients table
            self.storage.insert(
                "clients",
                {k: v for k, v in record.items() if k != "admins"}
            )
            for admin in record["admins"]:
                self.storage.insert(
                    "client_admins",
                    {"client_id": client_id, "admin_email": admin}
                )
            # Check for failed operations
            responses = self.storage.transaction_responses()
            if any(resp.status == "error" for resp in responses):
                self.storage.rollback_transaction()
                return ClientResponse("error", Message.FAILED, responses)
            else:
                self.storage.commit_transaction()
                return ClientResponse("ok", Message.SUCCESS, record)
        # transaction is automatically closed

    def update_client(
            self,
            client_id: str,
            updates: dict
    ) -> ClientResponse:
        """Update an existing client record."""
        # Validate arguments first to avoid unnecessary database operations
        if not updates:
            return ClientResponse("ok", Message.EMPTY, "Nothing to update")
        if "admins" in updates:
            return ClientResponse("error", Message.NOT_ALLOWED, "Admins may not be updated directly (use add/remove admin endpoints instead)")
        validate_keys(updates, ClientRecord.__required_keys__, required=False)

        resp = self.storage.update_by_id("clients", client_id, updates)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.UPDATED, _):
                return ClientResponse("ok", Message.UPDATED)
        raise ValueError(f"Unexpected response: {resp}")

    def add_client_admin(self, client_id: str, admin_email: Email) -> ClientResponse:
        """Add an admin to a client application."""
        resp = self.storage.insert(
            "client_admins",
            {"client_id": client_id, "admin_email": admin_email}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, _):
                return ClientResponse("ok", Message.SUCCESS)
        raise ValueError(f"Unexpected response: {resp}")

    def remove_client_admin(self, client_id: str, admin_email: Email) -> ClientResponse:
        """Remove an admin from a client application."""
        # Check if admin_email is the last admin
        resp = self.storage.get_matching(
            "client_admins",
            {"client_id": client_id}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.EMPTY, _):
                return ClientResponse("error", Message.NOT_FOUND, "Client not found")
            case ("ok", Message.FOUND, result):
                if (
                        result and len(result) == 1
                        and result[0]["admin_email"] == admin_email
                ):
                    return ClientResponse("error", Message.NOT_ALLOWED, "Cannot remove last client admin")

        resp = self.storage.delete_matching(
            "client_admins",
            {"client_id": client_id, "admin_email": admin_email}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.DELETED, _):
                return ClientResponse("ok", Message.SUCCESS)
        raise ValueError(f"Unexpected response: {resp}")

    def get_client(self, client_id: str) -> ClientResponse:
        """Retrieve a client application by its ID, including its admins."""
        resp = self.storage.get_by_id("clients", client_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, None):
                return ClientResponse("error", Message.NOT_FOUND)
        assert isinstance(resp, sqlite.DrumResponse)  # appease mypy
        client_record = resp.data
        assert isinstance(client_record, dict)

        resp = self.storage.get_matching("client_admins", {"client_id": client_id})
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, None):
                # client has no admins
                return ClientResponse("error", Message.INVALID)
        assert isinstance(resp, sqlite.DrumResponse)  # appease mypy
        admin_records = resp.data
        assert isinstance(admin_records, list)
        assert all(
            admin_record["client_id"] == client_id
            for admin_record in admin_records
        )

        client_record["admins"] = [
            admin_record["admin_email"]
            for admin_record in admin_records
        ]
        return ClientResponse("ok", Message.SUCCESS, client_record)

    def delete_client(self, client_id: str) -> ClientResponse:
        """Delete a client application by its ID."""
        resp = self.get_client(client_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, None):
                return ClientResponse("error", Message.NOT_FOUND)
        assert isinstance(resp, sqlite.DrumResponse)  # appease mypy
        client_record = resp.data
        assert isinstance(client_record, dict)

        with self.storage.use_transaction():
            # Remove admins first
            self.storage.delete_matching(
                "client_admins",
                {"client_id": client_id}
            )
            # Then remove the client
            self.storage.delete_by_id("clients", client_id)
            # Check for failed operations
            responses = self.storage.transaction_responses()
            if any(resp.status == "error" for resp in responses):
                self.storage.rollback_transaction()
                return ClientResponse("error", Message.FAILED, responses)
            else:
                self.storage.commit_transaction()
                return ClientResponse("ok", Message.SUCCESS)
        # transaction is automatically closed

    def revoke_client(self, client_id: str) -> ClientResponse:
        """Revoke a client secret by its ID, and issue a new secret."""
        client_secret = secret.generate_client_secret()
        resp = self.storage.update_by_id(
            "clients",
            client_id,
            {"secret_hash": secret.hash_client_secret(
                client_secret,
                os.environ["PALMTREE_SECRET_KEY"]
            )}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.UPDATED, _):
                return ClientResponse("ok", Message.SUCCESS, client_secret)
        raise ValueError(f"Unexpected response: {resp}")


class ClientAPIKey:
    """Model for database operations related to client API keys."""

    def __init__(self):
        self.storage = sqlite.SqliteDrum()

    def create_api_key(self, *, client_id: str, name: str) -> ClientResponse:
        """Create a new API key for a client.

        Validate name first before calling this function.

        Args:
            client_id: The ID of the client.
            name: The name of the API key.
        
        Returns:
            A ClientResponse indicating the result of the operation.
        """
        if not validname.is_valid_label(name):
            return ClientResponse("error", "Invalid API key name")
        api_key = secret.generate_api_key()
        record = APIKeyRecord(
            client_id=client_id,
            name=name,
            key=api_key
        )
        resp = self.storage.insert("api_keys", record)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, _):
                return ClientResponse("ok", "API key created", record["key"])
            case _:
                raise ValueError(f"Unexpected response: {resp}")

    def get_api_keys(self, client_id: str) -> ClientResponse:
        """Retrieve all API keys for a client."""
        resp = self.storage.get_matching("api_keys", {"client_id": client_id})
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.FOUND, result):
                return ClientResponse("ok", Message.SUCCESS, result)
            case ("ok", Message.EMPTY, _):
                return ClientResponse("ok", Message.EMPTY, [])
        raise ValueError(f"Unexpected response: {resp}")

    def delete_api_key(self, client_id: str, name: str) -> ClientResponse:
        """Delete an API key for a client."""
        resp = self.storage.delete_matching(
            "api_keys",
            {"client_id": client_id, "name": name}
        )
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.DELETED, _):
                return ClientResponse("ok", Message.DELETED)
        raise ValueError(f"Unexpected response: {resp}")
