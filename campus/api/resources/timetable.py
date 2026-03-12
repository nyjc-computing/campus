"""campus.api.resources.timetable

Timetable resource for Campus API.
"""

import typing
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model
from campus.model import timetable
import campus.storage
from campus.storage.documents.interface import PK

timetable_lessongroup_collection = campus.storage.get_collection("timetable_lessongroup")
timetable_lessongroupmembers_table = campus.storage.get_table("timetable_lessongroupmembers")
timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_collection = campus.storage.get_collection("timetables")
timetable_table = campus.storage.get_table("timetables") 

def _from_record(record: dict) -> campus.model.TimetableMetadata:
    """Convert a storage record into a TimetableMetadata model.

    Args:
        record (dict): Raw timetable metadata record from storage.

    Returns:
        campus.model.TimetableMetadata: Parsed timetable metadata object.
    """
    return campus.model.TimetableMetadata(
        id=schema.CampusID(record["id"]),
        filename=record["filename"],
        start_date=schema.DateTime(record["start_date"]),
        end_date=schema.DateTime(record["end_date"]),
    )

def _entry_from_record(record: dict) -> campus.model.TimetableEntry:
    """Convert a storage record into a TimetableEntry model.

    Args:
        record (dict): Raw timetable entry record from storage.

    Returns:
        campus.model.TimetableEntry: Parsed timetable entry object.
    """
    return campus.model.TimetableEntry(
        id=schema.CampusID(record["id"]),
        timetable_id=schema.CampusID(record["timetable_id"]),
        lessongroup_id=schema.CampusID(record["lessongroup_id"]),
        venue=schema.String(record["venue"]),
        weekday=schema.String(record["weekday"]),
        timeslot=schema.String(record["timeslot"]),
    )


def _upsert(table, key: str, data: dict) -> None:
    """Insert or update a record in a table.

    Attempts to update a record by its key. If the record does not exist,
    it inserts a new record with the provided key and data.

    Args:
        table: Storage table object.
        key (str): Primary key for the record.
        data (dict): Data fields to update or insert.
    """
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
    
    def __getitem__(self, timetable_id: schema.CampusID) -> "TimetableResource":
        """Return a resource object for a specific timetable.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.

        Returns:
            TimetableResource: Resource representing the timetable.
        """
        return TimetableResource(timetable_id)
    
    def list(self, **filters: typing.Any) -> list[campus.model.TimetableMetadata]:
        """List timetables matching the provided filters.

        Args:
            **filters: Arbitrary filter parameters applied to the storage query.

        Returns:
            list[campus.model.TimetableMetadata]: Matching timetable metadata objects.
        """
        try:
            records = timetable_collection.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [_from_record(record) for record in records]
    
    def new(self, **fields: typing.Any) -> campus.model.TimetableMetadata:
        """Create a new timetable and optionally its entries.

        Args:
            **fields: Timetable fields including filename, start_date,
                      end_date, and optionally entries.

        Returns:
            campus.model.TimetableMetadata: The created timetable metadata.
        """
        timetable = campus.model.TimetableMetadata(
            filename=fields["filename"],
            start_date=fields["start_date"],
            end_date=fields["end_date"],
        )

        data = fields.get("data", {})

        lessongroups = []
        members = []
        entry_list = []
        entry_list_to_insert = []
        
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
                memberStorageData = timetable_lessongroupmembers_table.get_matching({
                    "timetable_id": timetable.id,
                    "lessongroup_id": lg.id,
                    "ade_participant": ade_participant
                })
                if memberStorageData:
                    memberStorageData = memberStorageData[0]
                    member = campus.model.LessonGroupMember.from_storage(memberStorageData)
                else:
                    member = campus.model.LessonGroupMember(
                        timetable_id=timetable.id,
                        lessongroup_id=lg.id,
                        ade_participant=ade_participant
                    )
                    members.append(member)
            
            for entry_data in lessongroup.get("entries", []):
                entryStorageData = timetable_entry_storage.get_matching({
                    "timetable_id": timetable.id,
                    "lessongroup_id": lg.id,
                    "weekday": entry_data["weekday"],
                    "timeslot": entry_data["timeslot"],
                    "venue": entry_data["venue"]
                })
                if entryStorageData:
                    entryStorageData = entryStorageData[0]
                    entry = campus.model.TimetableEntry.from_storage(entryStorageData)
                else:
                    entry = campus.model.TimetableEntry(
                        timetable_id=timetable.id,
                        lessongroup_id=lg.id,
                        weekday = entry_data["weekday"],
                        timeslot = entry_data["timeslot"],
                        venue = entry_data["venue"],
                    )
                    entry_list_to_insert.append(entry)
                entry_list.append(entry)
        
        timetable.entries = entry_list

        try:
            timetable_collection.insert_one(timetable.to_storage())
            for entry in entry_list_to_insert:
                timetable_entry_storage.insert_one(entry.to_storage())
            for lessongroup in lessongroups:
                timetable_lessongroup_collection.insert_one(lessongroup.to_storage())
            for member in members:
                timetable_lessongroupmembers_table.insert_one(member.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
    
        return timetable

    def get_current(self) -> schema.CampusID | None:
        """Retrieve the current active timetable ID.

        Returns:
            schema.CampusID | None: The current timetable ID, or None if not set.
        """
        try:
            record = timetable_table.get_by_id("current_timetable")
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_current(self, timetable_id: schema.CampusID) -> None:
        """Set the current active timetable.

        Args:
            timetable_id (schema.CampusID): ID of the timetable to set as current.
        """

        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_table, "current_timetable", {"timetable_id": str(timetable_id)})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get_next(self) -> schema.CampusID | None:
        """Retrieve the next scheduled timetable ID.

        Returns:
            schema.CampusID | None: The next timetable ID, or None if not set.
        """
        try:
            record = timetable_table.get_by_id("next_timetable")
            return schema.CampusID(record["timetable_id"]) if record else None
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def set_next(self, timetable_id: schema.CampusID) -> None:
        """Set the next scheduled timetable.

        Args:
            timetable_id (schema.CampusID): ID of the timetable to set as next.
        """
        TimetableResource(timetable_id).get()
        try:
            _upsert(timetable_table, "next_timetable", {"timetable_id": str(timetable_id)})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

class TimetableResource:
    """Represents a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id

    def get(self) -> campus.model.TimetableMetadata:
        """Retrieve the timetable metadata.

        Returns:
            campus.model.TimetableMetadata: The timetable metadata.

        Raises:
            ConflictError: If the timetable does not exist.
        """
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
        """Update fields of the timetable.

        Args:
            **updates: Fields to update in the timetable record.
        """
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
        """Delete the timetable and all associated entries.

        Raises:
            ConflictError: If the timetable does not exist.
        """
        try:
            record = timetable_collection.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            timetable_entry_storage.delete_matching({"timetable_id": self.timetable_id})
            timetable_collection.delete_by_id(self.timetable_id)
            timetable_lessongroup_collection.delete_matching({"timetable_id": self.timetable_id})
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
        """Access the timetable entries resource."""
        return TimetableEntriesResource(self.timetable_id)

    @property
    def metadata(self) -> "TimetableMetadataResource":
        """Access the timetable metadata resource."""
        return TimetableMetadataResource(self.timetable_id)


class TimetableEntriesResource:
    """Represents the TimetableEntries Resource."""
    def __init__(self, timetable_id: schema.CampusID):
        """Initialize with the parent timetable ID.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.
        """
        self.timetable_id = timetable_id

    def list(self) -> list[campus.model.TimetableEntry]:
        """List all entries belonging to the timetable.

        Returns:
            list[campus.model.TimetableEntry]: Timetable entries.
        """
        records = timetable_entry_storage.get_matching({
            "timetable_id": self.timetable_id
        })
        return [_entry_from_record(r) for r in records]

class TimetableMetadataResource:
    """Represents metadata for a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        """Initialize with the timetable ID.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.
        """
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
        """Update timetable metadata fields.

        Args:
            **updates: Metadata fields to update.
        """
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

