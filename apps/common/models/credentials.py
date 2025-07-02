"""apps.common.models.credentials

Credentials model for the Campus API.

Credentials are long-lived secrets, typically used for authorisation.

Credentials are assumed to be issued by a provider.
"""

from typing import NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.common.webauth.oauth2.authorization_code import TokenResponseSchema
from common.drum.mongodb import get_drum, PK
from common.schema import CampusID

TABLE = "credentials"


class ClientCredentials:
    """Model for client credentials.

    Client credentials are issued for clients, typically in the form of an
    access token and optionally a refresh token. They are identified by a
    client ID.

    Scopes may be included in the credentials, but are not required.
    """

    def __init__(self):
        pass

    def delete(self, client_id: CampusID) -> None:
        """Delete a client credential by its ID."""
        get_drum().delete_by_id(TABLE, client_id)

    def get(self, client_id: CampusID) -> dict | None:
        """Retrieve a client credential by its ID."""
        resp = get_drum().get_by_id(TABLE, client_id)
        match resp.status:
            case "error":
                api_errors.raise_api_error(404, message="Client not found")
            case "ok":
                record = resp.data
                return record

    def store(self, credentials: dict) -> None:
        """Store a client credential with the given ID and data."""
        # Add id primary key which is needed by the Drum interface.
        assert PK in credentials, "Client credentials must have an ID"
        drum = get_drum()
        resp = drum.get_by_id(TABLE, credentials[PK])
        if resp.status == "ok":
            # If the record already exists, we update it.
            drum.update_by_id(TABLE, credentials[PK], credentials)
        else:
            drum.insert(TABLE, credentials)


class UserCredentialsSchema(TypedDict):
    """TokenCredentials type for storing access and refresh tokens."""
    id: NotRequired[str]  # Primary key, only used internally
    provider: NotRequired[str]  # added by UserCredentials
    user_id: CampusID  # must be provided
    issued_at: NotRequired[int]  # Timestamp of when the token was issued
    token: TokenResponseSchema


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

    def delete(self, user_id: CampusID) -> None:
        """Delete user credentials by ID."""
        get_drum().delete_matching(
            TABLE,
            condition={"provider": self.provider, "user_id": user_id}
        )

    def get(self, user_id: CampusID) -> dict | None:
        """Retrieve user credentials by user ID."""
        resp = get_drum().get_matching(
            TABLE,
            condition={"provider": self.provider, "user_id": user_id}
        )
        match resp.status:
            case "error":
                api_errors.raise_api_error(500)
            case "ok":
                records = resp.data
                if not records:
                    api_errors.raise_api_error(
                        404,
                        message="User credentials not found"
                    )
                record = records[0]
                # Remove the primary key field from the record
                del record[PK]
                return record

    def store(self, **credentials: Unpack[UserCredentialsSchema]) -> None:
        """Store user credentials with the given data."""
        # Add id primary key which is needed by the Drum interface.
        if credentials.get("provider", self.provider) != self.provider:
            api_errors.raise_api_error(
                500, message="Provider mismatch in credentials"
            )
        token_id = self.provider + ":" + credentials["user_id"]
        credentials[PK] = token_id
        drum = get_drum()
        resp = drum.get_by_id(TABLE,  token_id)
        if resp.status == "ok" and resp.data:
            # If the record already exists, update it.
            drum.update_by_id(TABLE, token_id, credentials)
        else:
            drum.insert(TABLE, credentials)
