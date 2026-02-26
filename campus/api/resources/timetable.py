"""campus.api.resources.timetable

Timetable resource for Campus API.
"""

import typing
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage

timetable_storage = campus.storage.get_collection("timetables")

def _from_record(record: dict) -> campus.model.TimetableEntry:
    """Convert storage record to TimetableEntry model."""
    return campus.model.TimetableEntry(
        id=schema.CampusID(record["id"]),
        timetable_id=record["timetable_id"],
        lessongroup_id=record["lessongroup_id"],
        venuetimeslot_id=record["venuetimeslot_id"],
        created_at=schema.DateTime(record["created_at"])
    )

class TimetablesResource:
    """Represents the timetables resource."""
    
    @staticmethod
    def init_storage() -> None:
        """Initialize storage."""
        timetable_storage.init_collection()
    
    def __getitem__(self, timetable_id: schema.CampusID) -> "TimetableResource":
        return TimetableResource(timetable_id)
    
    def list(self, **filters: typing.Any) -> list[campus.model.TimetableEntry]:
        """List timetables matching filters."""
        try:
            records = timetable_storage.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]
    
    def new(self, **fields: typing.Any) -> campus.model.TimetableEntry:
        """Create new timetable."""

        timetable = campus.model.TimetableEntry(
            # id generation is handled by the dataclass default factory
            lessongroup_id = fields["lessongroup_id"],
            venuetimeslot_id = fields["venuetimeslot_id"],
            created_at=schema.DateTime.utcnow(),
            timetable_id=fields["timetable_id"]
        )

        try:
            timetable_storage.insert_one(timetable.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return timetable

class TimetableResource:
    """Represents a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id
    
    def get(self) -> campus.model.TimetableEntry:
        """Get the timetable."""
        try:
            record = timetable_storage.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            return _from_record(record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    
    def update(self, **updates: typing.Any) -> None:
        """Update the timetable record."""
        try:
            timetable_storage.update_by_id(self.timetable_id, updates)
        except campus.storage.errors.NoChangesAppliedError:
            return None
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def delete(self) -> None:
        """Delete the timetable."""
        try:
            record = timetable_storage.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            timetable_storage.delete_by_id(self.timetable_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e