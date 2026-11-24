"""Unit tests for timetable version deletion (#1088).

The cleanup surface the label-drift create 409 points at: a stale
duplicate-label row is owned by the superseded version that minted it,
so deleting that version removes the row and unblocks the create. A
group row that a later create reused is owned by the later version
(update-in-place, #592/campus#1080) and survives the deletion of the
older version. The derived current and next pointer targets (#1222)
are undeletable until the validity windows change.

Tests drive the resources directly with explicit windows, so no clock
mocking is needed (same pattern as test_timetable_lessongroups).
"""

import datetime
import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
from tests.unit.api import _derived_current_stamp as _stamp

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


def _metadata(
        filename: str,
        start: datetime.datetime | None = None,
        end: datetime.datetime | None = None,
) -> dict:
    now = utc_time.now()
    return {
        "filename": filename,
        # Default window is wholly past (two to one year ago): a
        # historical version, deletable under the derived delete-guard.
        "start_date": utc_time.to_rfc3339(
            start or now - datetime.timedelta(days=730)
        ),
        "end_date": utc_time.to_rfc3339(
            end or now - datetime.timedelta(days=365)
        ),
        # created_at comes from the process-global monotonic stamp: the
        # derived-current/next tie-breaks read the clock-stamped field,
        # and Windows's ~15.6 ms system-clock tick makes back-to-back
        # creates stamp identical values (see test_timetable_lessongroups).
        "created_at": utc_time.to_rfc3339(_stamp.stamp()),
    }


def _groups(labels: list[str], entries_per_group: int = 1) -> list[dict]:
    return [
        {
            "label": label,
            "members": [f"2510-{label}-0"],
            "entries": [
                {
                    "venue": "5-64",
                    "weekday": "Mon A",
                    "timeslot": f"0{800 + i:04d}",
                }
                for i in range(entries_per_group)
            ],
        }
        for label in labels
    ]


class TestTimetableDelete(unittest.TestCase):
    def setUp(self):
        from campus.api.resources.timetable import TimetablesResource

        self.resource = TimetablesResource()
        self.resource.init_storage()
        self.marker = uuid.uuid4().hex[:6]

    def _create(self, filename: str, labels: list[str], **window):
        return self.resource.new(
            metadata=_metadata(f"{self.marker}-{filename}", **window),
            lessongroups=_groups(labels),
        )

    def test_delete_removes_version_and_rows(self):
        """Deleting a version removes its entries, members, groups and the
        version row itself."""
        from campus.api.resources.timetable import (
            timetable_collection,
            timetable_entry_storage,
            timetable_lessongroup_collection,
            timetable_lessongroupmembers_table,
        )

        v1 = self._create("v1.xml", ["25A-Math", "25A-Phy"])
        tid = str(v1.id)
        self.resource.delete(v1.id)

        self.assertEqual(
            timetable_entry_storage.get_matching({"timetable_id": tid}), []
        )
        self.assertEqual(
            timetable_lessongroupmembers_table.get_matching({"timetable_id": tid}),
            [],
        )
        self.assertEqual(
            timetable_lessongroup_collection.get_matching({"timetable_id": tid}), []
        )
        self.assertIsNone(timetable_collection.get_by_id(tid))

    def test_delete_keeps_group_row_reused_by_later_version(self):
        """A group row a later create reused is owned by that later version
        (update-in-place) and survives the older version's deletion; the
        later version keeps rendering."""
        v1 = self._create("v1.xml", ["25A-Math"])
        v2 = self._create("v2.xml", ["25A-Math"])
        self.resource.delete(v1.id)

        from campus.api.resources.timetable import (
            timetable_lessongroup_collection,
        )

        rows = timetable_lessongroup_collection.get_matching(
            {"label": "25A-Math"}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timetable_id"], str(v2.id))
        self.assertEqual(
            {entry.label for entry in self.resource[str(v2.id)].entries.list()},
            {"25A-Math"},
        )

    def test_delete_refuses_derived_current(self):
        # A window covering today makes the version derived-current.
        # The start is staggered forward (1h ago, not 1d) so this
        # version wins the derived-current key's start-date leg over
        # any earlier test's covering version; created_at (the other
        # tie-break leg) comes from the monotonic stamp, so the pick
        # stays deterministic even when the Windows clock tick makes
        # real stamps identical — on an exact tie the derived-current
        # pick degenerated to storage row order and the delete wrongly
        # succeeded.
        now = utc_time.now()
        v1 = self._create(
            "v1.xml",
            ["25A-Math"],
            start=now - datetime.timedelta(hours=1),
            end=now + datetime.timedelta(days=30),
        )
        with self.assertRaises(api_errors.ConflictError):
            self.resource.delete(v1.id)
        # A historical (wholly-past window) version deletes fine.
        v2 = self._create("v2.xml", ["25B-Chem"])
        self.resource.delete(v2.id)

    def test_delete_refuses_derived_next(self):
        # A wholly-future window makes the version derived-next
        # (earliest future start).
        now = utc_time.now()
        v1 = self._create("v1.xml", ["25A-Math"])
        v2 = self._create(
            "v2.xml",
            ["25B-Chem"],
            start=now + datetime.timedelta(days=60),
            end=now + datetime.timedelta(days=300),
        )
        with self.assertRaises(api_errors.ConflictError):
            self.resource.delete(v2.id)
        # The historical version is deletable while v2 sits in next.
        self.resource.delete(v1.id)

    def test_delete_unknown_version_404s(self):
        from campus.common import schema

        with self.assertRaises(api_errors.NotFoundError):
            self.resource.delete(schema.CampusID(f"uid-timetable-{uuid.uuid4().hex[:8]}"))

    def test_delete_clears_label_drift_blocking_create(self):
        """The money test: a stale duplicate-label row (minted by a
        superseded version) 409s every later create with that label;
        deleting the owning version removes the row and unblocks the
        create."""
        from campus.api.resources.timetable import (
            timetable_lessongroup_collection,
        )

        v1 = self._create("v1.xml", ["25A-Math"])
        v2 = self._create("v2.xml", ["25A-Math"])  # reuses v1's row → owned by v2
        # Label-anchored reuse moves the row update-in-place: one row,
        # owned by the newest version.
        rows = timetable_lessongroup_collection.get_matching(
            {"label": "25A-Math"}
        )
        self.assertEqual([r["timetable_id"] for r in rows], [str(v2.id)])

        # Simulate pre-reuse drift: a second "25A-Math" row minted by (and
        # owned by) the superseded v1.
        timetable_lessongroup_collection.insert_one(
            {
                "id": uid.generate_category_uid("lesson-group"),
                "timetable_id": str(v1.id),
                "label": "25A-Math",
            }
        )

        with self.assertRaises(api_errors.ConflictError):
            self._create("v3.xml", ["25A-Math"])

        self.resource.delete(v1.id)

        v3 = self._create("v3.xml", ["25A-Math"])
        rows = timetable_lessongroup_collection.get_matching(
            {"label": "25A-Math"}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timetable_id"], str(v3.id))


if __name__ == "__main__":
    unittest.main()


class TestTimetableDeleteEdgeFamilies(unittest.TestCase):
    """A version whose row families are empty deletes cleanly.

    Regression guard for the dev cleanup: the postgres backend raises
    NoChangesAppliedError on a zero-match delete_matching, which aborted
    the cascade for versions with no entries (14 of dev's 57 versions).
    """

    def setUp(self):
        from campus.api.resources.timetable import TimetablesResource

        self.resource = TimetablesResource()
        self.resource.init_storage()
        self.marker = uuid.uuid4().hex[:6]

    def test_delete_version_with_no_entries_or_groups(self):
        from campus.api.resources.timetable import (
            timetable_collection,
            timetable_entry_storage,
        )

        v1 = self.resource.new(
            metadata=_metadata(f"{self.marker}-empty.xml"),
            lessongroups=[],  # legal create: no groups, no entries, no members
        )
        self.resource.delete(v1.id)

        self.assertEqual(
            timetable_entry_storage.get_matching({"timetable_id": str(v1.id)}),
            [],
        )
        self.assertIsNone(timetable_collection.get_by_id(str(v1.id)))


if __name__ == "__main__":
    unittest.main()
