"""campus.models.credentials

Credentials model for the Campus API.

Credentials are long-lived secrets, assumed to be a TokenRecord.

Credentials are assumed to be issued by a provider.
"""

from dataclasses import dataclass
from typing import NotRequired, TypedDict

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
from campus.models import base, token
from campus.storage import (
    errors as storage_errors,
    get_collection
)

TokenId = str

COLLECTION = "credentials"

tokens = token.Tokens()


# class ClientCredentialsSchema(TypedDict):
#     """TokenCredentials type for storing access and refresh tokens."""
#     id: NotRequired[TokenId]  # Primary key, only used internally
#     provider: NotRequired[str]  # added by ClientCredentials
#     client_id: schema.CampusID  # must be provided
#     issued_at: schema.DateTime
#     token: TokenId


class UserCredentialsSchema(TypedDict):
    """TokenCredentials type for storing access and refresh tokens."""
    id: schema.CampusID  # Internal primary key
    provider: NotRequired[str]  # added by UserCredentials
    user_id: schema.UserID  # must be provided
    issued_at: schema.DateTime  # access_token issued at
    token: TokenId


@dataclass(eq=False, kw_only=True)
class UserCredentialsRecord(base.BaseRecord):
    provider: str
    user_id: schema.UserID
    token: token.TokenRecord

    @classmethod
    def from_dict(cls, data: dict) -> "UserCredentialsRecord":
        return cls(
            id=data.get("id", uid.generate_category_uid(COLLECTION, length=16)),
            provider=data["provider"],
            user_id=data["user_id"],
            token=tokens.get(data["token_id"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "user_id": self.user_id,
            "token_id": self.token.id,
        }


# class ClientCredentials:
#     """Model for client credentials.

#     Client credentials are issued for clients, typically in the form of an
#     access token and optionally a refresh token. They are identified by a
#     client ID.

#     Scopes may be included in the credentials, but are not required.

#     The client credentials are assumed to be issued by Campus.
#     """

#     def __init__(self, provider: str = "campus"):
#         self.provider = provider
#         self.storage = get_collection(COLLECTION)

#     def delete(self, client_id: schema.CampusID) -> None:
#         """Delete a client credential by its ID."""
#         try:
#             self.storage.delete_by_id(client_id)
#         except storage_errors.NotFoundError as e:
#             raise api_errors.ConflictError(
#                 message="Client credential not found",
#                 client_id=client_id
#             ) from e
#         except Exception as e:
#             raise api_errors.InternalError.from_exception(e) from e

#     def get(self, client_id: schema.CampusID) -> dict | None:
#         """Retrieve a client credential by its ID."""
#         try:
#             record = self.storage.get_by_id(client_id)
#         except storage_errors.NotFoundError as e:
#             api_errors.raise_api_error(
#                 404, message="Client credential not found")
#         except Exception as e:
#             if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
#                 raise  # Re-raise API errors as-is
#             raise api_errors.InternalError(message=str(e), error=e)
#         if record is None:
#             api_errors.raise_api_error(
#                 404, message="Client credential not found")
#         return record

#     def store(self, credentials: dict) -> None:
#         """Store a client credential with the given ID and data."""
#         try:
#             # Add id primary key which is needed by the backend interface.
#             assert schema.CAMPUS_KEY in credentials, "Client credentials must have an ID"
#             credentials_data = dict(credentials)

#             # Check if record already exists
#             try:
#                 existing_record = self.storage.get_by_id(
#                     credentials_data[schema.CAMPUS_KEY])
#             except storage_errors.NotFoundError:
#                 existing_record = None
#             # Other exceptions are handled below
#             if existing_record is not None:
#                 # If the record already exists, we update it.
#                 try:
#                     self.storage.update_by_id(
#                         credentials_data[schema.CAMPUS_KEY],
#                         credentials_data
#                     )
#                 except storage_errors.NoChangesAppliedError as e:
#                     raise api_errors.ConflictError(
#                         message="No client credential updated",
#                         client_id=credentials_data[schema.CAMPUS_KEY]
#                     ) from e
#                 # Other exceptions are handled below
#             else:
#                 try:
#                     self.storage.insert_one(credentials_data)
#                 except storage_errors.ConflictError as e:
#                     raise api_errors.ConflictError(
#                         message="Client credential conflict",
#                         client_id=credentials_data[schema.CAMPUS_KEY]
#                     ) from e
#                 # Other exceptions are handled below
#         except Exception as e:
#             if isinstance(e, AssertionError):
#                 raise  # Re-raise assertion errors as-is
#             raise api_errors.InternalError.from_exception(e) from e


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

    def delete(self, user_id: schema.CampusID) -> None:
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
            raise api_errors.InternalError.from_exception(e) from e

    def get(self, user_id: schema.CampusID) -> UserCredentialsRecord:
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
            return UserCredentialsRecord.from_dict(record)

    def new(
            self,
            user_id: schema.UserID,
            token: token.TokenRecord
    ) -> UserCredentialsRecord:
        """Create a new user credentials record."""
        return UserCredentialsRecord(
            id=uid.generate_category_uid(COLLECTION, length=16),
            provider=self.provider,
            user_id=user_id,
            token=token
        )

    def store(self, user_credentials: UserCredentialsRecord) -> None:
        """Store user credentials with the given data."""
        # Add id primary key which is needed by the backend interface.
        cred_id = uid.generate_category_uid(COLLECTION, length=16)
        credentials_data = user_credentials.to_dict()
        credentials_data[schema.CAMPUS_KEY] = cred_id
        credentials_data["provider"] = self.provider
        self.storage.insert_one(credentials_data)

    def update(self, user_credentials: UserCredentialsRecord) -> None:
        """Update user credentials with the given data."""
        # provider and user_id are not expected to change
        try:
            # check for existing record
            self.storage.update_by_id(
                user_credentials.id,
                {
                    "provider": self.provider,
                    "user_id": user_credentials.user_id
                }
            )
        except storage_errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                message="User credentials not found",
                provider=self.provider,
                user_id=user_credentials.user_id,
        ) from None
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
