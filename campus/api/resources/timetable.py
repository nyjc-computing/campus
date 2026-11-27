"""campus.api.resources.timetable

Timetable resource for Campus API.

Lessongroup identity is label-anchored across allocations (#592,
campus#1080): when a new timetable is created, a group whose label
already has a row — from any earlier allocation — reuses that row's id
and the row's `timetable_id` moves to the new allocation
(update-in-place; the collection is PK'd on id). References keyed by
group id, i.e. subjcombi mappings, therefore survive version switches.
A label claimed by two or more rows is historical drift and fails the
create with a 409; labels absent from the new allocation are left
untouched.

The active (current/next) timetable "pointers" are derived, not stored
(#1222): current is the version whose validity window covers today
(Asia/Singapore dates — latest start_date wins overlapping windows),
next is the wholly-future version with the earliest start_date. There
is no pointer document to keep in sync: changing what runs means
editing a version's window (PATCH /timetable/{id}/metadata). A
deployment with no covering window serves current: null. The retired
effective-dated trail (#1075) and legacy @metadata documents are never
read or written; lingering rows are inert history.
"""

import contextlib
import datetime
import typing

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import ValidationError, api_errors
from campus.common.utils import uid, utc_time
from campus.storage.documents.interface import PK

from . import files as files_resource

timetable_lessongroup_collection = campus.storage.get_collection("timetable_lessongroup")
timetable_lessongroupmembers_table = campus.storage.get_table("timetable_lessongroupmembers")

timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_collection = campus.storage.get_collection("timetables")

# Timetable attachments are files in the campus files backend under
# this slug namespace: timetables/<timetable_id>/attachments/<uid>.
# Storing attachments as file records (name = the committee's original
# filename, content bytes in the files bucket) reuses the files
# backend's content plumbing; the namespace is what binds a record to
# its version. The generic files routes refuse writes under this
# namespace to non-timetable-admins (same gate as the timetable
# mutation routes), so the binding cannot be forged through the files
# surface. Reads stay authentication-only, like other timetable reads.
ATTACHMENT_SLUG_NAMESPACE = "timetables/"


def attachment_slug_prefix(timetable_id: schema.CampusID) -> str:
    """The files-backend slug prefix holding this version's attachments."""
    return f"{ATTACHMENT_SLUG_NAMESPACE}{timetable_id}/attachments/"

# School time is Singapore time (UTC+8, no DST). Validity-window
# derivation and effective-dated subjcombi records both compare school
# dates: date-only values mean 07:00 school time — the committee's
# default switch-over hour, before the first period. (parse_effective_from
# is shared with the subjcombi resource, which re-exports it.)
SGT = datetime.timezone(datetime.timedelta(hours=8), name="SGT")


def parse_effective_from(raw: str | None) -> datetime.datetime:
    """Parse an effective_from request value into an aware UTC datetime.

    - absent/None: now (immediate change);
    - date-only (`YYYY-MM-DD`): 07:00 school time (SGT) on that date;
    - ISO datetime: as given, naive values interpreted as school time.
    """
    if raw is None:
        return utc_time.now()
    text = raw.strip()
    try:
        if len(text) == 10:
            day = datetime.date.fromisoformat(text)
            dt = datetime.datetime(day.year, day.month, day.day, 7, 0, tzinfo=SGT)
        else:
            dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SGT)
    except ValueError as e:
        raise api_errors.InvalidRequestError(
            f"Invalid effective_from {raw!r}: use ISO datetime or "
            "YYYY-MM-DD (applies 07:00 school time)",
        ) from e
    return dt.astimezone(datetime.timezone.utc)


def _get_lessongroup_labels(
        timetable_id: schema.CampusID
) -> dict[schema.CampusID, schema.String]:
    """Get a mapping of lesson group IDs to labels for one timetable."""
    records = timetable_lessongroup_collection.get_matching(
        {"timetable_id": timetable_id}
    )
    return {
        schema.CampusID(record["id"]): schema.String(record["label"])
        for record in records
    }

def _lessongroup_for_label(
        label: schema.String,
        timetable_id: schema.CampusID,
) -> tuple[model.LessonGroup, bool]:
    """The lessongroup row owning `label`, or a freshly minted one.

    Label-anchored reuse (#592, campus#1080): the label is the group's
    identity anchor within a cohort year, so an allocation carrying a
    known label is the same group — its id is reused and the caller
    moves the row's timetable_id to the new allocation. Two or more
    rows sharing a label is historical drift; refuse with a 409 naming
    the rows rather than silently picking one. Returns (group, reused).
    """
    try:
        matches = timetable_lessongroup_collection.get_matching(
            {"label": label}
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    if len(matches) > 1:
        raise api_errors.ConflictError(
            f"Multiple lessongroups share the label {label!r} "
            f"({sorted(m['id'] for m in matches)}); delete the superseded "
            "versions that own the duplicate-label rows "
            "(DELETE /timetable/<id>/) and retry the timetable create"
        )
    if matches:
        return (
            model.LessonGroup(
                id=schema.CampusID(matches[0]["id"]),
                timetable_id=timetable_id,
                label=label,
            ),
            True,
        )
    return (
        model.LessonGroup(timetable_id=timetable_id, label=label),
        False,
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


def _version_windows() -> list[tuple[model.TimetableMetadata, datetime.datetime | None]]:
    """Every timetable version as (metadata, created_at), leniently.

    Rows whose metadata does not parse (a legacy pointer document, a
    manual write missing a window) are skipped rather than failing the
    whole pointer state: a version without a usable window can be
    neither current nor next by definition (#1222).
    """
    try:
        records = timetable_collection.get_matching({})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    versions: list[tuple[model.TimetableMetadata, datetime.datetime | None]] = []
    for record in records:
        if str(record.get("id", "")).startswith("@"):
            continue  # retired legacy @metadata pointer documents (#1075)
        try:
            meta = model.TimetableMetadata.from_storage(record)
        except (KeyError, TypeError, ValueError, ValidationError):
            continue
        created_at = record.get("created_at")
        versions.append((
            meta,
            utc_time.from_rfc3339(created_at) if created_at else None,
        ))
    return versions


def _sgt_date(dt: datetime.datetime) -> datetime.date:
    """An instant as a school (Singapore) calendar date."""
    return dt.astimezone(SGT).date()


def _covers_today(meta: model.TimetableMetadata, at_date: datetime.date) -> bool:
    """Whether the version's validity window covers a school date.

    Dates are inclusive on both ends (the model's field contract:
    end_date is 00:00 on the last day the timetable is effective); a
    reversed window can never cover.
    """
    start = _sgt_date(meta.start_date.to_datetime())
    end = _sgt_date(meta.end_date.to_datetime())
    return start <= at_date <= end


class TimetablesResource:
    """Represents the timetables resource."""
    
    @staticmethod
    def init_storage() -> None:
        """Initialize storage."""
        timetable_lessongroupmembers_table.init_from_model(
            "timetable_lessongroupmembers",
            model.LessonGroupMember
        )
        timetable_lessongroup_collection.init_collection()
        timetable_entry_storage.init_collection()
        timetable_collection.init_collection()

    def __getitem__(self, timetable_id: schema.CampusID) -> "TimetableResource":
        """Return a resource object for a specific timetable.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.

        Returns:
            TimetableResource: Resource representing the timetable.
        """
        return TimetableResource(timetable_id)

    def list_members(self, timetable_id: schema.CampusID) -> list[dict]:
        """The version's lesson-group roster, one row per member.

        The file-derived timetable_lessongroupmembers rows, projected
        to (lessongroup_id, ade_participant): ade_participant carries
        the XML participant id verbatim (teacher entity names in this
        year's exports; campus ids once import-time resolution lands —
        ttv2#174). Browse consumers (Search Time Tables, ttv2#175
        stopgap) key groups by these values verbatim.
        """
        try:
            rows = timetable_lessongroupmembers_table.get_matching(
                {"timetable_id": timetable_id}
            )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return [
            {
                "lessongroup_id": schema.CampusID(row["lessongroup_id"]),
                "ade_participant": schema.String(row["ade_participant"]),
            }
            for row in rows
        ]

    def list(self, **filters: typing.Any) -> list[model.TimetableMetadata]:
        """List timetables matching the provided filters.

        Args:
            **filters: Arbitrary filter parameters applied to the storage query.

        Returns:
            list[model.TimetableMetadata]: Matching timetable metadata objects.
        """
        # Defensive: the retired legacy @metadata pointer document
        # (#1075) may linger in deployments whose storage was bootstrapped
        # before #1222 — never a version row.
        filters["id"] = campus.storage.query.ne("@metadata")
        try:
            records = timetable_collection.get_matching(filters)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        timetables: list[model.TimetableMetadata] = []
        for record in records:
            try:
                timetables.append(model.TimetableMetadata.from_storage(record))
            except KeyError as e:
                raise api_errors.InternalError(
                    e.args[0],
                    record=record
                ) from e
        return timetables
    
    def new(
            self,
            metadata: dict[str, typing.Any],
            lessongroups: typing.List[dict[str, typing.Any]],
    ) -> model.Timetable:
        """Create a new timetable with metadata and labeled entries.

        Groups are reused by label across allocations (#592): a label
        that already has a lessongroup row keeps its id, and the row's
        timetable_id moves to the new allocation — subjcombi mappings
        keyed by lessongroup_id survive the version switch. Labels
        absent from the new allocation are untouched. A label repeated
        within the payload is rejected with a 400 (one label anchors
        one group); a label already claimed by two rows is historical
        drift and fails with a 409.

        `lessongroups` is a list of dicts following the schema:
        - label [str]
        - members list[str]
        - entries list[dict]

        Each entry has:
        - venue Optional[str]
        - weekday [str]
        - timeslot [str]
        """
        timetable_meta = model.TimetableMetadata(**metadata)
        groups: list[model.LessonGroup] = []
        reused_group_ids: list[schema.CampusID] = []
        members = []
        entries = []

        for lessongroup in lessongroups:
            # HACK: hardcoded key validation
            # TODO: create a model or TypedDict for validation
            missing_keys = []
            for key in ("label", "members", "entries"):
                if key not in lessongroup:
                    missing_keys.append(key)
            if missing_keys:
                raise api_errors.InvalidRequestError(
                    "'lessongroup' object requires missing properties: "
                    f"{', '.join(missing_keys)}"
                )
        labels = [lessongroup["label"] for lessongroup in lessongroups]
        duplicate_labels = sorted({
            label for label in labels if labels.count(label) > 1
        })
        if duplicate_labels:
            raise api_errors.InvalidRequestError(
                "Duplicate lessongroup labels in the create payload "
                "(a label anchors one group): "
                f"{', '.join(repr(label) for label in duplicate_labels)}"
            )

        for lessongroup in lessongroups:
            lg, reused = _lessongroup_for_label(
                label=lessongroup["label"],
                timetable_id=timetable_meta.id,
            )
            if reused:
                reused_group_ids.append(lg.id)
            else:
                groups.append(lg)
            for ade_participant in lessongroup["members"]:
                member = model.LessonGroupMember(
                    timetable_id=timetable_meta.id,
                    lessongroup_id=lg.id,
                    ade_participant=ade_participant
                )
                members.append(member)
            for entry_data in lessongroup["entries"]:
                entry = model.TimetableEntry(
                    timetable_id=timetable_meta.id,
                    lessongroup_id=lg.id,
                    weekday = entry_data["weekday"],
                    timeslot = entry_data["timeslot"],
                    venue = entry_data["venue"],
                    label = lessongroup["label"],
                )
                entries.append(entry)

        timetable = model.Timetable(
            id=timetable_meta.id,
            created_at=timetable_meta.created_at,
            filename=timetable_meta.filename,
            label=timetable_meta.label,
            start_date=timetable_meta.start_date,
            end_date=timetable_meta.end_date,
            entries=entries,
        )
        try:
            # TODO: Atomic transactions across multiple storage objects
            timetable_collection.insert_one(timetable_meta.to_storage())
            # Label-anchored reuse: move each reused row to the new
            # allocation in place — the collection is PK'd on id, so
            # never insert a second row for the same group.
            for lg_id in reused_group_ids:
                with contextlib.suppress(
                    campus.storage.errors.NoChangesAppliedError
                ):
                    timetable_lessongroup_collection.update_by_id(
                        str(lg_id),
                        {"timetable_id": str(timetable_meta.id)},
                    )  # no-op when the row is already owned here
            # Bulk inserts (#576): a full timetable has too many entries,
            # groups and members for per-row inserts, which time out on
            # the development deployment.
            error_details: dict[str, str] = {}
            for name, storage, records in (
                ("entries", timetable_entry_storage, entries),
                ("lessongroups", timetable_lessongroup_collection, groups),
                ("members", timetable_lessongroupmembers_table, members),
            ):
                for i, e in storage.insert_many(
                    [record.to_storage() for record in records]
                ).items():
                    error_details[f"{name}[{i}]"] = str(e)
            if error_details:
                raise campus.storage.errors.StorageError(
                    "Some timetable records failed to insert",
                    details=error_details
                )
        except campus.storage.errors.StorageError as e:
            # TODO: transaction rollback
            raise api_errors.InternalError.from_exception(e) from e

        return timetable

    def delete(self, timetable_id: schema.CampusID) -> None:
        """Delete a timetable version and all of its rows (#1088).

        Cascades the version's entries, group members and lessongroup
        rows (all keyed on timetable_id), then the version row itself.
        This is the cleanup surface the label-drift 409 points at: a
        stale duplicate-label row is owned by the superseded version
        that minted it, so deleting that version removes the row and
        unblocks the create. A label-anchored row that a later create
        reused is owned by the *later* version (update-in-place), so
        deleting the older version never strips a live group.

        Refuses to delete the version the derived current or next
        pointer names (#1222) — adjust the validity windows first.
        Historical versions are fair game.

        Raises:
            NotFoundError: unknown timetable_id.
            ConflictError: the version is the current or next target.
        """
        try:
            record = timetable_collection.get_by_id(str(timetable_id))
        except campus.storage.errors.NotFoundError:
            record = None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if record is None:
            raise api_errors.NotFoundError(
                "Timetable not found",
                timetable_id=str(timetable_id),
            )

        current = self.get_current()
        if current is not None and str(current) == str(timetable_id):
            raise api_errors.ConflictError(
                "Refusing to delete the timetable the current pointer "
                f"names ({timetable_id}); adjust the validity windows first"
            )
        scheduled_next = self.get_next()
        if (
            scheduled_next is not None
            and str(scheduled_next["timetable_id"]) == str(timetable_id)
        ):
            raise api_errors.ConflictError(
                "Refusing to delete the timetable scheduled as next "
                f"({timetable_id}); adjust the validity windows first"
            )

        # TODO: Atomic transactions across multiple storage objects —
        # same caveat as new(): a mid-cascade failure leaves a partial
        # delete, which is safe for a cleanup path (the version row is
        # deleted last, so a retry is expressible).
        try:
            # Empty row families are normal (a version with no entries, no
            # members, or no groups of its own); the postgres backend raises
            # NoChangesAppliedError on a zero-match delete, so suppress it
            # per family (same convention as new()'s update-in-place).
            for storage in (
                timetable_entry_storage,
                timetable_lessongroupmembers_table,
                timetable_lessongroup_collection,
            ):
                with contextlib.suppress(
                    campus.storage.errors.NoChangesAppliedError
                ):
                    storage.delete_matching({"timetable_id": str(timetable_id)})
            # Attachment files are children too: they go before the
            # version row, keeping the delete retryable on failure.
            TimetableAttachmentsResource(timetable_id).delete_all()
            timetable_collection.delete_by_id(str(timetable_id))
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

    def get(self, timetable_id: schema.CampusID) -> model.Timetable:
        """Get a full timetable by ID."""
        return TimetableResource(timetable_id).get()

    def get_current(
            self,
            at: datetime.datetime | None = None,
    ) -> schema.CampusID | None:
        """Retrieve the current active timetable ID at `at` (default now).

        Derived from the validity windows (#1222): the covering
        version's window includes `at` as a school (Singapore) date;
        when several windows overlap, the latest start_date wins, with
        created_at breaking exact ties. No covering version — including
        a deployment whose every window is wholly past — serves None.

        Returns:
            schema.CampusID | None: The current timetable ID, or None if not set.
        """
        at_dt = at or utc_time.now()
        at_date = _sgt_date(at_dt)
        covering = [
            (meta, created_at)
            for meta, created_at in _version_windows()
            if _covers_today(meta, at_date)
        ]
        if not covering:
            return None
        # Latest start_date wins; created_at (None sorts oldest) breaks
        # exact-start ties deterministically.
        meta, _ = max(
            covering,
            key=lambda pair: (
                _sgt_date(pair[0].start_date.to_datetime()),
                pair[1] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
            ),
        )
        return schema.CampusID(meta.id)

    def get_next(self) -> dict | None:
        """Retrieve the next scheduled timetable and its effective date.

        Derived from the validity windows (#1222): the wholly-future
        version with the earliest start_date; its effective_from is
        that start date. None when no version starts in the future.

        Returns:
            dict | None: {"timetable_id": ..., "effective_from": str |
            None} for the pending switch, or None when nothing is
            scheduled.
        """
        today = _sgt_date(utc_time.now())
        future: list[tuple[model.TimetableMetadata, datetime.datetime | None]] = [
            (meta, created_at)
            for meta, created_at in _version_windows()
            if _sgt_date(meta.start_date.to_datetime()) > today
        ]
        if not future:
            return None
        meta, _ = min(
            future,
            key=lambda pair: (
                _sgt_date(pair[0].start_date.to_datetime()),
                (pair[1] or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)),
            ),
        )
        return {
            "timetable_id": schema.CampusID(meta.id),
            "effective_from": str(meta.start_date),
        }

    def pointers_state(self) -> dict:
        """The pointer state served by GET /timetable/ (#1222).

        {"current": id | None, "next": id | None, "effective_from":
        ts | None} — flat, with the next version's window start.
        """
        nxt = self.get_next()
        return {
            "current": self.get_current(),
            "next": nxt["timetable_id"] if nxt else None,
            "effective_from": nxt["effective_from"] if nxt else None,
        }

class TimetableResource:
    """Represents a single timetable."""
    
    def __init__(self, timetable_id: schema.CampusID):
        self.timetable_id = timetable_id

    def get(self) -> model.Timetable:
        """Get a full Timetable (metadata + labeled entries) by ID.

        Returns:
            model.Timetable: The timetable metadata and entries.

        Raises:
            NotFoundError: If the timetable does not exist.
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

        try:
            lessongroup_labels = _get_lessongroup_labels(self.timetable_id)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        entries = []
        for entry_record in entry_records:
            entry = model.TimetableEntry.from_storage(entry_record)
            # Persisted label first (#592); the group-row join stays as
            # the fallback for legacy records created before labels
            # were persisted. The join goes dark for an old allocation
            # once its lessongroup row is reused by a newer one —
            # exactly why entries carry their own label now.
            entry.label = (
                entry.label or lessongroup_labels.get(entry.lessongroup_id)
            )
            entries.append(entry)

        return model.Timetable(
            id=schema.CampusID(record["id"]),
            created_at=schema.DateTime(record["created_at"]),
            filename=record["filename"],
            label=record.get("label"),
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

        Also deletes the lessongroup rows currently owned by this
        allocation. With label-anchored reuse (#592) those rows may be
        referenced by entries of an older allocation too; the older
        allocation's entries keep rendering (each entry persists its
        label), but the group documents themselves go away with the
        owning allocation.

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

    @property
    def attachments(self) -> "TimetableAttachmentsResource":
        """Access the timetable attachments resource."""
        return TimetableAttachmentsResource(self.timetable_id)


class TimetableEntriesResource:
    """Represents the TimetableEntries Resource."""
    def __init__(self, timetable_id: schema.CampusID):
        """Initialize with the parent timetable ID.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.
        """
        self.timetable_id = timetable_id

    def list(self) -> list[model.TimetableEntry]:
        """List all entries belonging to the timetable.

        Returns:
            list[model.TimetableEntry]: Timetable entries with lesson group labels.
        """
        records = timetable_entry_storage.get_matching({
            "timetable_id": self.timetable_id
        })
        lessongroup_labels = _get_lessongroup_labels(self.timetable_id)

        entries = []
        for record in records:
            entry = model.TimetableEntry.from_storage(record)
            # Persisted label first (#592); group-row join as the
            # legacy-record fallback (see TimetableResource.get).
            entry.label = (
                entry.label or lessongroup_labels.get(entry.lessongroup_id)
            )
            entries.append(entry)
        return entries

class TimetableMetadataResource:
    """Represents metadata for a single timetable."""
    def __init__(self, timetable_id: schema.CampusID):
        """Initialize with the timetable ID.

        Args:
            timetable_id (schema.CampusID): ID of the timetable.
        """
        self.timetable_id = timetable_id
    
    def get(self) -> model.TimetableMetadata:
        """Get the timetable metadata without entries."""
        try:
            record = timetable_collection.get_by_id(self.timetable_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Timetable not found",
                    id=self.timetable_id
                )
            try:
                return model.TimetableMetadata.from_storage(record)
            except KeyError as e:
                raise api_errors.InternalError(
                    e.args[0],
                    record=record
                ) from e
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




class TimetableAttachmentsResource:
    """Per-version attachments, stored as files in the files backend.

    An attachment is a file record whose slug sits under this version's
    ``timetables/<timetable_id>/attachments/`` prefix — the namespace is
    the binding. Records carry the committee's original filename as the
    display ``name``; content lives in the files bucket. The generic
    files routes refuse writes under the namespace to non-admins, so a
    record's presence in the prefix is proof a timetable admin put it
    there.

    Attachment identity is the underlying file id: it is what list()
    returns, what content/delete address, and what survives in URLs.
    """

    def __init__(self, timetable_id: schema.CampusID):
        """Initialize with the parent timetable ID.

        Args:
            timetable_id (CampusID): ID of the timetable.
        """
        self.timetable_id = timetable_id

    def _prefix(self) -> str:
        """This version's attachment slug prefix."""
        return attachment_slug_prefix(self.timetable_id)

    def _require_timetable(self) -> None:
        """404 when the parent timetable does not exist.

        (metadata.get() reports a missing version as a conflict — a
        pre-existing quirk this resource does not inherit: an unknown
        timetable here is a plain not-found.)
        """
        try:
            record = timetable_collection.get_by_id(str(self.timetable_id))
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if not record:
            raise api_errors.NotFoundError(
                "Timetable not found",
                id=self.timetable_id,
            )

    def _get(self, attachment_id: schema.CampusID) -> dict:
        """The attachment record, 404 unless it belongs to this version."""
        record = files_resource.FileResource(attachment_id).get()
        if not record["slug"].startswith(self._prefix()):
            raise api_errors.NotFoundError(
                "Attachment not found on this timetable",
                attachment_id=str(attachment_id),
                timetable_id=str(self.timetable_id),
            )
        return record

    def list(self) -> list[dict]:
        """List this version's attachments, newest first."""
        self._require_timetable()
        records = files_resource.FilesResource().list(prefix=self._prefix())
        return sorted(
            records,
            key=lambda record: record["created_at"],
            reverse=True,
        )

    def add(
            self,
            *,
            data: bytes,
            filename: str,
            content_type: str,
            client_id: str,
            user_id: str | None = None,
    ) -> dict:
        """Attach a file (raw bytes) to this version.

        The committee's original filename rides as the record's display
        name; the slug mints a fresh attachment uid, so re-uploading the
        same filename adds a new attachment rather than silently
        replacing one (removal is explicit).

        Raises:
            NotFoundError: unknown timetable_id.
            InvalidRequestError: empty content.
        """
        self._require_timetable()
        if not data:
            raise api_errors.InvalidRequestError(
                "Attachment content required: send the bytes as the "
                "request body"
            )
        slug = (
                self._prefix()
                + uid.generate_category_uid("ttattachment", length=8)
        )
        record, _created = files_resource.FileResource.update_content_by_slug(
            slug,
            data,
            content_type=content_type,
            client_id=client_id,
            user_id=user_id,
            name=filename,
        )
        return record

    def get_content(self, attachment_id: schema.CampusID) -> tuple[bytes, dict]:
        """The attachment's bytes and record (404 off this version)."""
        self._get(attachment_id)
        return files_resource.FileResource(attachment_id).get_content()

    def delete(self, attachment_id: schema.CampusID) -> None:
        """Remove one attachment (404 off this version)."""
        self._get(attachment_id)
        files_resource.FileResource(attachment_id).delete()

    def delete_all(self) -> int:
        """Remove every attachment (the timetable-delete cascade).

        Tolerates records already gone (per-file NotFound suppressed) —
        the version row deletes last, so a failed cascade stays
        retryable. Returns the number of files removed.
        """
        records = files_resource.FilesResource().list(prefix=self._prefix())
        removed = 0
        for record in records:
            try:
                files_resource.FileResource(record["id"]).delete()
            except api_errors.NotFoundError:
                continue
            removed += 1
        return removed
