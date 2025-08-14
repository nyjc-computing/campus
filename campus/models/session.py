"""campus.models.session

Session model for the Campus API.

Sessions are short-lived processes, typically used for authentication state.
Sessions are identified by a unique session ID, which is stored client-side
    using cookies or local storage.
Sessions must have an expiry datetime, for pruning.
"""

from typing import TypedDict

from campus.common.errors import api_errors
from campus.common.schema import CampusID
from campus.models.base import BaseRecord
from campus.storage import (
    errors as storage_errors,
    get_collection
)

COLLECTION = "sessions"


class SessionRecord(BaseRecord):
    """Schema for a full session record."""
    expires_at: str


class SessionNew(TypedDict, total=False):
    """Schema for a new session request."""
    expires_at: str


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
