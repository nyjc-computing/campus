"""apps.common.models.session

Session model for the Campus API.

Sessions are short-lived processes, typically used for authentication state.
"""

from apps.common.errors import api_errors
from common.drum.mongodb import get_drum, PK
from common.schema import CampusID

TABLE = "sessions"


class Session:
    """Model for Sessions.

    This model represents a Session in the database.
    """

    def __init__(self):
        pass

    def delete(self, session_id: CampusID) -> None:
        """Delete an OAuth session by its ID."""
        get_drum().delete_by_id(TABLE, session_id)

    def get(self, session_id: CampusID) -> dict:
        """Retrieve an OAuth session by its ID."""
        resp = get_drum().get_by_id(TABLE, session_id)
        match resp.status:
            case "error":
                api_errors.raise_api_error(404, message="Session not found")
            case "ok":
                record = resp.data
                assert record[PK] == record["state"]
                del record[PK]
                return record
        raise AssertionError(f"Unexpected response: {resp}")

    def store(self, session_id: CampusID, session: dict) -> None:
        """Store an OAuth session with the given ID and data."""
        # Add id primary key which is needed by the Drum interface.
        session["id"] = session_id
        get_drum().insert(TABLE, session)
