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

timetable_lessongroup_table = campus.storage.get_collection("timetable_lessongroup")
timetable_lessongroupmembers_table = campus.storage.get_table("timetable_lessongroupmembers")

timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_collection = campus.storage.get_collection("timetables")


def _from_record(record: dict) -> campus.model.TimetableMetadata:
    return campus.model.TimetableMetadata(
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
        venue=schema.String(record["venue"]),
        weekday=schema.String(record["weekday"]),
        timeslot=schema.String(record["timeslot"]),
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
        timetable_collection.init_collection()
        # Use a metadata document to store current & next
        _upsert(
            timetable_collection,
            "@metadata",
            {
                "current": None,
                "next": None
            }
        )
        # Use this to update the metadata doc
        # timetable_collection.update_by_id("@metadata", {"current": ...})

    def __getitem__(self, timetable_id: schema.CampusID) -> "TimetableResource":
        return TimetableResource(timetable_id)

    def list(self, **filters: typing.Any) -> list[campus.model.TimetableMetadata]:
        """List timetables matching filters."""
        try:
            records = timetable_collection.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]
    
    def new(self, **fields: typing.Any) -> campus.model.TimetableMetadata:
        timetable = campus.model.TimetableMetadata(
            filename=fields["filename"],
            start_date=fields["start_date"],
            end_date=fields["end_date"],
        )
        groups: list[campus.model.LessonGroup] = []
        members = []
        entries = []
        
        for lessongroup in data.get("lessongroups", []):

            lgStorageData = timetable_lessongroup_collection.get_matching({
                "timetable_id": timetable.id,
                "label": lessongroup["label"]
            })
            if lgStorageData:
                lgStorageData = lgStorageData[0]
                
                lg = campus.model.LessonGroup.from_storage(lgStorageData)
            else:
                lg = campus.model.LessonGroup(
                    timetable_id=timetable.id,
                    lessongroup_id=entry_data["lessongroup_id"],
                    venue=schema.String(entry_data["venue"]),
                    weekday=schema.String(entry_data["weekday"]),
                    timeslot=schema.String(entry_data["timeslot"]),
                )
                lessongroups.append(lg)

              
            for ade_participant in lessongroup["members"]:
                member = campus.model.LessonGroupMember(
                    timetable_id=timetable_meta.id,
                    lessongroup_id=lg.id,
                    ade_participant=ade_participant
                )
                members.append(member)
            for entry_data in lessongroup["entries"]:
                entry = campus.model.TimetableEntry(
                    timetable_id=timetable_meta.id,
                    lessongroup_id=lg.id,
                    weekday = entry_data["weekday"],
                    timeslot = entry_data["timeslot"],
                    venue = entry_data["venue"],
                )
                entries.append(entry)

        timetable = campus.model.Timetable(
            id=timetable_meta.id,
            filename=timetable_meta.filename,
            start_date=timetable_meta.start_date,
            end_date=timetable_meta.end_date,
            entries=entries,
        )
        try:
            # TODO: Atomic transactions across multiple storage objects
            timetable_collection.insert_one(timetable_meta.to_storage())
            for entry in entries:
                timetable_entry_storage.insert_one(
                    entry.to_storage()
                )
            for lessongroup in groups:
                timetable_lessongroup_table.insert_one(
                    lessongroup.to_storage()
                )
            for member in members:
                timetable_lessongroupmembers_table.insert_one(
                    member.to_storage()
                )
        except campus.storage.errors.StorageError as e:
            # TODO: transaction rollback
            raise api_errors.InternalError.from_exception(e) from e
        return timetable

    def get(self, timetable_id: schema.CampusID) -> campus.model.Timetable:
        """Get a full timetable by ID."""
        return TimetableResource(timetable_id).get()

    def get_current(self) -> schema.CampusID | None:
        """Get the current active timetable. This is used to indicate which timetable is currently active."""
        try:
            metadata = timetable_collection.get_by_id("@metadata")
            record = metadata["current"]
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_current(self, timetable_id: schema.CampusID) -> None:
        """Set the current active timetable. This is used to indicate which timetable is currently active."""
        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_collection, "@metadata", {"current": timetable_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get_next(self) -> schema.CampusID | None:
        """Get the next timetable. This is used to indicate which timetable will be active after the current one expires."""
        try:
            metadata = timetable_collection.get_by_id("@metadata")
            record = metadata["next"]
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_next(self, timetable_id: schema.CampusID) -> None:
        """Set the next timetable. This is used to indicate which timetable will be active after the current one expires."""
        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_collection, "@metadata", {"next": timetable_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

class TimetableResource:
    """Represents a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id

    def get(self) -> campus.model.Timetable:
        """
        Get a full Timetable (metadata + entries) by ID.
        Assembles the Timetable model from the three storage collections:
          timetable_collection, timetable_entry_storage, timetable_lessongroup_collection.
        """
        try:
            record = timetable_collection.get_by_id(self.timetable_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        if record is None:
            raise api_errors.NotFoundError("Timetable not found", id=self.timetable_id)

        try:
            entry_records = timetable_entry_storage.get_matching({"timetable_id": self.timetable_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        entries = [_entry_from_record(r) for r in entry_records]

        return campus.model.Timetable(
            id=schema.CampusID(record["id"]),
            filename=record["filename"],
            start_date=schema.DateTime(record["start_date"]),
            end_date=schema.DateTime(record["end_date"]),
            entries=entries,
        )


    
    def update(self, **updates: typing.Any) -> None:
        """Update the timetable record."""
        try:
            timetable_collection.update_by_id(self.timetable_id, updates)
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
        """Delete the timetable and all associated entries, lessongroups and members."""
        try:
            record = timetable_collection.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            timetable_entry_storage.delete_matching({"timetable_id": self.timetable_id})
            timetable_collection.delete_by_id(self.timetable_id)
            timetable_lessongroup_table.delete_matching({"timetable_id": self.timetable_id})
            timetable_lessongroupmembers_table.delete_matching({"timetable_id": self.timetable_id})
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
    
    def get(self) -> campus.model.TimetableMetadata:
        """Get the timetable metadata without entries."""
        try:
            record = timetable_collection.get_by_id(self.timetable_id)
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
            timetable_collection.update_by_id(self.timetable_id, updates)
        except campus.storage.errors.NoChangesAppliedError:
            return None
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Timetable not found",
                id=self.timetable_id
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
