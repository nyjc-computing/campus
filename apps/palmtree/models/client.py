"""
Client Models

This module provides classes and utilities for handling client applications
and API keys for Campus services.
"""
import os
from collections.abc import Sequence
from typing import Any, Literal, NamedTuple, TypedDict

from common.drum import sqlite
from common.schema import Message
from common.utils import secret, uid, utc_time
from common.utils.diff import diff_list
from common.validation import name as validname
from common.validation.record import validate_keys

APIName = str
APIKey = str
Email = str


def init_db():
    """Initialize the database with the necessary tables."""
    conn = sqlite.get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id TEXT PRIMARY KEY,
            client_secret TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_on TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('review', 'rejected', 'approved'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_admins (
            client_id TEXT NOT NULL,
            admin_email TEXT NOT NULL,
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


class ClientRequest(NamedTuple):
    """Data model for a client key request."""
    name: str
    description: str
    admins: list[Email]
    created_on: utc_time.datetime
    status: Literal["review", "rejected", "approved"] = "review"


class ClientRecord(TypedDict):
    """Data model for a complete client record."""
    client_id: str
    secret_hash: str
    name: str
    description: str
    admins: list[Email]
    api_keys: dict[APIName, APIKey]
    created_on: utc_time.datetime


class APIKeyRecord(NamedTuple):
    """
    Data model for an API key.
    """
    client_id: str
    name: APIName
    key: APIKey


class ClientResponse(NamedTuple):
    """Represents a client operation response."""
    status: Literal["ok", "error"]
    message: str
    data: Any = None


class ClientModel:
    """
    Client model for handling database operations related to client applications
    and API keys.
    """

    def __init__(self):
        """Initialize the Client model with a storage interface."""
        self.storage = sqlite.SqliteDrum()

    def create_client(self, **fields) -> ClientResponse:
        """Create a new client application with associated admins."""
        # Use Client model to validate keyword arguments
        request_fields = {"name": str, "description": str, "admins": list[str]}
        validate_keys(fields, request_fields)
        client_id = uid.generate_uid()
        client_secret = secret.generate_client_secret()
        client_record = dict(
            client_id=client_id,
            secret_hash=secret.hash_client_secret(client_secret, os.environ["PALMTREE_SECRET_KEY"]),
            name=fields["name"],
            description=fields["description"],
            admins=fields["admins"],
            created_on=utc_time.now(),
            status="review"
        )

        # Registering a client involves multiple database operations
        # We use a transaction to ensure atomicity, i.e. all operations are
        # committed together, or none are.
        with self.storage.use_transaction():
            # admins are inserted in junction table and not in clients table
            self.storage.insert(
                "clients",
                {k: v for k, v in client_record.items() if k != "admins"}
            )
            for admin in client_record["admins"]:
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
                return ClientResponse("ok", Message.SUCCESS, client_record)
        # transaction is automatically closed

    def update_client(self, client_id: str, updates: dict) -> ClientResponse:
        """Update an existing client record."""
        if not updates:
            return ClientResponse("ok", Message.EMPTY)
        resp = self.get_client(client_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, None):
                return ClientResponse("error", Message.NOT_FOUND)

        assert isinstance(resp, sqlite.DrumResponse)  # appease mypy
        client_record = resp.data
        assert isinstance(client_record, dict)
        # Client requests under review may not be updated
        if client_record["status"] != "approved":
            return ClientResponse("error", Message.NOT_ALLOWED, "Client may not be updated (create a new request instead)")
        validate_keys(updates, ClientRecord.__required_keys__, required=False)
        if "admins" in updates:
            return ClientResponse("error", Message.NOT_ALLOWED, "Admins may not be updated directly (use add/remove admin endpoints instead)")

        resp = self.storage.update("clients", client_id, updates)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.UPDATED, _):
                return ClientResponse("ok", Message.SUCCESS)
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
            case _:
                raise ValueError(f"Unexpected response: {resp}")

    def remove_client_admin(self, client_id: str, admin_email: Email) -> ClientResponse:
        """Remove an admin from a client application."""
        # Check if client is approved
        resp = self.storage.get_by_id("clients", client_id)
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.NOT_FOUND, _):
                return ClientResponse("error", Message.NOT_FOUND)
            case ("ok", Message.FOUND, client):
                assert isinstance(client, dict)
                if client["status"] != "approved":
                    return ClientResponse("error", Message.NOT_ALLOWED, "Client not (yet) approved")
            case _:
                raise ValueError(f"Unexpected response: {resp}")

        # Check if admin_email is the last admin
        resp = self.storage.get_matching("client_admins", {"client_id": client_id})
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", Message.EMPTY, _):
                return ClientResponse("error", Message.NOT_FOUND, "Client has no admins")
            case ("ok", Message.FOUND, result):
                assert isinstance(result, list)
                if len(result) == 1 and result[0]["admin_email"] == admin_email:
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
        assert isinstance(admin_records, dict)
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

        with self.storage.use_transaction() as conn:
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

    def create_api_key(self, client_id: str, name: str) -> ClientResponse:
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
        api_key = APIKeyRecord(
            client_id=client_id,
            name=name,
            key=secret.generate_api_key()
        )
        resp = self.storage.insert("api_keys", api_key._asdict())
        match resp:
            case ("error", _, _):
                return ClientResponse("error", Message.FAILED)
            case ("ok", _, _):
                return ClientResponse("ok", "API key created", api_key.key)
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
