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

The active (current/next) timetable pointers are an effective-dated
trail (#1075): every change appends a row — {timetable_id,
effective_from, actor} — and "current at T" is the latest row whose
effective_from is at or before T, so a scheduled version switch flips
as a read-time fact (no scheduler process). A pending flip is
superseded by a newer schedule or cancelled outright; effective rows
are immutable. Legacy deployments' bare @metadata pointer documents
keep resolving as a fallback until first written through the trail.
"""

import contextlib
import datetime
import typing

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
from campus.storage.documents.interface import PK

timetable_lessongroup_collection = campus.storage.get_collection("timetable_lessongroup")
timetable_lessongroupmembers_table = campus.storage.get_table("timetable_lessongroupmembers")

timetable_entry_storage = campus.storage.get_collection("timetable_entries")
timetable_collection = campus.storage.get_collection("timetables")
timetable_effective_collection = campus.storage.get_collection("timetable_effective")

# School time is Singapore time (UTC+8, no DST). A date-only pointer
# effective_from means 07:00 school time — the committee's default
# switch-over hour, before the first period. (Shared with the
# subjcombi resource, which re-exports it.)
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


def _pointer_id(value: typing.Any) -> str | None:
    """Normalise a stored pointer value to a bare timetable id.

    Legacy @metadata documents have stored pointer values both as bare
    ids and as `{"timetable_id": ...}` objects; accept either so old
    documents keep resolving as the trail fallback.
    """
    if isinstance(value, dict):
        value = value.get("timetable_id")
    return str(value) if value else None


def _pointer_rows() -> list[dict]:
    """Active (not superseded, not cancelled) pointer-trail rows."""
    try:
        records = timetable_effective_collection.get_matching({})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return [
        r for r in records
        if not r.get("superseded_by") and not r.get("cancelled_at")
    ]


def _row_effective_at(record: dict) -> datetime.datetime | None:
    """The row's effective_from as an aware UTC datetime (undated rows
    have none — they only flip when pointed at manually).
    """
    raw = record.get("effective_from")
    return utc_time.from_rfc3339(raw) if raw else None


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
        timetable_effective_collection.init_collection()
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

    def list(self, **filters: typing.Any) -> list[model.TimetableMetadata]:
        """List timetables matching the provided filters.

        Args:
            **filters: Arbitrary filter parameters applied to the storage query.

        Returns:
            list[model.TimetableMetadata]: Matching timetable metadata objects.
        """
        # Exclude metadata document
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

        Refuses to delete the version the current or next pointer
        names — move/cancel the pointer first. Historical versions
        are fair game.

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
                f"names ({timetable_id}); move the pointer first"
            )
        scheduled_next = self.get_next()
        if (
            scheduled_next is not None
            and str(scheduled_next["timetable_id"]) == str(timetable_id)
        ):
            raise api_errors.ConflictError(
                "Refusing to delete the timetable scheduled as next "
                f"({timetable_id}); cancel the pending switch first"
            )

        # TODO: Atomic transactions across multiple storage objects —
        # same caveat as new(): a mid-cascade failure leaves a partial
        # delete, which is safe for a cleanup path (the version row is
        # deleted last, so a retry is expressible).
        try:
            timetable_entry_storage.delete_matching(
                {"timetable_id": str(timetable_id)}
            )
            timetable_lessongroupmembers_table.delete_matching(
                {"timetable_id": str(timetable_id)}
            )
            timetable_lessongroup_collection.delete_matching(
                {"timetable_id": str(timetable_id)}
            )
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

        The latest effective-dated pointer row at or before `at`; falls
        back to the legacy @metadata pointer while the trail has no
        effective rows.

        Returns:
            schema.CampusID | None: The current timetable ID, or None if not set.
        """
        at_dt = at or utc_time.now()
        past: list[tuple[datetime.datetime, dict]] = []
        for row in _pointer_rows():
            effective_at = _row_effective_at(row)
            if effective_at is not None and effective_at <= at_dt:
                past.append((effective_at, row))
        if past:
            _, latest = max(past, key=lambda pair: pair[0])
            return schema.CampusID(latest["timetable_id"])
        return self._legacy_pointer("current")

    def get_next(self) -> dict | None:
        """Retrieve the next scheduled timetable and its effective date.

        Returns:
            dict | None: {"timetable_id": ..., "effective_from": str |
            None} for the pending switch — earliest future-dated row,
            else the latest undated row — or None when nothing is
            scheduled (legacy @metadata `next` resolves as undated).
        """
        now_dt = utc_time.now()
        pending: list[dict] = []
        dated: list[tuple[datetime.datetime, dict]] = []
        for row in _pointer_rows():
            effective_at = _row_effective_at(row)
            if effective_at is None or effective_at > now_dt:
                pending.append(row)
                if effective_at is not None:
                    dated.append((effective_at, row))
        if pending:
            row = (
                min(dated, key=lambda pair: pair[0])[1]
                if dated
                else max(pending, key=lambda r: r["created_at"])
            )
            return {
                "timetable_id": schema.CampusID(row["timetable_id"]),
                "effective_from": row.get("effective_from"),
            }
        legacy = self._legacy_pointer("next")
        if legacy is not None:
            return {"timetable_id": legacy, "effective_from": None}
        return None

    def pointers_state(self) -> dict:
        """The pointer state served by GET /timetable/ (#1075).

        {"current": id | None, "next": id | None, "effective_from":
        ts | None} — flat, with the pending switch's effective date.
        """
        nxt = self.get_next()
        return {
            "current": self.get_current(),
            "next": nxt["timetable_id"] if nxt else None,
            "effective_from": nxt["effective_from"] if nxt else None,
        }

    def _legacy_pointer(self, key: str) -> schema.CampusID | None:
        """Pre-trail pointer fallback: the legacy @metadata document."""
        try:
            metadata = timetable_collection.get_by_id("@metadata")
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if metadata is None:
            return None
        timetable_id = _pointer_id(metadata.get(key))
        return schema.CampusID(timetable_id) if timetable_id else None

    def _append_pointer_row(
            self,
            timetable_id: schema.CampusID,
            effective_from: datetime.datetime | None,
            actor_id: schema.UserID,
    ) -> dict:
        """Append a pointer-trail row after validating the target."""
        TimetableResource(timetable_id).get()
        row = {
            schema.CAMPUS_KEY: uid.generate_category_uid("tteffective"),
            "timetable_id": str(timetable_id),
            "effective_from": (
                utc_time.to_rfc3339(effective_from) if effective_from else None
            ),
            "actor_id": str(actor_id),
            "created_at": utc_time.to_rfc3339(utc_time.now()),
            "superseded_by": None,
            "cancelled_at": None,
            "cancelled_by": None,
        }
        try:
            timetable_effective_collection.insert_one(row)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return row

    def flip_current(
            self,
            timetable_id: schema.CampusID,
            actor_id: schema.UserID,
    ) -> None:
        """Make `timetable_id` the current timetable, effective now.

        Scheduled future switches (if any) remain pending and still
        flip at their effective dates.
        """
        self._append_pointer_row(timetable_id, utc_time.now(), actor_id)

    def schedule_next(
            self,
            timetable_id: schema.CampusID,
            effective_from: datetime.datetime | None,
            actor_id: schema.UserID,
    ) -> dict:
        """Schedule (or reschedule) the pending switch to `timetable_id`.

        `effective_from` None means undated: the switch is staged but
        only applies when pointed at manually. Any previous pending
        row is superseded (one pending switch at a time).

        Returns:
            dict: The appended trail row.
        """
        now_dt = utc_time.now()
        pending: list[dict] = []
        for stale_row in _pointer_rows():
            effective_at = _row_effective_at(stale_row)
            if effective_at is None or effective_at > now_dt:
                pending.append(stale_row)
        try:
            row = self._append_pointer_row(
                timetable_id, effective_from, actor_id
            )
            for stale in pending:
                timetable_effective_collection.update_by_id(
                    stale[schema.CAMPUS_KEY],
                    {"superseded_by": row[schema.CAMPUS_KEY]},
                )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return row

    def cancel_next(self, actor_id: schema.UserID) -> typing.List[dict]:
        """Cancel the pending switch (trail-preserving tombstones).

        Already-effective rows are immutable history and are left
        alone.
        """
        now_dt = utc_time.now()
        now_str = utc_time.to_rfc3339(now_dt)
        cancelled = []
        try:
            for r in _pointer_rows():
                ef = _row_effective_at(r)
                if ef is None or ef > now_dt:
                    timetable_effective_collection.update_by_id(
                        r[schema.CAMPUS_KEY],
                        {
                            "cancelled_at": now_str,
                            "cancelled_by": str(actor_id),
                        },
                    )
                    cancelled.append(r)
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return cancelled

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


