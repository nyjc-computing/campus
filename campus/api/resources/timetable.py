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

timetable_lessongroup_table = campus.storage.get_collection("timetable_lessongroup")
timetable_lessongroupmembers_table = campus.storage.get_table("timetable_lessongroupmembers")

timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_collection = campus.storage.get_collection("timetables")


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
        weekday = schema.String(record["weekday"]),
        timeslot = schema.String(record["timeslot"]),
        venue = schema.String(record["venue"]),
    )

def _lessongroup_from_record(record: dict) -> campus.model.LessonGroup:
    return campus.model.LessonGroup(
        timetable_id=schema.CampusID(record["timetable_id"]),
        label = schema.String(record["label"])
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
    
    def new(
            self,
            metadata: dict[str, typing.Any],
            lessongroups: typing.List[dict[str, typing.Any]],
    ) -> campus.model.Timetable:
        """Create a new timetable with metadata and entries.

        `lessongroups` is a list of dicts following the schema:
        - label [str]
        - members list[str]
        - entries list[dict]

        Each entry has:
        - venue Optional[str]
        - weekday [str]
        - timeslot [str]
        """
        timetable_meta = campus.model.TimetableMetadata(
            filename=metadata["filename"],
            start_date=metadata["start"],
            end_date=metadata["end"],
        )
        groups: list[campus.model.LessonGroup] = []
        members = []
        entries = []
        
        for lessongroup in lessongroups:
            lg = campus.model.LessonGroup(
                timetable_id=timetable_meta.id,
                label = lessongroup["label"]
            )
            groups.append(lg)
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
        """Retrieve the current active timetable ID.

        Returns:
            schema.CampusID | None: The current timetable ID, or None if not set.
        """
        try:
            metadata = timetable_collection.get_by_id("@metadata")
            record = metadata["current"]
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
            _upsert(timetable_collection, "@metadata", {"current": timetable_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get_next(self) -> schema.CampusID | None:
        """Retrieve the next scheduled timetable ID.

        Returns:
            schema.CampusID | None: The next timetable ID, or None if not set.
        """
        try:
            metadata = timetable_collection.get_by_id("@metadata")
            record = metadata["next"]
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

        Returns:
            campus.model.TimetableMetadata: The timetable metadata.

        Raises:
            ConflictError: If the timetable does not exist.
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

