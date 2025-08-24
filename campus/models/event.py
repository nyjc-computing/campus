"""campus.models.event

This module provides classes for managing Campus events.

Data structures:
- 

Main operations:
- CRUD
"""

from typing import NotRequired, TypedDict, Unpack

from campus.common.utils import uid, utc_time
from campus.common.errors import api_errors
from campus.common.schema import CampusID
from campus.storage import get_table
from campus.common import devops
from campus.models.base import BaseRecord

# Create a new EventID with CampusID(uid.generate_category_uid("event", length=8))
EventID = CampusID

### Database-related code

"""
Database schema:
id: TEXT - EventID, is the primary key
name: TEXT - name of the event
venue: TEXT - venue of the event
time: TIMESTAMPTZ - rfc3339 time
length: INTEGER - length of event in seconds

created_at: TIMESTAMPTZ - from BaseRecord
"""

# TODO: Implement some venue validation through some master list?

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
            id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            venue TEXT NOT NULL,
            time TIMESTAMPTZ NOT NULL,
            length INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
    """
    storage.init_table(schema)

class EventRecord(BaseRecord, total = True):
    """The event record stored in the events table."""
    id: EventID
    name: str
    venue: str
    time: utc_time.datetime
    length: int # time in seconds
    # Also has created_at from BaseRecord.

### Request body schemas

# In requests that modify events (new, update), allow str | utc_time.datetime for time.
# Everywhere else, it is ONLY utc_time.datetime.

class RequestEventInfo(TypedDict):
    """Request body schema for a request with event info as parameters."""
    name: str
    venue: str
    time: str | utc_time.datetime # rfc3339 time if str
    length: int # time in seconds

class EventNew(RequestEventInfo, total=True): 
    """Request body schema for a events.new operation."""
    pass

# total = False as all params are optional.
class EventUpdate(RequestEventInfo, total=False):
    """Request body schema for a events.update operation."""
    pass

# events.delete and events.get do not need a request body schema as it takes no params.

def coerce_time_datetime(time: str | utc_time.datetime) -> utc_time.datetime:
    """Coerces time from str | utc_time.datetime to utc_time.datetime"""
    if isinstance(time, utc_time.datetime):
        return time
    else:
        return utc_time.from_rfc3339(time)

### Response body schemas

# Response body schema representing the result of a events.get, events.update and events.new operation.
EventResource = EventRecord

### Model classes.

class Event:
    """Event model for handling database operations related to events."""

    def __init__(self):
        """Initialize the User model with a table storage interface."""
        self.storage = get_table(TABLE)
    
    def new(self, **fields: Unpack[EventNew]) -> EventResource:
        """Create a new event."""
        event_id = EventID(uid.generate_category_uid("event", length=8))

        # Least ugly solution due to type gymnastics.
        record = EventRecord(
            id=event_id,
            created_at=utc_time.now(),
            name=fields["name"],
            venue=fields["venue"],
            length=fields["length"],
            time=coerce_time_datetime(fields["time"])
        )

        try:
            self.storage.insert_one(dict(record))
            return EventResource(**record)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
    
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
            event = EventRecord(**event) # Assert-coerce to EventResource.
        except api_errors.ConflictError:
            raise
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
        
        return event
    
    def delete(self, event_id: EventID) -> None:
        """Delete an event by id."""
        self._try_get(event_id) # Make sure it exists.
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

        if "time" in updates:
            updates["time"] = coerce_time_datetime(updates["time"])

        self._try_get(event_id) # Make sure it exists.
        try:
            self.storage.update_by_id(event_id, dict(updates))
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)