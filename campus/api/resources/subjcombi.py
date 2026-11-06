"""campus.api.resources.subjcombi

Subject-combination (subjcombi) resource: the maintained mapping of a
user to a timetable lessongroup (#592).

One active mapping per user at any instant: every change appends an
effective-dated record, and the current mapping is the latest record
whose `effective_from` is at or before the query time. A scheduled
change is simply a record with a future `effective_from` — it takes
effect as a read-time fact, so no scheduler process is needed and
redeploys cannot miss a switch. Records are the mutation trail
(actor, old and new value, timestamps); pending records are superseded
or cancelled rather than rewritten, and effective records are
immutable.

A user has at most one pending record: setting a new mapping
supersedes any still-pending record (the supersede is recorded on the
old row via `superseded_by`).

Resolution chain for "the user's group" (`resolve`): maintained
mapping → the file-derived `timetable_lessongroupmembers` roster →
unmapped. The roster is written from `lessongroups[].members` when a
timetable version is created and identifies members by their XML id
(`ade_participant`), so the fallback only fires when rosters carry the
campus user id; otherwise the maintained mapping is the authority.

Boundary (ratified 2026-11-06, campus#1069): mutations are gated in
the route modules on the `subjcombi.admin` role circle — the
access-grant store is never consulted here. The resources stay
ungated for in-process callers.
"""

import datetime
import typing

import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time

from .timetable import (
    TimetablesResource,
    timetable_lessongroup_collection,
    timetable_lessongroupmembers_table,
)

subjcombi_collection = campus.storage.get_collection("subjcombi")

# School time is Singapore time (UTC+8, no DST). A date-only
# effective_from means 07:00 school time — the committee's default
# switch-over hour, before the first period.
SGT = datetime.timezone(datetime.timedelta(hours=8), name="SGT")


def to_resource(record: dict) -> dict:
    """Project a storage record into its API resource form.

    The record is the mutation trail entry and is served as-is; the
    copy protects the storage dict from caller mutation.
    """
    return dict(record)


def _now() -> datetime.datetime:
    return utc_time.now()


def parse_effective_from(raw: str | None) -> datetime.datetime:
    """Parse an effective_from request value into an aware UTC datetime.

    - absent/None: now (immediate change);
    - date-only (`YYYY-MM-DD`): 07:00 school time (SGT) on that date;
    - ISO datetime: as given, naive values interpreted as school time.
    """
    if raw is None:
        return _now()
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


def _active(records: list[dict]) -> list[dict]:
    """Records that are neither superseded nor cancelled."""
    return [
        r for r in records
        if not r.get("superseded_by") and not r.get("cancelled_at")
    ]


def _effective_at(record: dict) -> datetime.datetime:
    return utc_time.from_rfc3339(record["effective_from"])


def get_record(record_id: schema.CampusID) -> dict | None:
    """Return a subjcombi record by id, or None if absent."""
    try:
        return subjcombi_collection.get_by_id(record_id)
    except campus.storage.errors.NotFoundError:
        return None


def get_current(
        user_id: schema.UserID,
        at: datetime.datetime | None = None,
) -> dict | None:
    """The user's effective mapping record at `at` (default: now).

    Latest active record whose effective_from is at or before the
    query time; None when the user has no effective record.
    """
    at_dt = at or _now()
    try:
        records = subjcombi_collection.get_matching({"user_id": str(user_id)})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    effective = [
        r for r in _active(records) if _effective_at(r) <= at_dt
    ]
    if not effective:
        return None
    return max(effective, key=_effective_at)


def get_history(user_id: schema.UserID) -> list[dict]:
    """All mapping records for the user, newest effective_from first.

    Superseded and cancelled records are included: the trail is the
    product requirement, not just the current state.
    """
    try:
        records = subjcombi_collection.get_matching({"user_id": str(user_id)})
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return sorted(records, key=_effective_at, reverse=True)


def pending(user_id: schema.UserID | None = None) -> list[dict]:
    """Active records not yet effective, soonest switch first.

    At most one per user: setting a new mapping supersedes the
    previous pending record.
    """
    filters: dict[str, typing.Any] = {}
    if user_id is not None:
        filters["user_id"] = str(user_id)
    try:
        records = subjcombi_collection.get_matching(filters)
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    now_dt = _now()
    soonest = [
        r for r in _active(records) if _effective_at(r) > now_dt
    ]
    return sorted(soonest, key=_effective_at)


def set_mapping(
        user_id: schema.UserID,
        lessongroup_id: schema.CampusID,
        actor_id: schema.UserID,
        effective_from: datetime.datetime | None = None,
        reason: str | None = None,
) -> dict:
    """Append a mapping record for the user, superseding pending ones.

    `effective_from` None means immediate (now). `previous_
    lessongroup_id` records the value being replaced at creation time;
    the user's other still-pending records are marked superseded so at
    most one pending switch per user survives.
    """
    try:
        matches = timetable_lessongroup_collection.get_matching(
            {"id": str(lessongroup_id)}
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    if not matches:
        raise api_errors.InvalidRequestError(
            f"Unknown lessongroup {lessongroup_id!r}: the mapping must "
            "reference a lessongroup of an existing timetable"
        )

    effective_dt = effective_from or _now()
    now_str = utc_time.to_rfc3339(_now())
    previous = get_current(user_id)
    record = {
        schema.CAMPUS_KEY: uid.generate_category_uid("subjcombi"),
        "user_id": str(user_id),
        "lessongroup_id": str(lessongroup_id),
        "previous_lessongroup_id": (
            previous["lessongroup_id"] if previous else None
        ),
        "actor_id": str(actor_id),
        "reason": reason,
        "created_at": now_str,
        "effective_from": utc_time.to_rfc3339(effective_dt),
        "superseded_by": None,
        "cancelled_at": None,
        "cancelled_by": None,
    }
    try:
        for stale in pending(user_id):
            subjcombi_collection.update_by_id(
                stale[schema.CAMPUS_KEY],
                {"superseded_by": record[schema.CAMPUS_KEY]},
            )
        subjcombi_collection.insert_one(record)
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return record


def cancel(
        record_id: schema.CampusID,
        actor_id: schema.UserID,
) -> dict:
    """Cancel a pending record (trail-preserving tombstone fields).

    Effective records are immutable history and cannot be cancelled;
    superseding a pending record with a replacement is `set_mapping`'s
    job, not cancellation's.
    """
    record = get_record(record_id)
    if record is None:
        raise api_errors.NotFoundError(f"No subjcombi record {record_id!r}")
    if record.get("superseded_by"):
        raise api_errors.ConflictError(
            f"Record {record_id!r} was superseded by "
            f"{record['superseded_by']}"
        )
    if record.get("cancelled_at"):
        raise api_errors.ConflictError(
            f"Record {record_id!r} was already cancelled"
        )
    if _effective_at(record) <= _now():
        raise api_errors.ConflictError(
            f"Record {record_id!r} is already effective and is "
            "immutable history"
        )
    try:
        subjcombi_collection.update_by_id(
            record_id,
            {
                "cancelled_at": utc_time.to_rfc3339(_now()),
                "cancelled_by": str(actor_id),
            },
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return get_record(record_id) or record


def resolve(
        user_id: schema.UserID,
        at: datetime.datetime | None = None,
) -> tuple[schema.CampusID | None, str]:
    """The user's lessongroup at `at`, with its source.

    "mapping" — a maintained subjcombi record; "roster" — the
    file-derived timetable_lessongroupmembers roster of the current
    timetable (exact match on the roster's member id); "unmapped" —
    neither source knows the user.
    """
    record = get_current(user_id, at)
    if record is not None:
        return schema.CampusID(record["lessongroup_id"]), "mapping"
    current_timetable = TimetablesResource().get_current()
    if current_timetable is not None:
        try:
            rows = timetable_lessongroupmembers_table.get_matching({
                "timetable_id": current_timetable,
                "ade_participant": str(user_id),
            })
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if rows:
            return schema.CampusID(rows[0]["lessongroup_id"]), "roster"
    return None, "unmapped"
