"""campus.models.session.login

Login sessions are long-lived records of user activity associated with a
specific:
- application (client_id)
- user (user_id)
- device (device_id)
(client_id, user_id, device_id) constitute a unique key for a login session.
The session_id is stored client-side in a cookie, and used as a primary
identifier.
Sessions must have an expiry datetime, for pruning.
Sessions are only initiated by client, but may be revoked by either party.
"""

from dataclasses import dataclass
from typing import Optional

from flask import session as client_session

from campus.common import env, schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
from campus.models.base import BaseRecord
from campus.storage import (
    errors as storage_errors,
    get_collection
)

# Type aliases
Url = str

COLLECTION = "login_sessions"
SESSION_KEY = "session_id"
DEFAULT_LOGIN_EXPIRY_DAYS = 30
DEFAULT_OAUTH_EXPIRY_MINUTES = 10


@dataclass(eq=False, kw_only=True)
class LoginSessionRecord(BaseRecord):
    """Dataclass representation of a login session record."""
    # id and created_at inherited from BaseRecord
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID | None = None
    device_id: str | None = None
    # TODO: add ip_address
    # TODO: add last_login?
    agent_string: str

    def __post_init__(self):
        """Set expiry time based on creation timestamp."""
        if self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=DEFAULT_LOGIN_EXPIRY_DAYS * utc_time.DAY_SECONDS
            )

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the session is expired."""
        if at_time is None:
            at_time = schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )



class LoginSessions:
    """Model for login sessions.

    This model represents a LoginSession in the database.
    Sessions are manipulated by session_id. Where session_id is not provided,
    the session_id stored in the client cookie will be used.
    """

    def __init__(self):
        """Initialize the Session model with a collection storage interface."""
        self.storage = get_collection(COLLECTION)

    def _check_existing_id(self) -> schema.CampusID | None:
        """Check if a session already exists.

        A session exists if:
        - there is a session_id stored in the client cookie, and
        - a session with that ID exists on the server.
        Returns the session ID if a session exists, otherwise None.
        """
        client_session_id = client_session.get(SESSION_KEY)
        if not client_session_id:
            return None
        try:
            self.storage.get_by_id(client_session_id)
        except storage_errors.NotFoundError:
            return None
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return client_session_id

    def _verify_session_id(
            self,
            session_id: schema.CampusID
    ) -> schema.CampusID:
        """Verify the session ID against the stored session.
        Raises ConflictError if there is a mismatch.
        Raises NotFoundError if no session ID is found in the client.
        This avoids accidental deletion of a session that does not belong to the
        client.
        """
        client_session_id = self._check_existing_id()
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
            self,
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
        session_id = session_id or self._check_existing_id()
        if not session_id:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        if sync_client:
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
            if sync_client and SESSION_KEY in client_session:
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
    ) -> list[LoginSessionRecord]:
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
            return [LoginSessionRecord(**r) for r in records]

    def get(
            self,
            session_id: schema.CampusID | None = None
    ) -> LoginSessionRecord | None:
        """Retrieve a session by its ID, or return None if not found.

        If session_id is not provided, uses the session ID from the client
        cookie.
        """
        if session_id:
            return self.get_by_id(session_id)
        existing_session_id = self._check_existing_id()
        if existing_session_id is not None:
            return self.get_by_id(existing_session_id)
        return None

    def get_by_id(self, session_id: schema.CampusID) -> LoginSessionRecord:
        """Retrieve a session by its ID."""
        try:
            record = self.storage.get_by_id(session_id)
        except storage_errors.NotFoundError:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
        else:
            assert record is not None
            return LoginSessionRecord.from_dict(record)

    def new(
        self,
        *,
        agent_string: str,
        client_id: schema.CampusID,
        expiry_seconds: int = DEFAULT_LOGIN_EXPIRY_DAYS * utc_time.DAY_SECONDS,
        user_id: schema.UserID | None = None,
        session_id: Optional[schema.CampusID] = None,
        created_at: Optional[schema.DateTime] = None,
    ) -> LoginSessionRecord:
        """Create a new session.

        Any existing session will be revoked.
        """
        # Delete any existing session
        if (existing_id := self._check_existing_id()):
            self.delete(existing_id)
        created_at = created_at or schema.DateTime.utcnow()
        expires_at = schema.DateTime.utcafter(
            created_at, seconds=expiry_seconds
        )
        session = LoginSessionRecord(
            id=session_id or uid.generate_category_uid(COLLECTION),
            created_at=created_at,
            expires_at=expires_at,
            client_id=client_id,
            user_id=user_id,
            agent_string=agent_string,
        )
        try:
            self.storage.insert_one(session.to_dict())
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
        else:
            client_session[SESSION_KEY] = session.id
            return session

    def sweep(
            self,
            *,
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired sessions from the database.

        Returns the number of deleted sessions.
        """
        at_time = at_time or schema.DateTime.utcnow()
        # TODO: implement query DSL for ranges
        try:
            records = self.storage.get_matching({})
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        deleted_ids = []
        # TODO: Optimize to do this in a single query
        for record in records:
            if schema.DateTime(record["expires_at"]) <= at_time:
                self.delete(record[schema.CAMPUS_KEY], sync_client=False)
                deleted_ids.append(record[schema.CAMPUS_KEY])
        return len(deleted_ids)

    def update(
            self,
            session_id: schema.CampusID | None = None,
            **update
    ) -> LoginSessionRecord:
        """Update an existing session."""
        session_id = session_id or self._check_existing_id()
        if not session_id:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from None
        self._verify_session_id(session_id)
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
            self.storage.update_by_id(session_id, update)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Session not found",
                session_id=session_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError.from_exception(e) from e
        else:
            return self.get_by_id(session_id)
