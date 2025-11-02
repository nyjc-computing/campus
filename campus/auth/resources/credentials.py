"""campus.auth.resources.token

Token resource for Campus API.
"""

import typing
from campus.common import env, schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
import campus.config
import campus.model
import campus.storage

token_storage = campus.storage.get_collection("tokens")
cred_storage = campus.storage.get_table("credentials")

cred_storage.init_from_model("credentials", campus.model.UserCredentials)


def delete_by_token_id(token_id: str) -> None:
    """Delete a token by its ID."""
    cred_storage.delete_matching({"token_id": token_id})
    token_storage.delete_by_id(token_id)


def delete_by_provider_user(
        *,
        provider: str,
        user_id: schema.UserID
) -> None:
    """Delete tokens for a given provider and user."""
    token_storage.delete_matching({
        "provider": provider,
        "user_id": user_id,
    })


@typing.overload
def find_credentials(
        *,
        provider: str,
        user_id: schema.UserID
) -> campus.model.UserCredentials: ...
@typing.overload
def find_credentials(
        *,
        user_id: schema.UserID
) -> list[campus.model.UserCredentials]: ...
@typing.overload
def find_credentials(
        *,
        provider: str,
) -> list[campus.model.UserCredentials]: ...
@typing.overload
def find_credentials() -> list[campus.model.UserCredentials]: ...
def find_credentials(
        *,
        provider: str | None = None,
        user_id: schema.UserID | None = None,
):
    """Find tokens matching criteria.

    To be supported in future; for now just returns all tokens.
    """
    query: dict[str, str] = {}
    if provider:
        query["provider"] = provider
    if user_id:
        query["user_id"] = str(user_id)
    records = cred_storage.get_matching(query)
    if provider and user_id:
        return (
            campus.model.UserCredentials.from_storage(records[0])
            if records else None
        )
    return [
        campus.model.UserCredentials.from_storage(record)
        for record in cred_storage.get_matching(query)
    ]


def get_credentials_by_id(credentials_id: schema.CampusID) -> campus.model.UserCredentials:
    """Retrieve credentials by their ID."""
    record = cred_storage.get_by_id(credentials_id)
    record["token"] = token_storage.get_by_id(record["token_id"])
    if not record:
        raise api_errors.NotFoundError(
            f"Credentials {credentials_id} not found."
        )
    return campus.model.UserCredentials.from_storage(record)


def get_token(token_id: str) -> campus.model.OAuthToken:
    """Retrieve a token by its ID."""
    record = token_storage.get_by_id(token_id)
    if not record:
        raise api_errors.NotFoundError(
            f"Token {token_id} not found."
        )
    return campus.model.OAuthToken.from_storage(record)


def new_campus_token(
        *,
        scopes: list[str],
        expiry_seconds: int = (
            campus.config.DEFAULT_TOKEN_EXPIRY_DAYS
            * utc_time.DAY_SECONDS
        ),
) -> campus.model.OAuthToken:
    """Create a new Campus OAuth token."""
    token_id = uid.generate_uid()
    token = campus.model.OAuthToken(
        id=token_id,
        expiry_seconds=expiry_seconds,
        scopes=scopes,
    )
    token_storage.insert_one(token.to_storage())
    return token


def store(
        *,
        provider: str,
        user_id: schema.UserID,
        token: campus.model.OAuthToken
) -> None:
    """Store or replace a token in the storage."""
    records = cred_storage.get_matching({
        "provider": provider,
        "user_id": user_id,
    })
    if len(records) == 0:  # No token stored prior
        token_storage.insert_one(token.to_storage())
        return
    elif len(records) == 1:  # Existing token
        creds = campus.model.UserCredentials.from_storage(records[0])
        if creds.token.id != token.id:
            # id mismatch; revoke token and update cred
            # TODO: perform transaction atomically
            delete_by_token_id(creds.token_id)
            token_storage.insert_one(token.to_storage())
            cred_storage.update_by_id(creds.id, {"token_id": token.id})
        else:
            token_storage.update_by_id(token.id, token.to_storage())


def sweep(
        *,
        at_time: schema.DateTime | None = None
) -> int:
    """Delete expired tokens from the database.

        Returns the number of deleted tokens.
        """
    at_time = at_time or schema.DateTime.utcnow()
    expired_tokens = [
        cred.token for cred in find_credentials()
        if cred.token.is_expired(at_time=at_time)
    ]
    # TODO: Optimize to do this in a single query
    for token in expired_tokens:
        delete_by_token_id(token.id)
    return len(expired_tokens)


def update_credentials(
        credentials: campus.model.UserCredentials,
        token: campus.model.OAuthToken,
) -> campus.model.UserCredentials:
    """Update token for existing credentials."""
    if credentials.token_id != token.id:
        # id mismatch; revoke token and update cred
        # TODO: perform transaction atomically
        delete_by_token_id(credentials.token_id)
        token_storage.insert_one(token.to_storage())
        cred_storage.update_by_id(
            credentials.id,
            {"token_id": token.id}
        )
    else:
        update_token(token)
    updated_credentials = get_credentials_by_id(credentials.id)
    return updated_credentials


def update_token(token: campus.model.OAuthToken) -> None:
    """Update an existing token in storage."""
    token_storage.update_by_id(token.id, token.to_storage())
