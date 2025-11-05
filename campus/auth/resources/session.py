"""campus.auth.resources.session

Auth session resource for Campus API.

Client-side session management is handled by first-/third-party apps,
e.g. through campus-api-python
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors, auth_errors
from campus.common.utils import uid, secret
import campus.model
import campus.storage

session_storage = campus.storage.get_collection("auth_sessions")


def init_storage() -> None:
    """Initialize storage for client authentication."""
    # Document store does not require initialization
    pass


class AuthSessionsResource:
    """Represents the auth sessions resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for session resource."""
        session_storage.init_from_model(
            "auth_sessions", campus.model.AuthSession
        )

    def __getitem__(
            self,
            provider: str
    ) -> "ProviderAuthSessionResource":
        """Get a provider session resource by provider.

        Args:
            provider: The provider identifier

        Returns:
            ProviderSessionResource instance
        """
        return ProviderAuthSessionResource(provider)

    def sweep(
            self,
            *,
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired sessions from the database.

        Returns the number of deleted sessions.
        """
        expired_records = (
            campus.model.AuthSession.from_storage(r)
            for r in session_storage.get_matching({})
        )
        expired_sessions = (
            s for s in expired_records if s.is_expired(at_time=at_time)
        )
        deletion_count = 0
        for session in expired_sessions:
            session_storage.delete_by_id(session.id)
            deletion_count += 1
        return deletion_count


class ProviderAuthSessionResource:
    """Represents a single auth session resource for a provider."""

    def __init__(self, provider: str):
        self.provider = provider

    def __getitem__(
            self,
            session_id: schema.CampusID
    ) -> "AuthSessionResource":
        """Get an auth session by ID.

        Args:
            session_id: The session identifier

        Returns:
            AuthSessionResource instance
        """
        return AuthSessionResource(self, session_id)

    def get(self, code: str) -> campus.model.AuthSession:
        """Get the auth session for this provider by authorization code.

        Args:
            code: authorization code to match

        Returns:
            AuthSession instance or None if not found
        """
        record = session_storage.get_matching({"authorization_code": code})
        if not record:
            raise auth_errors.AccessDeniedError("Invalid authorization code")
        session = _from_record(record[0])
        if session.provider != self.provider:
            raise auth_errors.AccessDeniedError("Invalid authorization code")
        return self[session.id].get()

    def new(
        self,
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
        """Create a new session."""
        session = _from_record({
            "id": uid.generate_category_uid(f"{self.provider}-session"),
            "expiry_seconds": expiry_seconds,
            "client_id": client_id,
            "user_id": user_id,
            "redirect_uri": redirect_uri,
            "scopes": scopes or [],
            "authorization_code": (
                authorization_code
                or secret.generate_authorization_code()
            ),
            "state": state,
            "target": target,
        })
        try:
            session_storage.insert_one(session.to_storage())
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)
        else:
            return session


class AuthSessionResource:
    """Represents a single auth session."""

    def __init__(
            self,
            parent: ProviderAuthSessionResource,
            session_id: schema.CampusID
    ):
        self.parent = parent
        self.session_id = session_id

    def delete(self) -> None:
        """Delete this auth session."""
        try:
            session_storage.delete_by_id(self.session_id)
        except campus.storage.errors.NotFoundError:
            # Session already deleted server-side
            # TODO: logging for missing session
            pass
        except Exception as e:
            raise api_errors.InternalError.from_exception(e)

    def finalize(self) -> schema.Url | None:
        """Finalize an auth session and return the redirect URI.
        This typically involves cleaning up the session and preparing
        for redirection to the target.
        """
        auth_session = self.get()
        self.delete()
        return auth_session.target

    def get(self) -> campus.model.AuthSession:
        """Get the auth session record.

        Returns:
            AuthSession instance
        """
        record = session_storage.get_by_id(self.session_id)
        if not record:
            raise api_errors.NotFoundError(
                f"Session '{self.session_id}' not found",
                session_id=self.session_id
            )
        return _from_record(record)

    def update(
            self,
            session_id: schema.CampusID,
            *,
            user_id: schema.UserID
    ) -> campus.model.AuthSession:
        """Update an existing session.
        
        Only user_id can be updated, since it will only be known after
        user has authenticated.
        """
        provider = self.parent.provider
        try:
            session_storage.update_by_id(
                session_id,
                {"user_id": str(user_id)}
            )
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
