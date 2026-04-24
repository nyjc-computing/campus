"""campus.auth.resources.login

Login session resource for Campus API.
"""

import typing

import flask

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
import campus.config as config
import campus.model as model
import campus.storage

PROVIDER = "campus"

login_storage = campus.storage.get_collection("login_sessions")


class LoginSessionsResource:
    """Represents the login sessions resource in Campus API Schema.
    
    Note that this only manages Campus logins, not for external
    authentication providers.
    """

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for login resource."""
        login_storage.init_from_model(
            "login_sessions", model.LoginSession
        )

    def __getitem__(
            self,
            session_id: schema.CampusID | str
    ) -> "LoginSessionResource":
        """Get a login session resource.

        Returns:
            LoginSessionResource instance
        """
        return LoginSessionResource(session_id)

    def new(
            self,
            *,
            # expiry_seconds: int,
            client_id: schema.CampusID | str,
            user_id: schema.UserID | None = None,
            device_id: str | None = None,
            agent_string: str,
    ) -> model.LoginSession:
        """Create a new session.

        Any existing session will be revoked.
        """
        login_expiry_seconds = (
            config.DEFAULT_LOGIN_EXPIRY_DAYS * utc_time.DAY_SECONDS
        )
        # Delete any existing session
        if (existing_session_id := _check_existing_id()):
            self[existing_session_id].delete()
        session = _from_record({
            "id": uid.generate_category_uid(f"{PROVIDER}-login_session"),
            "expiry_seconds": login_expiry_seconds,
            "client_id": str(client_id),
            "user_id": str(user_id) if user_id else None,
            "device_id": device_id,
            "agent_string": agent_string,
        })
        try:
            login_storage.insert_one(session.to_storage())
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            flask.session[_session_key(PROVIDER)] = session.id
            return session


class LoginSessionResource:
    """Represents a login session resource in Campus API Schema."""

    def __init__(self, session_id: schema.CampusID | str | None = None):
        self.session_id = schema.CampusID(session_id) if session_id else None

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
            login_storage.delete_by_id(session_id)
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

    def get(self) -> model.LoginSession:
        """Get the login session record.

        Returns:
            LoginSession instance
        """
        session_id = self.session_id
        record = login_storage.get_by_id(str(session_id))
        if not record:
            raise api_errors.NotFoundError(
                f"Session '{session_id}' not found",
                session_id=session_id
            )
        return _from_record(record)

    def update(self, **update) -> model.LoginSession:
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
            login_storage.update_by_id(session_id, update)
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
) -> model.LoginSession:
    """Convert a storage record to a LoginSession model instance."""
    args: dict[str, typing.Any] = {}
    if "id" in record:
        args["id"] = schema.CampusID(record["id"])
    if "created_at" in record and record["created_at"] is not None:
        args["created_at"] = schema.DateTime(record["created_at"])
    if "expires_at" in record and record["expires_at"] is not None:
        args["expires_at"] = schema.DateTime(record["expires_at"])
    if "expiry_seconds" in record and record["expiry_seconds"] is not None:
        args["expiry_seconds"] = record["expiry_seconds"]
    args["client_id"] = schema.CampusID(record["client_id"])
    if "user_id" in record:
        args["user_id"] = schema.UserID(record["user_id"])
    args["device_id"] = record.get("device_id")
    args["agent_string"] = record["agent_string"]
    return model.LoginSession(**args)


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
        login_storage.get_by_id(client_session_id)
    except campus.storage.errors.NotFoundError:
        # Revoke client-side
        flask.session.pop(session_key, None)
        return None
    except Exception as e:
        raise api_errors.InternalError.from_exception(e)
    else:
        return client_session_id


def _verify_session_id(
        session_id: schema.CampusID | str
) -> schema.CampusID:
    """Verify the session ID against the stored session.
    Raises:
        ConflictError if there is a mismatch.
        NotFoundError if no session ID is found in the client.
    
    This avoids accidental deletion of a session that does not
    belong to the client.
    """
    session_id = schema.CampusID(session_id)
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
