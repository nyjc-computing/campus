"""campus.models.event

This module provides classes for managing Campus events.

Data structures:
- 

Main operations:
- CRUD
"""

from typing import Unpack, Any, Self, Type
from dataclasses import dataclass, asdict

from campus.common import schema
from campus.common.utils import uid
from campus.common.errors import api_errors
from campus.common.schema import CampusID
from campus.storage import get_table, errors as storage_errors
from campus.common import devops
from campus.models.base import BaseRecord

### Database-related code

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

# TODO: Implement description.

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
            location_url TEXT,
            duration INTEGER
        )
    """
    storage.init_table(schema)


class EventRecord(BaseRecord):
    """The event record stored in the events table."""
    name: str
    location: str
    location_url: str
    start_time: schema.DateTime  
    duration: int
    # Also has created_at & ID from BaseRecord.

### Request body schemas
@dataclass
class BaseRequest:
    """A dataclass with to_dict and from_dict, similar to a 
    BaseRecord."""
    @classmethod
    def from_dict(cls: Type[Self], data: dict) -> Self:
        """Create a record from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a dictionary."""
        return asdict(self)

@dataclass
class EventGet(BaseRequest):
    """Request body schema for a request with event info as parameters."""
    id: CampusID

@dataclass
class EventNew(BaseRequest):
    """Request body schema for a events.new operation."""
    name: str
    location: str
    location_url: str
    start_time: schema.DateTime   
    duration: int 

@dataclass
class EventDelete(BaseRequest):
    """Request body schema for a deletion request."""
    id: CampusID

@dataclass
class EventUpdate(BaseRequest):
    """Request body schema for a events.update operation."""
    id: CampusID
    name: str
    location: str
    location_url: str
    start_time: schema.DateTime    
    duration: int  

### Model classes.

class Event:
    """Event model for handling database operations related to events."""

    def __init__(self):
        """Initialize the User model with a table storage interface."""
        self.storage = get_table(TABLE)

    def new(self, fields: EventNew) -> EventRecord:
        """Create a new event."""
        event_id = CampusID(uid.generate_category_uid("event", length=16))

        # Least ugly solution due to type gymnastics.
        dtnow = schema.DateTime.utcnow()
        record = EventRecord.from_dict({
            "id": event_id,
            "created_at": dtnow,
            "name": fields.name,
            "location": fields.location,
            "location_url": fields.location_url,
            "duration": fields.duration,
            "start_time": fields.start_time
        })

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

    def _try_get(self, event_id: CampusID) -> EventRecord:
        """Private method.
        Tries to get event by event_id
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

    def delete(self, fields: EventDelete) -> None:
        """Delete an event by id."""
        self._try_get(fields.id)  # Make sure it exists.
        try:
            self.storage.delete_by_id(fields.id)
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, fields: EventGet) -> EventRecord:
        """Get an event by id."""
        return self._try_get(fields.id)

    def update(self, fields: EventUpdate) -> None:
        """Update an event by id."""
        # Check if user exists first

        self._try_get(fields.id)  # Make sure it exists.
        try:
            self.storage.update_by_id(fields.id, fields.to_dict())
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)
