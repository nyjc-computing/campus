"""
Client Models

This module provides classes and utilities for handling client applications
and API keys for Campus services.
"""
import os
from typing import TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import ModelResponse
from common import devops
from common.drum import DrumResponse
if devops.ENV in (devops.STAGING, devops.PRODUCTION):
    from common.drum.postgres import get_conn, get_drum
else:
    from common.drum.sqlite import get_conn, get_drum
from common.schema import Message, Response
from common.utils import secret, uid, utc_time
from common.validation import name as validname
from common.validation.record import validate_keys

APIName = str
APIKey = str
Email = str


def init_db() -> None:
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    # TODO: Refactor into decorator
    if os.getenv('ENV', 'development') == 'production':
        raise AssertionError(
            "Database initialization detected in production environment"
        )
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "client_applications" (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'review',
                CHECK (status IN ('review', 'rejected', 'approved'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "clients" (
                id TEXT PRIMARY KEY,
                secret_hash TEXT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (name),
                UNIQUE (secret_hash)
            );
        """)
        # Note that junction tables violate the assumption of a single-column
        # string primary key, as they are not expected to be directly queried
        # by end users.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "client_admins" (
                id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                admin_id TEXT NOT NULL,
                UNIQUE (client_id, admin_id),
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        """)
        # cursor.execute("""
        #     CREATE TABLE IF NOT EXISTS apikeys (
        #         client_id TEXT NOT NULL,
        #         name TEXT NOT NULL,
        #         key TEXT NOT NULL,
        #         PRIMARY KEY (client_id, name),
        #         UNIQUE (key),
        #         FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
        #     )
        # """)
    except Exception:
        # init_db() is not expected to be called in production, so we don't
        # need to handle errors gracefully.
        raise
    else:
        conn.commit()
    finally:
        conn.close()


# class ClientApplicationNewSchema(TypedDict):
#     """Data model for a clients.applications.new operation."""
#     owner: Email
#     name: str
#     description: str


# class ClientApplicationRecord(TypedDict):
#     """Data model for a client application."""
#     id: str
#     owner: Email
#     name: str
#     description: str
#     created_at: utc_time.datetime
#     status: Literal["review", "rejected", "approved"]


# class ClientApplication:
#     """Model for database operations related to client id requests."""
#     __record_schema__ = ClientApplicationRecord
#     __request_schema__ = {
#         "list": None,
#         "delete": None,
#         "get": None,
#         "new": ClientApplicationNewSchema,
#         "approve": None,
#         "reject": None,
#     }

#     def __init__(self):
#         """Initialize the Client model with a storage interface."""
#         self.storage = get_drum()

#     def list(self) -> ModelResponse:
#         """List all client requests."""
#         resp = self.storage.get_all("client_applications")
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.FOUND, data=result):
#                 return ModelResponse("ok", Message.FOUND, result)
#             case Response(status="ok", message=Message.EMPTY):
#                 return ModelResponse("ok", Message.EMPTY, [])
#         raise ValueError(f"Unexpected response: {resp}")

#     def delete(self, client_application_id: str) -> ModelResponse:
#         """Revoke a client request by its ID."""
#         resp = self.storage.delete_by_id("client_applications", client_application_id)
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise api_errors.ConflictError(
#                     "Client request not found",
#                      client_application_id=client_application_id
#                 )
#             case Response(status="ok", message=Message.DELETED):
#                 return ModelResponse("ok", Message.DELETED)
#         raise ValueError(f"Unexpected response: {resp}")

#     def get(self, client_application_id: str) -> ModelResponse:
#         """Retrieve a client request by its ID."""
#         resp = self.storage.get_by_id("client_applications", client_application_id)
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise api_errors.ConflictError(
#                     "Client request not found",
#                      client_application_id=client_application_id
#                 )
#             case Response(status="ok", message=Message.FOUND, data=result):
#                 return ModelResponse("ok", Message.FOUND, result)
#         raise ValueError(f"Unexpected response: {resp}")

#     def new(self, **fields: Unpack[ClientApplicationNewSchema]) -> ModelResponse:
#         """Submit a request for a new client id."""
#         validate_keys(fields, ClientApplicationNewSchema.__required_keys__)
#         request = ClientApplicationRecord(
#             id=uid.generate_category_uid("client_application", length=6),
#             **fields,
#             created_at=utc_time.now(),
#             status="review"
#         )
#         resp = self.storage.insert("client_applications", request)
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok"):
#                 return ModelResponse("ok", Message.CREATED, request)
#         raise ValueError(f"Unexpected response: {resp}")

#     def approve(self, client_application_id: str) -> ModelResponse:
#         """Approve a client request by its ID."""
#         resp = self.storage.update_by_id(
#             "client_applications",
#             client_application_id,
#             {"status": "approved"}
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise api_errors.ConflictError(
#                     "Client request not found",
#                      client_application_id=client_application_id
#                 )
#             case Response(status="ok", message=Message.UPDATED):
#                 return ModelResponse("ok", Message.SUCCESS)
#         raise ValueError(f"Unexpected response: {resp}")

#     def reject(self, client_application_id: str) -> ModelResponse:
#         """Reject a client request by its ID."""
#         resp = self.storage.update_by_id(
#             "client_applications",
#             client_application_id,
#             {"status": "rejected"}
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise api_errors.ConflictError(
#                     "Client request not found",
#                      client_application_id=client_application_id
#                 )
#             case Response(status="ok", message=Message.UPDATED):
#                 return ModelResponse("ok", Message.SUCCESS)
#         raise ValueError(f"Unexpected response: {resp}")
    

# class ClientAdmin:
#     """Model for database operations related to client admins."""

#     def __init__(self):
#         """Initialize the Client model with a storage interface."""
#         self.storage = get_drum()

#     def list(self, client_id: str) -> ModelResponse:
#         """List all admins for a client application."""
#         resp = self.storage.get_matching("client_admins", {"client_id": client_id})
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.FOUND, data=result):
#                 return ModelResponse("ok", Message.FOUND, result)
#             case Response(status="ok", message=Message.EMPTY):
#                 return ModelResponse("ok", Message.EMPTY, [])
#         raise ValueError(f"Unexpected response: {resp}")

#     def add(self, client_id: str, admin_id: Email) -> ModelResponse:
#         """Add an admin to a client application."""
#         resp = self.storage.insert(
#             "client_admins",
#             {
#                 "id": uid.generate_category_uid("client_admin", length=4),
#                 "client_id": client_id,
#                 "admin_id": admin_id
#             }
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.SUCCESS):
#                 return ModelResponse("ok", Message.SUCCESS)
#         raise ValueError(f"Unexpected response: {resp}")

#     def remove(self, client_id: str, admin_id: Email) -> ModelResponse:
#         """Remove an admin from a client application."""
#         # Check if admin_id is the last admin
#         resp = self.storage.get_matching(
#             "client_admins",
#             {"client_id": client_id}
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.EMPTY):
#                 raise api_errors.ConflictError(
#                     "Client has no admins",
#                      client_id=client_id
#                 )
#             case Response(status="ok", message=Message.FOUND, data=result):
#                 if (
#                         result and len(result) == 1
#                         and result[0]["admin_id"] == admin_id
#                 ):
#                     raise api_errors.UnauthorizedError(
#                         "Cannot remove last client admin",
#                         client_id=client_id
#                     )

#         resp = self.storage.delete_matching(
#             "client_admins",
#             {"client_id": client_id, "admin_id": admin_id}
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise AssertionError("Client admin not found")
#             case Response(status="ok", message=Message.DELETED):
#                 return ModelResponse("ok", Message.SUCCESS)
#         raise ValueError(f"Unexpected response: {resp}")


class ClientNew(TypedDict, total=True):
    """Data model for a clients.new operation."""
    name: str
    description: str
    # admins: list[Email]


class ClientResource(ClientNew, total=True):
    """Data model for a complete client resource."""
    # client_id and secret_hash will be generated and need not be provided
    id: ReadOnly[str]
    secret_hash: str
    created_at: utc_time.datetime
    # apikeys: NotRequired[dict[APIName, APIKey]]
    # admins: list[Email]


class Client:
    """Model for database operations related to client applications."""
    # Nested attribute follows Campus API schema
    # applications = ClientApplication()
    # admins = ClientAdmin()
    # apikeys = ClientAPIKey()

    def __init__(self):
        """Initialize the Client model with a storage interface."""
        self.storage = get_drum()

    def delete(self, client_id: str) -> ModelResponse:
        """Delete a client application by its ID."""
        resp = self.get(client_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", data=None):
                raise api_errors.ConflictError(
                    "Client not found",
                     client_id=client_id
                )
        assert isinstance(resp, DrumResponse)  # appease mypy
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
                raise api_errors.InternalError(message="Some operations failed", responses=self.storage.transaction_responses())
            else:
                self.storage.commit_transaction()
                return ModelResponse("ok", Message.SUCCESS)
        # transaction is automatically closed

    def list(self) -> ModelResponse:
        """List all client applications."""
        resp = self.storage.get_all("clients")
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND, data=result):
                return ModelResponse("ok", Message.FOUND, result)
            case Response(status="ok", message=Message.EMPTY):
                return ModelResponse("ok", Message.EMPTY, [])
        raise ValueError(f"Unexpected response: {resp}")

    def get(self, client_id: str) -> ModelResponse:
        """Retrieve a client application by its ID, including its admins."""
        resp = self.storage.get_by_id("clients", client_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND, data=None):
                raise api_errors.ConflictError(
                    "Client not found",
                     client_id=client_id
                )
        assert isinstance(resp, DrumResponse)  # appease mypy
        client_record = resp.data
        # Do not reveal secrets in API
        del client_record["secret_hash"]
        assert isinstance(client_record, dict)

        resp = self.storage.get_matching("client_admins", {"client_id": client_id})
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", data=None):
                # client has no admins
                raise api_errors.ConflictError(
                    "Client has no admins",
                     client_id=client_id
                )
        assert isinstance(resp, DrumResponse)  # appease mypy
        admin_records = resp.data
        assert isinstance(admin_records, list)
        assert all(
            admin_record["client_id"] == client_id
            for admin_record in admin_records
        )

        # client_record["admins"] = [
        #     admin_record["admin_id"]
        #     for admin_record in admin_records
        # ]
        return ModelResponse("ok", Message.SUCCESS, client_record)

    def new(self, **fields: Unpack[ClientNew]) -> ModelResponse:
        """Create a new client with associated admins."""
        # Use Client model to validate keyword arguments
        validate_keys(fields, ClientNew.__required_keys__)
        client_id = uid.generate_category_uid("client", length=6)
        record = ClientResource(
            id=client_id,
            created_at=utc_time.now(),
            **fields,
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
            # for admin in record["admins"]:
            #     self.storage.insert(
            #         "client_admins",
            #         {
            #             "id": uid.generate_category_uid("client_admin", length=4),
            #             "client_id": client_id,
            #             "admin_id": admin
            #         }
            #     )
            # Check for failed operations
            failures = [
                resp for resp in self.storage.transaction_responses()
                if resp.status == "error"
            ]
            if failures:
                raise api_errors.InternalError(
                    "Some operations failed",
                    failed=failures
                )
            else:
                return ModelResponse("ok", Message.SUCCESS, record)
        # rollback/commit and tansaction closing are automatically handled

    def replace(self, client_id: str) -> ModelResponse:
        """Revoke a client secret by its ID, and issue a new secret."""
        client_secret = secret.generate_client_secret()
        resp = self.storage.update_by_id(
            "clients",
            client_id,
            {"secret_hash": secret.hash_client_secret(
                client_secret,
                os.environ["SECRET_KEY"]
            )}
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    "Client not found",
                     client_id=client_id
                )
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse("ok", Message.SUCCESS, client_secret)
        raise ValueError(f"Unexpected response: {resp}")

    def update(self, client_id: str, updates: dict) -> ModelResponse:
        """Update an existing client record."""
        # Validate arguments first to avoid unnecessary database operations
        if not updates:
            return ModelResponse("ok", Message.EMPTY, "Nothing to update")
        if "admins" in updates:
            raise api_errors.InvalidRequestError(
                message="Admins may not be updated directly (use add/remove admin endpoints instead)",
                invalid_fields=["admins"]
            )
        validate_keys(updates, ClientResource.__required_keys__, required=False)

        resp = self.storage.update_by_id("clients", client_id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    "Client not found",
                     client_id=client_id
                )
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse("ok", Message.UPDATED)
        raise ValueError(f"Unexpected response: {resp}")

    def validate_credentials(self, client_id: str, client_secret: str) -> bool:
        """Validate client_id and client_secret."""
        resp = self.storage.get_by_id("clients", client_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.NOT_FOUND):
                return False
            case Response(status="ok", message=Message.FOUND, data=cursor):
                client = cursor['result']
                return client["secret_hash"] == secret.hash_client_secret(
                    client_secret, os.environ["SECRET_KEY"]
                )
            case _:
                return False


# class APIKeyNewSchema(TypedDict):
#     """Data model for a clients.apikeys.new operation."""
#     name: APIName
#     description: str


# class APIKeyRecord(TypedDict):
#     """Data model for an API key."""
#     client_id: str
#     name: APIName
#     key: APIKey


# class ClientAPIKey:
#     """Model for database operations related to client API keys."""

#     def __init__(self):
#         self.storage = get_drum()

#     def new(self, client_id: str, *, name: str) -> ModelResponse:
#         """Create a new API key for a client.

#         Validate name first before calling this function.

#         Args:
#             client_id: The ID of the client.
#             name: The name of the API key.
        
#         Returns:
#             A ModelResponse indicating the result of the operation.
#         """
#         if not validname.is_valid_label(name):
#             raise api_errors.InvalidRequestError(
#                 message="Invalid API key name",
#                 invalid_values=["name"]
#             )
#         api_key = secret.generate_api_key()
#         record = APIKeyRecord(
#             client_id=client_id,
#             name=name,
#             key=api_key
#         )
#         resp = self.storage.insert("apikeys", record)
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.CREATED):
#                 return ModelResponse("ok", "API key created", record["key"])
#         raise ValueError(f"Unexpected response: {resp}")

#     def list(self, client_id: str) -> ModelResponse:
#         """Retrieve all API keys for a client."""
#         resp = self.storage.get_matching("apikeys", {"client_id": client_id})
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.FOUND, data=result):
#                 return ModelResponse("ok", Message.SUCCESS, result)
#             case Response(status="ok", message=Message.EMPTY):
#                 return ModelResponse("ok", Message.EMPTY, [])
#         raise ValueError(f"Unexpected response: {resp}")

#     def delete(self, client_id: str, name: str) -> ModelResponse:
#         """Delete an API key for a client."""
#         resp = self.storage.delete_matching(
#             "apikeys",
#             {"client_id": client_id, "name": name}
#         )
#         match resp:
#             case Response(status="error", message=message, data=error):
#                 raise api_errors.InternalError(message=message, error=error)
#             case Response(status="ok", message=Message.NOT_FOUND):
#                 raise api_errors.ConflictError(
#                     "API key not found",
#                      client_id=client_id, name=name
#                 )
#             case Response(status="ok", message=Message.DELETED):
#                 return ModelResponse(*resp)
#         raise ValueError(f"Unexpected response: {resp}")

