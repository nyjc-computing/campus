"""campus.models.session

Session model for the Campus API.

Sessions are short-lived processes, typically used for authentication state.
Sessions are identified by a unique session ID, which is stored client-side
    using cookies or local storage.
Sessions must have an expiry datetime, for pruning.
"""

from typing import NotRequired, Required, TypedDict

from campus.common.errors import api_errors
from campus.common.schema import CampusID
from campus.common.utils import (
    uid,
    utc_time,
)
import campus.common.validation.record as record_validation
from campus.models.base import BaseRecord
from campus.storage import (
    errors as storage_errors,
    get_collection
)

COLLECTION = "sessions"


class SessionRecord(BaseRecord):
    """Schema for a full session record."""
    expires_at: str
    scopes: NotRequired[list[str]]


class SessionNew(TypedDict, total=False):
    """Schema for a new session request."""
    expires_at: Required[str]
    # A session may include specific scopes
    scopes: list[str]


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
        else:
            return record

    def new(self, session_data: dict, *, expiry_seconds: int) -> dict:
        """Create a new OAuth session."""
        record_validation.validate_keys(
            session_data,
            valid_keys=SessionNew.__annotations__,
            ignore_extra=False,
        )
        session_data["id"] = uid.generate_category_uid(COLLECTION)
        dt_now = utc_time.now()
        session_data["created_at"] = utc_time.to_rfc3339(dt_now)
        session_data["expires_at"] = utc_time.to_rfc3339(
            utc_time.after(dt_now, seconds=expiry_seconds)
        )
        try:
            self.storage.insert_one(session_data)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return session_data

    def update(self, session_id: CampusID, **update) -> dict:
        """Update an existing session."""
        try:
            self.storage.update_by_id(session_id, update)
        except storage_errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                message="Session not found",
                session_id=session_id
            ) from e
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        else:
            return self.get(session_id)
