"""campus.models.event

This module provides classes for managing Campus events.

Data structures:
- 

Main operations:
- CRUD
"""

from typing import TypedDict, Unpack

from campus.common import schema
from campus.common.utils import uid
from campus.common.errors import api_errors
# from campus.common.schema import CampusID
from campus.storage import get_table, errors as storage_errors
from campus.common import devops
from campus.models.base import BaseRecord

# Create a new EventID with CampusID(uid.generate_category_uid("event", length=8))
EventID = schema.CampusID

# Database-related code

"""
Database schema:
id: TEXT - EventID, is the primary key
created_at: TEXT - from BaseRecord
name: TEXT - name of the event
description: TEXT  longer description or details of event
location: TEXT - location of the event
location_url: TEXT - URL for the location of the event
start_time: TEXT - time that event starts.
duration: INTEGER - duration of event in seconds
"""

# TODO: Implement some location validation through some master list?

TABLE = "events"


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    storage = get_table(TABLE)
    schema = f"""
        CREATE TABLE IF NOT EXISTS "{TABLE}" (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            name TEXT,
            location TEXT,
            start_time TEXT,
            duration INTEGER
        )
    """
    storage.init_table(schema)



# TODO: Update to dataclass (https://docs.python.org/3.11/library/dataclasses.html)
class EventRecord(BaseRecord):
    """The event record stored in the events table."""
    id: EventID
    name: str
    location: str
    location_url: str
    start_time: str  # rfc3339 string
    duration: int  # time in minutes
    # Also has created_at from BaseRecord.

# Request body schemas


class RequestEventInfo(TypedDict):
    """Request body schema for a request with event info as parameters."""
    name: str
    location: str
    location_url: str
    start_time: str  # rfc3339 string
    duration: int  # time in minutes


class EventNew(RequestEventInfo, total=True):
    """Request body schema for a events.new operation."""
    pass

# total = False as all params are optional.


class EventUpdate(RequestEventInfo, total=False):
    """Request body schema for a events.update operation."""
    pass

# events.delete and events.get do not need a request body schema as it takes no params.

# Response body schemas


# Response body schema representing the result of a events.get, events.update and events.new operation.
EventResource = EventRecord

# Model classes.


class Event:
    """Event model for handling database operations related to events."""

    def __init__(self):
        """Initialize the User model with a table storage interface."""
        self.storage = get_table(TABLE)

    def new(self, **fields: Unpack[EventNew]) -> EventRecord:
        """Create a new event."""
        event_id = EventID(uid.generate_category_uid("event", length=16))

        # Least ugly solution due to type gymnastics.
        dtnow = schema.DateTime.utcnow()
        record = EventRecord(
            id=event_id,
            created_at=dtnow,
            name=fields["name"],
            location=fields["location"],
            location_url=fields["location_url"],
            duration=fields["duration"],
            start_time=schema.DateTime(fields["start_time"])
        )

        try:
            self.storage.insert_one(record.to_dict())
            return record
        except storage_errors.ConflictError:
            raise api_errors.ConflictError(
                message="Event with the same ID already exists",
                event_id=event_id
            ) from None
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e) from e

    def _try_get(self, event_id: EventID) -> EventRecord:
        """Tries to get event by event_id
        Raises InternalError upon other errors."""
        try:
            event = self.storage.get_by_id(event_id)
            if not event:
                raise api_errors.ConflictError(
                    message="Event not found",
                    event_id=event_id
                )
            event = EventRecord(**event)  # Assert-coerce to EventResource.
        except api_errors.ConflictError:
            raise
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

        return event

    def delete(self, event_id: EventID) -> None:
        """Delete an event by id."""
        self._try_get(event_id)  # Make sure it exists.
        try:
            self.storage.delete_by_id(event_id)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, event_id: EventID) -> EventResource:
        """Get an event by id."""
        return self._try_get(event_id)

    def update(self, event_id: EventID, **updates: Unpack[EventUpdate]) -> None:
        """Update an event by id."""
        # Check if user exists first

        self._try_get(event_id)  # Make sure it exists.
        try:
            self.storage.update_by_id(event_id, dict(updates))
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
