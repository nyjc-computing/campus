"""campus.models.credentials

Credentials model for the Campus API.

Credentials are long-lived secrets, typically used for authorisation.

Credentials are assumed to be issued by a provider.
"""

from typing import NotRequired, TypedDict, Unpack

from campus.common.errors import api_errors
from campus.common.webauth.token import TokenSchema
from campus.storage import get_collection
from campus.common.schema import CampusID
from campus.common.utils import utc_time
from campus.storage import errors as storage_errors

COLLECTION = "credentials"


class ClientCredentialsSchema(TypedDict):
    """TokenCredentials type for storing access and refresh tokens."""
    id: NotRequired[str]  # Primary key, only used internally
    provider: NotRequired[str]  # added by ClientCredentials
    client_id: CampusID  # must be provided
    issued_at: utc_time.datetime
    token: TokenSchema


class UserCredentialsSchema(TypedDict):
    """TokenCredentials type for storing access and refresh tokens."""
    id: NotRequired[str]  # Primary key, only used internally
    provider: NotRequired[str]  # added by UserCredentials
    user_id: CampusID  # must be provided
    issued_at: utc_time.datetime
    token: TokenSchema


class ClientCredentials:
    """Model for client credentials.

    Client credentials are issued for clients, typically in the form of an
    access token and optionally a refresh token. They are identified by a
    client ID.

    Scopes may be included in the credentials, but are not required.

    The client credentials are assumed to be issued by Campus.
    """

    def __init__(self, provider: str = "campus"):
        self.provider = provider
        self.storage = get_collection(COLLECTION)

    def delete(self, client_id: CampusID) -> None:
        """Delete a client credential by its ID."""
        try:
            self.storage.delete_by_id(client_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Client credential not found",
                client_id=client_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, client_id: CampusID) -> dict | None:
        """Retrieve a client credential by its ID."""
        try:
            record = self.storage.get_by_id(client_id)
        except storage_errors.NotFoundError as e:
            api_errors.raise_api_error(
                404, message="Client credential not found")
        except Exception as e:
            if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
                raise  # Re-raise API errors as-is
            raise api_errors.InternalError(message=str(e), error=e)
        if record is None:
            api_errors.raise_api_error(
                404, message="Client credential not found")
        return record

    def store(self, credentials: dict) -> None:
        """Store a client credential with the given ID and data."""
        try:
            # Add id primary key which is needed by the backend interface.
            assert "id" in credentials, "Client credentials must have an ID"
            credentials_data = dict(credentials)

            # Check if record already exists
            try:
                existing_record = self.storage.get_by_id(
                    credentials_data["id"])
            except storage_errors.NotFoundError:
                existing_record = None
            # Other exceptions are handled below
            if existing_record is not None:
                # If the record already exists, we update it.
                try:
                    self.storage.update_by_id(
                        credentials_data["id"],
                        credentials_data
                    )
                except storage_errors.NoChangesAppliedError as e:
                    raise api_errors.ConflictError(
                        message="No client credential updated",
                        client_id=credentials_data["id"]
                    ) from e
                # Other exceptions are handled below
            else:
                try:
                    self.storage.insert_one(credentials_data)
                except storage_errors.ConflictError as e:
                    raise api_errors.ConflictError(
                        message="Client credential conflict",
                        client_id=credentials_data["id"]
                    ) from e
                # Other exceptions are handled below
        except Exception as e:
            if isinstance(e, AssertionError):
                raise  # Re-raise assertion errors as-is
            raise api_errors.InternalError(message=str(e), error=e)


class UserCredentials:
    """Model for user credentials.

    User credentials are issued for users, typically in the form of an
    access token and optionally a refresh token. They are identified by a
    provider and user ID.

    Scopes may be included in the credentials, but are not required.
    """
    provider: str

    def __init__(self, provider: str):
        self.provider = provider
        self.storage = get_collection(COLLECTION)

    def delete(self, user_id: CampusID) -> None:
        """Delete user credentials by ID."""
        try:
            self.storage.delete_matching(
                {"provider": self.provider, "user_id": user_id}
            )
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="User credentials not found",
                user_id=user_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, user_id: CampusID) -> UserCredentialsSchema:
        """Retrieve user credentials by user ID."""
        try:
            records = self.storage.get_matching(
                {"provider": self.provider, "user_id": user_id}
            )
        except storage_errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                message="User credentials not found",
                user_id=user_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            record = records[0]
            # Remove the primary key field from the record
            # Make a copy to avoid modifying the original
            credentials_data = dict(record)
            if "id" in credentials_data:
                del credentials_data["id"]
            return credentials_data  # type: ignore

    def store(self, **credentials: Unpack[UserCredentialsSchema]) -> None:
        """Store user credentials with the given data."""
        assert credentials.get("provider", self.provider) == self.provider, \
            "Provider mismatch in credentials"
        # Add id primary key which is needed by the backend interface.
        token_id = self.provider + ":" + credentials["user_id"]
        credentials_data = dict(credentials)
        credentials_data["id"] = token_id
        credentials_data["provider"] = self.provider
        try:
            # Check if record already exists
            try:
                existing_record = self.storage.get_by_id(token_id)
            except storage_errors.NotFoundError:
                existing_record = None
            # Other exceptions are handled below
            if existing_record is not None:
                # If the record already exists, update it.
                try:
                    self.storage.update_by_id(token_id, credentials_data)
                except storage_errors.NoChangesAppliedError as e:
                    raise api_errors.ConflictError(
                        message="No user credentials updated",
                        user_id=token_id
                    ) from e
                # Other exceptions are handled below
            else:
                try:
                    self.storage.insert_one(credentials_data)
                except storage_errors.ConflictError as e:
                    raise api_errors.ConflictError(
                        message="User credentials conflict",
                        user_id=token_id
                    ) from e
                # Other exceptions are handled below
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
