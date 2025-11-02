"""campus.auth.resources.session

Auth session resource for Campus API.
"""

import typing

import flask

from campus.common import env, schema
from campus.common.errors import api_errors, auth_errors
from campus.common.utils import uid, secret
import campus.config
import campus.model
import campus.storage

session_storage = campus.storage.get_collection("auth_sessions")


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.AuthSession:
    """Convert a storage record to an AuthSession model instance."""
    args: dict[str, typing.Any] = {}
    if "id" in record:
        args["id"] = schema.CampusID(record["id"])
    if "created_at" in record:
        args["created_at"] = schema.DateTime(record["created_at"])
    if "expires_at" in record:
        args["expires_at"] = schema.DateTime(record["expires_at"])
    args["client_id"] = schema.CampusID(record["client_id"])
    if "user_id" in record:
        args["user_id"] = schema.UserID(record["user_id"])
    args["redirect_uri"] = schema.Url(record["redirect_uri"])
    if "scopes" in record:
        args["scopes"] = record["scopes"]
    if "authorization_code" in record:
        args["authorization_code"] = record["authorization_code"]
    if "target" in record and record["target"] is not None:
        args["target"] = schema.Url(record["target"])
    return campus.model.AuthSession(**args)


def _session_key(provider: str) -> str:
    """Get the session key for the provider."""
    return f"{provider}_session_id"


def init_storage() -> None:
    """Initialize storage for client authentication."""
    # Document store does not require initialization
    pass


def _check_existing_id(provider: str) -> schema.CampusID | None:
    """Check if a session already exists.

    A session exists if:
    - there is a session_id stored in the client cookie, and
    - a session with that ID exists on the server.
    Returns the session ID if a session exists, otherwise None.
    If the session ID is found client-side but not server-side, the
    client-side session is considered invalid and revoked; this does
    not trigger an error as it is expected to happen when
    server-side sweeps happen.
    """
    session_key = _session_key(provider)
    client_session_id = flask.session.get(session_key)
    if not client_session_id:
        return None
    try:
        session_storage.get_by_id(client_session_id)
    except campus.storage.errors.NotFoundError:
        # Revoke client-side
        flask.session.pop(session_key, None)
        return None
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    else:
        return client_session_id


def _verify_session_id(
        provider: str,
        session_id: schema.CampusID
) -> schema.CampusID:
    """Verify the session ID against the stored session.
    Raises:
        ConflictError if there is a mismatch.
        NotFoundError if no session ID is found in the client.
    
    This avoids accidental deletion of a session that does not
    belong to the client.
    """
    client_session_id = _check_existing_id(provider)
    if client_session_id and session_id != client_session_id:
        raise api_errors.ConflictError(
            message="Mismatch with client session ID",
            session_id=session_id
        ) from None
    if not client_session_id:
        raise api_errors.NotFoundError(
            message="No session ID in client",
            session_id=session_id
        ) from None
    return client_session_id


def delete(
        provider: str,
        session_id: schema.CampusID | None = None,
        sync_client: bool = True
) -> None:
    """Delete a session by its ID.

    Args:
        session_id: The ID of the session to delete. If None, uses the
            session ID from the client cookie.
        sync_client: If True, also removes the session ID from the client
            cookie.
    """
    # Check if session exists client-side
    session_id = session_id or _check_existing_id(provider)
    if not session_id:
        raise api_errors.NotFoundError(
            message="Session not found",
            session_id=session_id
        ) from None
    if sync_client:
        session_id = _verify_session_id(provider, session_id)
    # Remove server-side session
    try:
        session_storage.delete_by_id(session_id)
    except campus.storage.errors.NotFoundError:
        # Session already deleted server-side
        # TODO: logging for missing session
        pass
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    else:
        # For consistency, only remove client-side session after
        # successful server-side deletion
        if sync_client and _session_key(provider) in flask.session:
            del flask.session[_session_key(provider)]

def finalize(
        provider: str,
        auth_session: campus.model.AuthSession
) -> schema.Url | None:
    """Finalize an auth session and return the redirect URI.
    This typically involves cleaning up the session and preparing
    for redirection to the target.
    """
    delete(provider, auth_session.id)
    return auth_session.redirect_uri

def find(
        *,
        client_id: schema.CampusID | None = None,
        user_id: schema.UserID | None = None,
        # expire_after: schema.DateTime | None = None,
        # expire_before: schema.DateTime | None = None,
        limit: int = 100,
) -> list[campus.model.AuthSession]:
    """Find sessions matching the given criteria.
    At least one filter must be provided.
    """
    query = {}
    if client_id:
        query["client_id"] = client_id
    if user_id:
        query["user_id"] = user_id
    # TODO: DSL for query ranges
    # if expire_after or expire_before:
    #     query["expires_at"] = {}
    #     if expire_after:
    #         query["expires_at"]["$gte"] = expire_after
    #     if expire_before:
    #         query["expires_at"]["$lte"] = expire_before
    if not query:
        raise api_errors.InvalidRequestError(
            message="At least one filter must be provided"
        )
    query["$limit"] = limit
    try:
        records = session_storage.get_matching(query)
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    else:
        return [_from_record(r) for r in records]

def get(
        provider: str,
        session_id: schema.CampusID | None = None
) -> campus.model.AuthSession | None:
    """Retrieve a session by its ID, or return None if not found.

    If session_id is not provided, uses the session ID from the client
    cookie.
    """
    if session_id:
        return get_by_id(session_id)
    existing_session_id = _check_existing_id(provider)
    if existing_session_id is not None:
        return get_by_id(existing_session_id)
    return None

def get_by_id(
        session_id: schema.CampusID
) -> campus.model.AuthSession | None:
    """Retrieve a session by its ID."""
    try:
        record = session_storage.get_by_id(session_id)
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    if not record:
        return None
    return _from_record(record)

def new(
    provider: str,
    *,
    expiry_seconds: int,
    client_id: schema.CampusID,
    user_id: schema.UserID | None = None,
    redirect_uri: schema.Url,
    scopes: list[str] | None = None,
    authorization_code: str | None = None,
    state: str | None = None,
    target: schema.Url | None = None,
) -> campus.model.AuthSession:
    """Create a new session.

    Any existing session will be revoked.
    """
    # Delete any existing session
    if (existing_id := _check_existing_id(provider)):
        delete(provider, existing_id)
    session = _from_record({
        "id": uid.generate_category_uid(f"{provider}-session"),
        "expiry_seconds": expiry_seconds,
        "client_id": str(client_id),
        "user_id": str(user_id) if user_id else None,
        "redirect_uri": str(redirect_uri),
        "scopes": scopes or [],
        "authorization_code": (
            authorization_code
            or secret.generate_authorization_code()
        ),
        "state": state,
        "target": str(target) if target else None,
    })
    try:
        session_storage.insert_one(session.to_storage())
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    else:
        flask.session[_session_key(provider)] = session.id
        return session

def sweep(
        provider: str,
        *,
        at_time: schema.DateTime | None = None
) -> int:
    """Delete expired sessions from the database.

    Returns the number of deleted sessions.
    """
    at_time = at_time or schema.DateTime.utcnow()
    # TODO: implement query DSL for ranges
    try:
        records = session_storage.get_matching({})
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    deleted_ids = []
    # TODO: Optimize to do this in a single query
    for record in records:
        if schema.DateTime(record["expires_at"]) <= at_time:
            delete(provider, record[schema.CAMPUS_KEY], sync_client=False)
            deleted_ids.append(record[schema.CAMPUS_KEY])
    return len(deleted_ids)

def update(
        provider: str,
        session_id: schema.CampusID | None = None,
        **update
) -> campus.model.AuthSession:
    """Update an existing session."""
    session_id = session_id or _check_existing_id(provider)
    if not session_id:
        raise api_errors.NotFoundError(
            message="Session not found",
            session_id=session_id
        ) from None
    _verify_session_id(provider, session_id)
    # TODO: Validate update fields
    for immutable_key in (
        schema.CAMPUS_KEY,
        "client_id",
        "user_id",
        "agent_string",
        "created_at",
    ):
        if immutable_key in update:
            raise api_errors.InvalidRequestError(
                message=f"Cannot update immutable field: {immutable_key}"
            )
    try:
        session_storage.update_by_id(session_id, update)
    except campus.storage.errors.NotFoundError as e:
        raise api_errors.ConflictError(
            message="Session not found",
            session_id=session_id
        ) from e
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    session = get_by_id(session_id)
    assert session
    return session
