"""campus.api.resources.timetable

Timetable resource for Campus API.
"""

import typing
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
import campus.storage
from campus.storage.documents.interface import PK

timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_storage = campus.storage.get_collection("timetables")
timetable_table = campus.storage.get_table("timetables") 


def _from_record(record: dict) -> campus.model.Timetable:
    return campus.model.Timetable(
        id=schema.CampusID(record["id"]),
        filename=record["filename"],
        start_date=schema.DateTime(record["start_date"]),
        end_date=schema.DateTime(record["end_date"]),
    )

def _entry_from_record(record: dict) -> campus.model.TimetableEntry:
    return campus.model.TimetableEntry(
        id=schema.CampusID(record["id"]),
        timetable_id=schema.CampusID(record["timetable_id"]),
        lessongroup_id=schema.CampusID(record["lessongroup_id"]),
        venuetimeslot_id=schema.Integer(record["venuetimeslot_id"]),
    )


def _upsert(table, key: str, data: dict) -> None:
    try:
        table.update_by_id(key, data)
    except campus.storage.errors.NotFoundError:
        table.insert_one({PK: key, **data})

class TimetablesResource:
    """Represents the timetables resource."""
    
    @staticmethod
    def init_storage() -> None:
        """Initialize storage."""
        timetable_storage.init_collection()
    
    def __getitem__(self, timetable_id: schema.CampusID) -> "TimetableResource":
        return TimetableResource(timetable_id)
    
    def list(self, **filters: typing.Any) -> list[campus.model.Timetable]:
        """List timetables matching filters."""
        try:
            records = timetable_storage.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]
    
    def new(self, **fields: typing.Any) -> campus.model.Timetable:
        timetable = campus.model.Timetable(
            filename=fields["filename"],
            start_date=fields["start_date"],
            end_date=fields["end_date"],
        )
        try:
            timetable_storage.insert_one(timetable.to_storage())
            for entry_data in fields.get("entries", []):
                entry = campus.model.TimetableEntry(
                    timetable_id=timetable.id,
                    lessongroup_id=entry_data["lessongroup_id"],
                    venuetimeslot_id=entry_data["venuetimeslot_id"],
                )
                timetable_entry_storage.insert_one(entry.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return timetable

    def get_current(self) -> schema.CampusID | None:
        try:
            record = timetable_table.get_by_id("current_timetable")
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_current(self, timetable_id: schema.CampusID) -> None:
        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_table, "current_timetable", {"timetable_id": str(timetable_id)})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get_next(self) -> schema.CampusID | None:
        try:
            record = timetable_table.get_by_id("next_timetable")
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_next(self, timetable_id: schema.CampusID) -> None:
        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_table, "next_timetable", {"timetable_id": str(timetable_id)})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

class TimetableResource:
    """Represents a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id

    def get(self) -> campus.model.Timetable:
        """Get the timetable with entries."""
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
        try:
            record = timetable_storage.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            timetable_entry_storage.delete_matching({"timetable_id": self.timetable_id})
            timetable_storage.delete_by_id(self.timetable_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    @property
    def entries(self) -> "TimetableEntriesResource":
        return TimetableEntriesResource(self.timetable_id)

    @property
    def metadata(self) -> "TimetableMetadataResource":
        return TimetableMetadataResource(self.timetable_id)


class TimetableEntriesResource:
    """Represents the TimetableEntries Resource."""
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id

    def list(self) -> list[campus.model.TimetableEntry]:
        records = timetable_entry_storage.get_matching({
            "timetable_id": self.timetable_id
        })
        return [_entry_from_record(r) for r in records]

class TimetableMetadataResource:
    """Represents metadata for a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id
    
    def get(self) -> campus.model.Timetable:
        """Get the timetable metadata without entries."""
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
        """Update the timetable metadata."""
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
