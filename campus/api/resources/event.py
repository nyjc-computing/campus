"""campus.api.resources.event

Event resource for Campus API.
"""

from campus.common import schema
import campus.model
import campus.storage

event_storage = campus.storage.get_table("event")


# class Event:
#     """Event model for handling database operations related to events."""

#     def __init__(self):
#         """Initialize the User model with a table storage interface."""
#         self.storage = get_table(TABLE)

#     def new(
#             self,
#             *,
#             name: str,
#             location: str | None = None,
#             location_url: str | None = None,
#             start_time: schema.DateTime | None = None,
#             duration: int | None = None,
#             description: str,
#     ) -> EventRecord:
#         """Create a new event."""
#         event_id = CampusID(uid.generate_category_uid("event", length=16))

#         # Least ugly solution due to type gymnastics.
#         dtnow = schema.DateTime.utcnow()
#         record = EventRecord.from_dict({
#             "id": event_id,
#             "created_at": dtnow,
#             "name": fields.name,
#             "location": fields.location,
#             "location_url": fields.location_url,
#             "duration": fields.duration,
#             "start_time": fields.start_time
#         })

#         try:
#             self.storage.insert_one(record.to_dict())
#             return record
#         except storage_errors.ConflictError:
#             raise api_errors.ConflictError(
#                 message="Event with the same ID already exists",
#                 event_id=event_id
#             ) from None
#         except Exception as e:
#             raise api_errors.InternalError(message=str(e), error=e) from e

#     def _try_get(self, event_id: CampusID) -> EventRecord:
#         """Private method.
#         Tries to get event by event_id
#         Raises InternalError upon other errors."""
#         try:
#             event = self.storage.get_by_id(event_id)
#             if not event:
#                 raise api_errors.ConflictError(
#                     message="Event not found",
#                     event_id=event_id
#                 )
#             event = EventRecord(**event)  # Assert-coerce to EventResource.
#         except api_errors.ConflictError:
#             raise
#         except Exception as e:
#             raise api_errors.InternalError(message=str(e), error=e)

#         return event

#     def delete(self, id: CampusID, fields: EventDelete) -> None:
#         """Delete an event by id."""
#         self._try_get(id)  # Make sure it exists.
#         try:
#             self.storage.delete_by_id(id)
#         except Exception as e:
#             raise api_errors.InternalError(message=str(e), error=e)

#     def get(self, id: CampusID, fields: EventGet) -> EventRecord:
#         """Get an event by id."""
#         return self._try_get(id)

#     def update(self, id: CampusID, fields: EventUpdate) -> EventRecord:
#         """Update an event by id."""
#         # Check if user exists first

#         self._try_get(id)  # Make sure it exists.
#         try:
#             self.storage.update_by_id(id, fields.to_dict())
#             return self._try_get(id)
#         except Exception as e:
#             raise api_errors.InternalError(message=str(e), error=e)


class EventsResource:
    """Represents the events resource in Campus API Schema."""
    # campus.events.new()

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for client authentication."""
        event_storage.init_from_model("event", campus.model.Event)

    def __getitem__(self, event_id: schema.CampusID) -> "EventResource":
        """Get an Event resource by event ID."""
        return EventResource()

    def new(
            self,
            *,
            name: str,
            location: str | None = None,
            location_url: str | None = None,
            start_time: schema.DateTime | None = None,
            duration: int | None = None,
            description: str,
    ) -> campus.model.Event:
        """Create a new event and return the Event model instance."""
        client = campus.model.Event(
            name=name,
            location=location,
            location_url=location_url,
            start_time=start_time,
            duration=duration,
            description=description,
        )
        event_storage.insert_one(client.to_storage())
        return client



class EventResource:
    """Represents a single event resource in Campus API Schema."""
    # campus.events[event_id].get()
    # campus.events[event_id].update()
    # campus.events[event_id].delete()
