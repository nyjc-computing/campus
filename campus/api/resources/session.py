"""campus.api.resources.session

Session resource for Campus API.
"""

import typing

import flask

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
import campus.model
import campus.storage

session_storage = campus.storage.get_collection("login_sessions")

SESSION_KEY = "session_id"
DEFAULT_LOGIN_EXPIRY_DAYS = 30


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.LoginSession:
    """Convert a storage record to a LoginSession model instance."""
    return campus.model.LoginSession(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        expires_at=schema.DateTime(record['expires_at']),
        client_id=schema.CampusID(record['client_id']),
        user_id=schema.UserID(record['user_id']) if record.get(
            'user_id') else None,
        device_id=record.get('device_id'),
        agent_string=record['agent_string'],
        expiry_seconds=None  # Already have expires_at
    )


class SessionsResource:
    """Represents the login sessions resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for session management."""
        session_storage.init_from_model(
            "login_sessions", campus.model.LoginSession)

    def __getitem__(self, session_id: schema.CampusID) -> "SessionResource":
        """Get a session resource by session ID.

        Args:
            session_id: The session ID

        Returns:
            SessionResource instance
        """
        return SessionResource(session_id)

    def _check_existing_id(self) -> schema.CampusID | None:
        """Check if a session already exists in the client cookie.

        Returns:
            Session ID if a session exists, otherwise None
        """
        client_session_id = flask.session.get(SESSION_KEY)
        if not client_session_id:
            return None
        try:
            session_storage.get_by_id(client_session_id)
        except campus.storage.errors.NotFoundError:
            return None
        return client_session_id

    def find(
            self,
            *,
            client_id: schema.CampusID | None = None,
            user_id: schema.UserID | None = None,
            agent_string: str | None = None,
            limit: int = 100,
    ) -> list[campus.model.LoginSession]:
        """Find sessions matching the given criteria.

        Args:
            client_id: Filter by client ID
            user_id: Filter by user ID
            agent_string: Filter by user agent string
            limit: Maximum number of results

        Returns:
            List of LoginSession instances

        Raises:
            InvalidRequestError: If no filter is provided
        """
        query = {}
        if client_id:
            query["client_id"] = client_id
        if user_id:
            query["user_id"] = user_id
        if agent_string:
            query["agent_string"] = agent_string
        if not query:
            raise api_errors.InvalidRequestError(
                "At least one filter must be provided"
            )
        query["$limit"] = limit
        records = session_storage.get_matching(query)
        return [_from_record(record) for record in records]

    def get(
            self,
            session_id: schema.CampusID | None = None
    ) -> campus.model.LoginSession | None:
        """Retrieve a session by its ID.

        Args:
            session_id: The session ID (uses client cookie if None)

        Returns:
            LoginSession instance or None if not found
        """
        if session_id:
            return self[session_id].get()
        existing_session_id = self._check_existing_id()
        if existing_session_id is not None:
            return self[existing_session_id].get()
        return None

    def new(
        self,
        *,
        agent_string: str,
        client_id: schema.CampusID,
        expiry_seconds: int = DEFAULT_LOGIN_EXPIRY_DAYS * utc_time.DAY_SECONDS,
        user_id: schema.UserID | None = None,
        session_id: schema.CampusID | None = None,
        created_at: schema.DateTime | None = None,
    ) -> campus.model.LoginSession:
        """Create a new session.

        Args:
            agent_string: User agent string
            client_id: The client identifier
            expiry_seconds: Session expiry in seconds
            user_id: The user identifier (optional)
            session_id: Custom session ID (optional)
            created_at: Custom creation time (optional)

        Returns:
            LoginSession instance
        """
        # Delete any existing session
        if (existing_id := self._check_existing_id()):
            self[existing_id].delete()

        created_at = created_at or schema.DateTime.utcnow()
        session = campus.model.LoginSession(
            id=session_id or uid.generate_category_uid("login_session"),
            created_at=created_at,
            client_id=client_id,
            user_id=user_id,
            agent_string=agent_string,
            expiry_seconds=expiry_seconds
        )
        session_storage.insert_one(session.to_storage())
        flask.session[SESSION_KEY] = session.id
        return session

    def sweep(
            self,
            *,
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired sessions from the database.

        Args:
            at_time: Reference time for expiry check (default: now)

        Returns:
            Number of deleted sessions
        """
        at_time = at_time or schema.DateTime.utcnow()
        records = session_storage.get_matching({})
        deleted_ids = []
        for record in records:
            if schema.DateTime(record["expires_at"]) <= at_time:
                self[record[schema.CAMPUS_KEY]].delete(sync_client=False)
                deleted_ids.append(record[schema.CAMPUS_KEY])
        return len(deleted_ids)


class SessionResource:
    """Represents a single login session in Campus API Schema."""

    def __init__(self, session_id: schema.CampusID):
        self.session_id = session_id

    def _verify_session_id(self) -> schema.CampusID:
        """Verify the session ID against the stored session.

        Raises:
            ConflictError: If there is a mismatch
            NotFoundError: If no session ID is found in the client
        """
        client_session_id = flask.session.get(SESSION_KEY)
        if client_session_id and self.session_id != client_session_id:
            raise api_errors.ConflictError(
                "Mismatch with client session ID",
                session_id=self.session_id
            )
        if not client_session_id:
            raise api_errors.NotFoundError(
                "No session ID in client",
                session_id=self.session_id
            )
        return client_session_id

    def delete(self, sync_client: bool = True) -> None:
        """Delete a session by its ID.

        Args:
            sync_client: If True, also removes the session ID from client cookie

        Raises:
            NotFoundError: If session not found
            ConflictError: If session ID mismatch
        """
        if sync_client:
            self._verify_session_id()

        try:
            session_storage.delete_by_id(self.session_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Session not found",
                session_id=self.session_id
            ) from None

        if sync_client and SESSION_KEY in flask.session:
            del flask.session[SESSION_KEY]

    def get(self) -> campus.model.LoginSession:
        """Retrieve a session by its ID.

        Returns:
            LoginSession instance

        Raises:
            NotFoundError: If session not found
        """
        record = session_storage.get_by_id(self.session_id)
        if not record:
            raise api_errors.NotFoundError(
                "Session not found",
                session_id=self.session_id
            )
        return _from_record(record=record)

    def update(self, **update: typing.Any) -> campus.model.LoginSession:
        """Update an existing session.

        Args:
            **update: Fields to update

        Returns:
            Updated LoginSession instance

        Raises:
            InvalidRequestError: If trying to update immutable field
            NotFoundError: If session not found
        """
        self._verify_session_id()

        for immutable_key in (
            schema.CAMPUS_KEY,
            "client_id",
            "user_id",
            "agent_string",
            "created_at",
        ):
            if immutable_key in update:
                raise api_errors.InvalidRequestError(
                    f"Cannot update immutable field: {immutable_key}"
                )

        try:
            session_storage.update_by_id(self.session_id, update)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Session not found",
                session_id=self.session_id
            ) from None

        return self.get()
