"""campus.models.session

Session model for the Campus API.

Sessions are short-lived processes, typically used for authentication state.
"""

from campus.common.errors import api_errors
from campus.storage import get_collection
from campus.common.schema import CampusID
from campus.storage import errors as storage_errors

COLLECTION = "sessions"


class Session:
    """Model for Sessions.

    This model represents a Session in the database.
    """

    def __init__(self):
        """Initialize the Session model with a collection storage interface."""
        self.storage = get_collection(COLLECTION)

    def delete(self, session_id: CampusID) -> None:
        """Delete an OAuth session by its ID."""
        try:
            self.storage.delete_by_id(session_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.ConflictError(
                message="Session not found",
                session_id=session_id
            ) from e
        except storage_errors.ConflictError as e:
            raise api_errors.ConflictError(
                message="Session conflict",
                session_id=session_id
            ) from e
        except storage_errors.NoChangesAppliedError as e:
            raise api_errors.ConflictError(
                message="No session deleted",
                session_id=session_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, session_id: CampusID) -> dict:
        """Retrieve an OAuth session by its ID."""
        try:
            record = self.storage.get_by_id(session_id)
        except storage_errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        # Remove id primary key: only needed by the backend interface.
        # Make a copy to avoid modifying the original
        session_data = dict(record)
        if "id" in session_data and "state" in session_data:
            assert session_data["id"] == session_data["state"]
            del session_data["id"]
        return session_data

    def store(self, session: dict) -> None:
        """Store an OAuth session."""
        session_data = dict(session)
        session_data["id"] = session_data["state"]
        try:
            # Add id primary key which is needed by the backend interface.
            self.storage.insert_one(session_data)
        except storage_errors.ConflictError as e:
            raise api_errors.ConflictError(
                message="Session conflict",
                session_id=session.get("state")
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
