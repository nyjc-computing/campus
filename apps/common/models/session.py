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
                # Remove id primary key: only needed by the Drum interface.
                assert record[PK] == record["state"]
                del record[PK]
                return record

    def store(self, session: dict) -> None:
        """Store an OAuth session."""
        # Add id primary key which is needed by the Drum interface.
        session[PK] = session["state"]
        get_drum().insert(TABLE, session)
