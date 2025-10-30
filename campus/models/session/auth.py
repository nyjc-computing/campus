"""campus.models.session.auth

Auth sessions are short-lived records of authentication attempts,
typically used in OAuth flows. They are associated with a specific:
- provider (e.g. google, github, campus)
- application (client_id)
- user (user_id) (may be anonymous initially)
(provider, client_id, user_id) constitute a unique key for an auth
session.
A randomized state is generated and stored client-side to verify the
session, as a precaution against CSRF attacks.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from flask import session as client_session

from campus.common import env, schema
from campus.common.errors import api_errors
from campus.common.utils import secret, uid, utc_time
from campus.models.base import BaseRecord
from campus.storage import (
    errors as storage_errors,
    get_collection
)

COLLECTION = "auth_sessions"
DEFAULT_LOGIN_EXPIRY_DAYS = 30
DEFAULT_OAUTH_EXPIRY_MINUTES = 10


@dataclass(eq=False, kw_only=True)
class AuthSessionRecord(BaseRecord):
    """Dataclass representation of an auth session record."""
    # id and created_at inherited from BaseRecord
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID | None = None
    # TODO: add ip_address
    redirect_uri: schema.Url
    scopes: list[str] = field(default_factory=list)
    authorization_code: Optional[str] = None
    state: Optional[str] = None
    target: Optional[schema.Url] = None

    def __post_init__(self):
        """Set expiry time based on creation timestamp.
        Cast attributes to correct types.
        """
        if self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=DEFAULT_OAUTH_EXPIRY_MINUTES * 60
            )

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the session is expired."""
        if at_time is None:
            at_time = schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthSessionRecord":
        """Create an AuthSessionRecord from a dictionary, ensuring
        correct types."""
        args: dict[str, Any] = {}
        if "id" in data:
            args["id"] = schema.CampusID(data["id"])
        if "created_at" in data:
            args["created_at"] = schema.DateTime(data["created_at"])
        if "expires_at" in data:
            args["expires_at"] = schema.DateTime(data["expires_at"])
        args["client_id"] = schema.CampusID(data["client_id"])
        if "user_id" in data:
            args["user_id"] = schema.UserID(data["user_id"])
        args["redirect_uri"] = schema.Url(data["redirect_uri"])
        if "scopes" in data:
            data["scopes"] = data["scopes"]
        if "authorization_code" in data:
            args["authorization_code"] = data["authorization_code"]
        if "target" in data and data["target"] is not None:
            args["target"] = schema.Url(data["target"])
        return cls(**args)


# class SessionNew(TypedDict, total=False):
#     """Schema for a new session request."""
#     id: schema.CampusID
#     created_at: schema.DateTime
#     expires_at: schema.DateTime
#     client_id: Required[schema.CampusID]
#     user_id: Required[schema.UserID]
#     device_id: Required[str]
#     agent_string: str
#     # A session may include specific scopes
#     scopes: list[str]


class AuthSessions:
    """Model for auth sessions.

    This model represents an AuthSession in the database.
    Sessions are manipulated by session_id. Where session_id is not provided,
    the session_id stored in the client cookie will be used.
    """

    def __init__(self, provider: str):
        """Initialize the Session model with a collection storage interface."""
        self.storage = get_collection(COLLECTION)
        self.provider = provider

    def _session_key(self) -> str:
        """Get the session key for the provider."""
        return f"{self.provider}_session_id"

    def _check_existing_id(self) -> schema.CampusID | None:
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
        session_key = self._session_key()
        client_session_id = client_session.get(session_key)
        if not client_session_id:
            return None
        try:
            self.storage.get_by_id(client_session_id)
        except storage_errors.NotFoundError:
            # Revoke client-side
            client_session.pop(session_key, None)
            return None
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            return client_session_id

    def _verify_session_id(
            self,
            session_id: schema.CampusID
    ) -> schema.CampusID:
        """Verify the session ID against the stored session.
        Raises:
            ConflictError if there is a mismatch.
            NotFoundError if no session ID is found in the client.
        
        This avoids accidental deletion of a session that does not
        belong to the client.
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
            # Session already deleted server-side
            # TODO: logging for missing session
            pass
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            # For consistency, only remove client-side session after
            # successful server-side deletion
            if sync_client and self._session_key() in client_session:
                del client_session[self._session_key()]

    def finalize(
            self,
            auth_session: AuthSessionRecord
    ) -> schema.Url | None:
        """Finalize an auth session and return the redirect URI.
        This typically involves cleaning up the session and preparing
        for redirection to the target.
        """
        self.delete(auth_session.id)
        return auth_session.redirect_uri

    def find(
            self,
            *,
            client_id: schema.CampusID | None = None,
            user_id: schema.UserID | None = None,
            # expire_after: schema.DateTime | None = None,
            # expire_before: schema.DateTime | None = None,
            limit: int = 100,
    ) -> list[AuthSessionRecord]:
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
            records = self.storage.get_matching(query)
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            return [AuthSessionRecord.from_dict(r) for r in records]

    def get(
            self,
            session_id: schema.CampusID | None = None
    ) -> AuthSessionRecord | None:
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

    def get_by_id(
            self,
            session_id: schema.CampusID
    ) -> AuthSessionRecord | None:
        """Retrieve a session by its ID."""
        try:
            record = self.storage.get_by_id(session_id)
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        if not record:
            return None
        return AuthSessionRecord.from_dict(record)

    def new(
        self,
        *,
        client_id: schema.CampusID,
        expiry_seconds: int = DEFAULT_OAUTH_EXPIRY_MINUTES * 60,
        redirect_uri: schema.Url,
        user_id: schema.UserID | None = None,
        session_id: Optional[schema.CampusID] = None,
        created_at: Optional[schema.DateTime] = None,
        scopes: list[str] | None = None,
        authorization_code: Optional[str] = None,
        state: Optional[str] = None,
        target: Optional[schema.Url] = None,
    ) -> AuthSessionRecord:
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
        session = AuthSessionRecord(
            id=session_id or uid.generate_category_uid(f"{self.provider}-session"),
            created_at=created_at,
            expires_at=expires_at,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes or [],
            authorization_code=(
                authorization_code
                or secret.generate_authorization_code()
            ),
            state=state,
            target=target,  # TODO: deprecate for client impl
        )
        try:
            self.storage.insert_one(session.to_dict())
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            client_session[self._session_key()] = session.id
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
            raise api_errors.InternalError.from_exception(e)
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
    ) -> AuthSessionRecord:
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
            raise api_errors.InternalError.from_exception(e)
        session = self.get_by_id(session_id)
        assert session
        return session
