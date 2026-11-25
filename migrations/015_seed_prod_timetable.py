"""Seed the production timetable domain with v1's live version.

Revision ID: 015
Create Date: 2026-11-25

TARGET_DB is "api": the timetable collections (``timetables``,
``timetable_lessongroup``, ``timetable_entries``) and the
``timetable_lessongroupmembers`` table belong to campus.api.

campus.api's timetable domain was empty on production when the school
started evaluating timetable-v2 as the v1 replacement (the committee's
test pilot needs a current version to see, edit and replace). This
migration inserts ONE timetable version — v1's live export, "no j1
(18 sep)", validity window 2026-09-18 .. 2026-11-27 (the committee
ruled the timetable valid to the end of that week) — using the exact
model/storage layer the POST /timetable/ route writes through
(campus.model.timetable + campus.storage), so rows are indistinguishable
from a UI import, down to label-anchored lessongroup reuse (#592).

The seed DATA never enters the repository (it carries staff names):
stage it at trigger time as ``TIMETABLE_SEED_PAYLOAD`` — gzip + base64
of one JSON object::

    {"metadata": {"filename": ..., "start_date": "YYYY-MM-DD",
                  "end_date": "YYYY-MM-DD", "label": ...},
     "lessongroups": [{"label": ..., "members": [...],
                       "entries": [{"venue", "weekday", "timeslot"}]}]}

The canonical producer is timetable-v2's scripts/seed_timetable_from_xml.py
(ttv2 PR #180 branch point), which runs the tt_file pipeline over the v1
XML export and prints the payload; the same version has already been
seeded through the API lane as campus-admin@, so on production this
migration's upgrade() is expected to detect the existing filename and
record the ledger entry as a no-op.

Environments without TIMETABLE_SEED_PAYLOAD set are the normal case:
upgrade() prints the staging instructions and exits without writing,
so dev/test boot auto-apply stays green.

Run from a context where the api service's MongoDB resolves (the api
container itself, or the campus-migrate job with
MIGRATE_JOB_API_MONGODB_URI wired):

    python migrations/015_seed_prod_timetable.py             # dry run
    python migrations/015_seed_prod_timetable.py --apply     # write

or through the runner, which applies pending api migrations:

    python migrations/runner.py apply --db api
"""

import base64
import gzip
import json
import os

from campus.common import schema
from campus.model.timetable import (
    LessonGroup,
    LessonGroupMember,
    TimetableEntry,
    TimetableMetadata,
)
from campus.storage import get_collection, get_table

TARGET_DB = "api"

PAYLOAD_ENV = "TIMETABLE_SEED_PAYLOAD"

timetable_collection = get_collection("timetables")
timetable_lessongroup_collection = get_collection("timetable_lessongroup")
timetable_entry_collection = get_collection("timetable_entries")
timetable_members_table = get_table("timetable_lessongroupmembers")

ROLLBACK_SUPPORTED = "ddl"


def _load_payload() -> dict | None:
    """The staged seed payload, or None when not staged."""
    raw = os.environ.get(PAYLOAD_ENV, "").strip()
    if not raw:
        return None
    return json.loads(gzip.decompress(base64.b64decode(raw)))


def _existing_version(filename: str) -> dict | None:
    """The version row carrying this filename, if any."""
    for record in timetable_collection.get_matching({"filename": filename}):
        if str(record.get("id", "")).startswith("@"):
            continue  # retired legacy pointer documents are not versions
        return record
    return None


def _group_for_label(label: str, timetable_id) -> tuple[LessonGroup, bool]:
    """Label-anchored group reuse, mirroring the resource layer (#592)."""
    matches = timetable_lessongroup_collection.get_matching({"label": label})
    if len(matches) > 1:
        raise SystemExit(
            f"historical drift: label {label!r} is claimed by rows "
            f"{sorted(m['id'] for m in matches)} — clean up the owning "
            "superseded versions first"
        )
    if matches:
        return (
            LessonGroup(
                id=schema.CampusID(matches[0]["id"]),
                timetable_id=timetable_id,
                label=label,
            ),
            True,
        )
    return LessonGroup(timetable_id=timetable_id, label=label), False


def seed(payload: dict, *, apply: bool) -> int:
    """Insert the staged version; returns 1 when already present."""
    metadata_raw = payload["metadata"]
    filename = metadata_raw["filename"]
    existing = _existing_version(filename)
    if existing is not None:
        print(
            f"version {filename!r} already present (id {existing['id']}, "
            f"created {existing.get('created_at')}) — nothing to seed"
        )
        return 1

    meta = TimetableMetadata(**metadata_raw)
    groups: list[LessonGroup] = []
    reused_ids: list[str] = []
    members: list[LessonGroupMember] = []
    entries: list[TimetableEntry] = []

    labels = [group["label"] for group in payload["lessongroups"]]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise SystemExit(f"duplicate labels in payload: {duplicates}")

    for raw_group in payload["lessongroups"]:
        group, reused = _group_for_label(raw_group["label"], meta.id)
        if reused:
            reused_ids.append(group.id)
        else:
            groups.append(group)
        for participant in raw_group.get("members", []):
            members.append(
                LessonGroupMember(
                    timetable_id=meta.id,
                    lessongroup_id=group.id,
                    ade_participant=participant,
                )
            )
        for raw_entry in raw_group.get("entries", []):
            entries.append(
                TimetableEntry(
                    timetable_id=meta.id,
                    lessongroup_id=group.id,
                    weekday=raw_entry["weekday"],
                    timeslot=raw_entry["timeslot"],
                    venue=raw_entry.get("venue"),
                    label=raw_group["label"],
                )
            )

    print(
        f"{filename!r} window {metadata_raw['start_date']}.."
        f"{metadata_raw['end_date']}: {len(payload['lessongroups'])} groups "
        f"({len(reused_ids)} reused by label), {len(members)} members, "
        f"{len(entries)} entries"
    )
    if not apply:
        print("dry run: no changes written")
        return 0

    timetable_collection.insert_one(meta.to_storage())
    for group_id in reused_ids:
        timetable_lessongroup_collection.update_by_id(
            str(group_id), {"timetable_id": str(meta.id)}
        )
    for name, storage, records in (
        ("entries", timetable_entry_collection, entries),
        ("lessongroups", timetable_lessongroup_collection, groups),
        ("members", timetable_members_table, members),
    ):
        if records:
            storage.insert_many([record.to_storage() for record in records])
        print(f"inserted {len(records)} {name}")
    return 0


def upgrade(apply: bool = False) -> None:
    """Seed the staged version (dry run unless apply)."""
    payload = _load_payload()
    if payload is None:
        print(
            f"{PAYLOAD_ENV} is not set — no seed data staged, nothing to do. "
            "Stage the gzip+base64 payload JSON (see this file's docstring; "
            "scripts/seed_timetable_from_xml.py in timetable-v2 produces it) "
            "at trigger time if this environment needs the seed."
        )
        return
    seed(payload, apply=apply)


def downgrade() -> None:
    """Remove the seeded version and its rows.

    Refuses when the version row no longer matches the staged payload's
    filename (the committee may have edited or replaced it by then) —
    clear TIMETABLE_SEED_PAYLOAD to acknowledge and roll back blind.
    """
    payload = _load_payload()
    if payload is None:
        print(
            f"{PAYLOAD_ENV} is not set — cannot identify the seeded version; "
            "set the payload again (or clear it deliberately to roll back "
            "blind) to reverse this migration."
        )
        return
    record = _existing_version(payload["metadata"]["filename"])
    if record is None:
        print("seeded version not found — nothing to reverse")
        return
    timetable_id = record["id"]
    print(f"reversing seed: deleting version {timetable_id} and its rows")
    for storage in (
        timetable_entry_collection,
        timetable_lessongroup_collection,
    ):
        storage.delete_matching({"timetable_id": timetable_id})
    timetable_members_table.delete_matching({"timetable_id": timetable_id})
    timetable_collection.delete_by_id(timetable_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the seed (the default run is a dry run)",
    )
    args = parser.parse_args()
    upgrade(apply=args.apply)
