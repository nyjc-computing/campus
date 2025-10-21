"""campus.models.session

Login Session model for the Campus API.

Sessions are long-lived records of authentication associated with a specific:
- application (client_id)
- user (user_id)
- device (agent_string)
(client_id, user_id, agent_string) constitute a unique key for a session.
The session_id is stored client-side in a cookie, and used as a primary
identifier.
Sessions must have an expiry datetime, for pruning.
Sessions are only initiated by client, but may be revoked by either party.

Additional metadata may be included, e.g. for use for OAuth

For authenticated HTTP requests in the Campus API, clients must include 
the session_id (in cookie), client_id (in header), and access_token (in header).
user_id is retrieved from the session record.
The access token itself is not stored in sessions; it's validated per-request.
"""

from typing import NotRequired, Required, TypedDict, cast

from flask import session as client_session

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.common.validation.record as record_validation
from campus.models.base import BaseRecordDict
from campus.storage import (
    errors as storage_errors,
    get_collection
)

COLLECTION = "sessions"
SESSION_KEY = "session_id"


class SessionRecord(BaseRecordDict):
    """Schema for a full session record."""
    expires_at: str
    client_id: schema.CampusID
    user_id: schema.UserID
    agent_string: str
    # fields for OAuth sessions
    scopes: NotRequired[list[str]]
    authorization_code: NotRequired[str]
    target: NotRequired[str]
    redirect_uri: NotRequired[str]


class SessionNew(TypedDict, total=False):
    """Schema for a new session request."""
    client_id: Required[schema.CampusID]
    user_id: Required[schema.UserID]
    agent_string: str
    # A session may include specific scopes
    scopes: list[str]


class Sessions:
    """Model for Sessions.

    This model represents a Session in the database.
    Sessions are manipulated by session_id. Where session_id is not provided,
    the session_id stored in the client cookie will be used.
    """

    def __init__(self):
        """Initialize the Session model with a collection storage interface."""
        self.storage = get_collection(COLLECTION)

    def _verify_session_id(
            self,
            session_id: schema.CampusID | None = None
    ) -> schema.CampusID:
        """Get the session ID from the client cookie, if it exists.
        If session_id is provided, it is verified against the client cookie and
        returned if they match.
        Returns None if no session ID is found or if there is a mismatch.
        This avoids accidental deletion of a session that does not belong to the
        client.
        """
        client_session_id = client_session.get(SESSION_KEY)
        if session_id and session_id != client_session_id:
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

    def delete(self, session_id: schema.CampusID | None = None) -> None:
        """Delete a session by its ID."""
        # Check if session exists client-side
        session_id = self._verify_session_id(session_id)
        # Remove server-side session
        try:
            self.storage.delete_by_id(session_id)
        except storage_errors.NotFoundError:
            raise api_errors.ConflictError(
                message="Session not found",
                session_id=session_id
            )
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            # For consistency, only remove client-side session after
            # successful server-side deletion
            del client_session[SESSION_KEY]

    def find(
            self,
            *,
            client_id: schema.CampusID | None = None,
            user_id: schema.UserID | None = None,
            agent_string: str | None = None,
            # expire_after: schema.DateTime | None = None,
            # expire_before: schema.DateTime | None = None,
            limit: int = 100,
    ) -> list[SessionRecord]:
        """Find sessions matching the given criteria.
        At least one filter must be provided.
        """
        query = {}
        if client_id:
            query["client_id"] = client_id
        if user_id:
            query["user_id"] = user_id
        if agent_string:
            query["agent_string"] = agent_string
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
            records = self.storage.get_matching(query)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return [SessionRecord(**r) for r in records]

    def get(
            self,
            session_id: schema.CampusID | None = None
    ) -> SessionRecord | None:
        """Retrieve a session by its ID, or return None if not found.
        
        If session_id is not provided, uses the session ID from the client
        cookie.
        """
        session_id = self._verify_session_id(session_id)
        return self.get_by_id(session_id)

    def get_by_id(self, session_id: schema.CampusID) -> SessionRecord:
        """Retrieve a session by its ID."""
        try:
            record = self.storage.get_by_id(session_id)
        except storage_errors.NotFoundError:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return cast(SessionRecord, record)

    def new(self, session_data: dict, *, expiry_seconds: int) -> SessionRecord:
        """Create a new session.

        Any existing session will be revoked.
        """
        # Delete any existing session
        try:
            session_id = self._verify_session_id()
        except (api_errors.NotFoundError, api_errors.ConflictError):
            # No existing session, or mismatch - ignore
            pass
        else:
            self.delete(session_id)
        record_validation.validate_keys(
            session_data,
            valid_keys=SessionNew.__annotations__,
            ignore_extra=False,
        )
        session_id = uid.generate_category_uid(COLLECTION)
        session_data[schema.CAMPUS_KEY] = session_id
        now = schema.DateTime.utcnow()
        session_data["created_at"] = now
        session_data["expires_at"] = schema.DateTime.utcafter(
            now, seconds=expiry_seconds
        )
        try:
            self.storage.insert_one(session_data)
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
        else:
            client_session[SESSION_KEY] = session_data[schema.CAMPUS_KEY]
            return cast(SessionRecord, session_data)

    def update(
            self,
            session_id: schema.CampusID | None = None,
            **update
    ) -> SessionRecord:
        """Update an existing session."""
        session_id = self._verify_session_id(session_id)
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
            self.storage.update_by_id(session_id, update)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Session not found",
                session_id=session_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
        else:
            return cast(SessionRecord, self.get_by_id(session_id))
