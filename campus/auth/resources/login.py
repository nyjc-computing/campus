"""campus.auth.resources.ogin

Login session resource for Campus API.
"""

import typing

import flask

from campus.common import env, schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage

PROVIDER = "campus"

session_storage = campus.storage.get_collection("auth_sessions")


class LoginSessionsResource:
    """Represents the login sessions resource in Campus API Schema.
    
    Note that this only manages Campus logins, not for external
    authentication providers.
    """

    def __getitem__(
            self,
            session_id: schema.CampusID
    ) -> "LoginSessionResource":
        """Get a login session resource.

        Returns:
            LoginSessionResource instance
        """
        return LoginSessionResource()

    def get(self) -> campus.model.LoginSession | None:
        """Get the login session for this provider.

        Returns:
            LoginSession instance or None if not found
        """
        existing_session_id = _check_existing_id()
        if existing_session_id is not None:
            return self[existing_session_id].get()
        return None

    def new(
            self,
            *,
            expiry_seconds: int,
            client_id: schema.CampusID,
            user_id: schema.UserID | None = None,
            device_id: str | None = None,
            agent_string: str,
    ) -> campus.model.LoginSession:
        """Create a new session.

        Any existing session will be revoked.
        """
        # Delete any existing session
        if (existing_session_id := _check_existing_id()):
            self[existing_session_id].delete()
        session = _from_record({
            "id": uid.generate_category_uid(f"{PROVIDER}-login_session"),
            "expiry_seconds": expiry_seconds,
            "client_id": str(client_id),
            "user_id": str(user_id) if user_id else None,
            "device_id": device_id,
            "agent_string": agent_string,
        })
        try:
            session_storage.insert_one(session.to_storage())
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            flask.session[_session_key(PROVIDER)] = session.id
            return session


class LoginSessionResource:
    """Represents a login session resource in Campus API Schema."""

    def __init__(self, session_id: schema.CampusID | None = None):
        self.session_id = session_id

    def delete(self, sync_client: bool = True) -> None:
        """Delete this auth session."""
        # Check if session exists client-side
        session_id = (self.session_id or _check_existing_id())
        if not session_id:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        if sync_client:
            session_id = _verify_session_id(session_id)
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
            if sync_client and _session_key(PROVIDER) in flask.session:
                del flask.session[_session_key(PROVIDER)]

    def get(self) -> campus.model.LoginSession:
        """Get the login session record.

        Returns:
            LoginSession instance
        """
        session_id = self.session_id
        record = session_storage.get_by_id(str(session_id))
        if not record:
            raise api_errors.NotFoundError(
                f"Session '{session_id}' not found",
                session_id=session_id
            )
        return _from_record(record)

    def update(self, **update) -> campus.model.LoginSession:
        """Update an existing session."""
        session_id = self.session_id
        if not session_id:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        _verify_session_id(session_id)
        # TODO: Validate update fields
        for immutable_key in (
            schema.CAMPUS_KEY,
            "client_id",
            "user_id",
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
        session = self.get()
        assert session
        return session


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.LoginSession:
    """Convert a storage record to a LoginSession model instance."""
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
    args["device_id"] = record.get("device_id")
    args["agent_string"] = record["agent_string"]
    return campus.model.LoginSession(**args)


def _session_key(provider: str) -> str:
    """Get the session key for the provider."""
    return f"{provider}_session_id"


def init_storage() -> None:
    """Initialize storage for client authentication."""
    # Document store does not require initialization
    pass


def _check_existing_id() -> schema.CampusID | None:
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
    session_key = _session_key(PROVIDER)
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
        session_id: schema.CampusID
) -> schema.CampusID:
    """Verify the session ID against the stored session.
    Raises:
        ConflictError if there is a mismatch.
        NotFoundError if no session ID is found in the client.
    
    This avoids accidental deletion of a session that does not
    belong to the client.
    """
    client_session_id = _check_existing_id()
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
