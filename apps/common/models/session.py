"""apps.common.models.session

Session model for the Campus API.

Sessions are short-lived processes, typically used for authentication state.
"""

from apps.common.errors import api_errors
from storage import get_collection
from common.schema import CampusID

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
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, session_id: CampusID) -> dict:
        """Retrieve an OAuth session by its ID."""
        try:
            record = self.storage.get_by_id(session_id)
            if record is None:
                api_errors.raise_api_error(404, message="Session not found")
            
            # Remove id primary key: only needed by the backend interface.
            # Make a copy to avoid modifying the original
            session_data = dict(record)
            if "id" in session_data and "state" in session_data:
                assert session_data["id"] == session_data["state"]
                del session_data["id"]
            return session_data
        except Exception as e:
            if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
                raise  # Re-raise API errors as-is
            raise api_errors.InternalError(message=str(e), error=e)

    def store(self, session: dict) -> None:
        """Store an OAuth session."""
        try:
            # Add id primary key which is needed by the backend interface.
            session_data = dict(session)
            session_data["id"] = session_data["state"]
            self.storage.insert_one(session_data)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
