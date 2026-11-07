"""Unit tests for label-anchored lessongroup reuse in new() (#592,
campus#1080).

The identity ruling: a lessongroup's label anchors its identity within
a cohort year, so creating a new timetable version with the same
labels reuses the same group ids (the row's timetable_id moves to the
new version, update-in-place) and subjcombi mappings keyed by
lessongroup_id survive the switch. Two rows sharing a label is
historical drift → 409; a label repeated within one payload → 400.
Entries persist their own label (campus-model#5) so an old version
keeps rendering after its group row moves on.

Tests drive the resources directly and pass explicit times, so no
clock mocking is needed (same pattern as test_timetable_pointers).
"""

import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


def _metadata(filename: str) -> dict:
    return {
        "filename": filename,
        "start_date": "2026-01-01T00:00:00Z",
        "end_date": "2026-12-31T00:00:00Z",
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


class TestLessongroupReuse(unittest.TestCase):
    """Label-anchored reuse across timetable versions."""

    def setUp(self):
        from campus.api.resources.timetable import TimetablesResource

        self.resource = TimetablesResource()
        self.resource.init_storage()
        self.marker = uuid.uuid4().hex[:6]

    def _create(self, filename: str, labels: list[str]):
        return self.resource.new(
            metadata=_metadata(f"{self.marker}-{filename}"),
            lessongroups=_groups(labels),
        )

    def test_same_label_across_versions_reuses_id(self):
        """Creating v2 with the same labels keeps v1's group ids."""
        v1 = self._create("v1.xml", ["25A-Math", "25A-Phy"])
        v2 = self._create("v2.xml", ["25A-Math", "25A-Phy"])

        v1_ids = {e.lessongroup_id for e in v1.entries}
        v2_ids = {e.lessongroup_id for e in v2.entries}
        self.assertEqual(len(v1_ids), 2)
        self.assertEqual(v1_ids, v2_ids)

    def test_reuse_moves_row_update_in_place(self):
        """The reused row's timetable_id moves; no duplicate rows."""
        from campus.api.resources.timetable import (
            timetable_lessongroup_collection,
        )

        self._create("v1.xml", ["25A-Math"])
        v2 = self._create("v2.xml", ["25A-Math"])
        rows = timetable_lessongroup_collection.get_matching(
            {"label": "25A-Math"}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timetable_id"], v2.id)

    def test_entries_persist_label(self):
        """New entries store their label (campus-model#5)."""
        from campus.api.resources.timetable import timetable_entry_storage

        v1 = self._create("v1.xml", ["25A-Math"])
        self._create("v2.xml", ["25A-Math"])
        stored = timetable_entry_storage.get_matching(
            {"timetable_id": str(v1.id)}
        )
        self.assertEqual(
            {record["label"] for record in stored}, {"25A-Math"}
        )

    def test_old_version_renders_labels_after_reuse(self):
        """v1 entries keep their labels after the group row moves to v2.

        The persisted entry label wins; the group-row join (keyed on
        the *old* timetable_id) returns nothing for the moved row, so
        without persistence v1 would render label-less.
        """
        v1 = self._create("v1.xml", ["25A-Math"])
        self._create("v2.xml", ["25A-Math"])
        entries = self.resource[str(v1.id)].entries.list()
        self.assertEqual(
            {entry.label for entry in entries}, {"25A-Math"}
        )

    def test_new_label_mints_fresh_id(self):
        """A label new to v2 gets its own id."""
        v1 = self._create("v1.xml", ["25A-Math"])
        v2 = self._create("v2.xml", ["25A-Math", "25B-Chem"])
        v1_ids = {e.lessongroup_id for e in v1.entries}
        v2_ids = {e.lessongroup_id for e in v2.entries}
        fresh = v2_ids - v1_ids
        self.assertEqual(len(fresh), 1)

    def test_label_absent_from_v2_leaves_row_untouched(self):
        """A label dropped from v2 keeps its row (and timetable_id)."""
        from campus.api.resources.timetable import (
            timetable_lessongroup_collection,
        )

        v1 = self._create("v1.xml", ["25A-Math", "25A-Phy"])
        dropped_id = next(
            e.lessongroup_id for e in v1.entries
            if e.label == "25A-Phy"
        )
        self._create("v2.xml", ["25A-Math"])
        rows = timetable_lessongroup_collection.get_matching(
            {"label": "25A-Phy"}
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], str(dropped_id))
        self.assertEqual(rows[0]["timetable_id"], str(v1.id))

    def test_duplicate_labels_in_payload_rejected(self):
        """The same label twice in one create payload is a 400."""
        with self.assertRaises(api_errors.InvalidRequestError):
            self.resource.new(
                metadata=_metadata("dupe.xml"),
                lessongroups=_groups(["25A-Math", "25A-Math"]),
            )


class TestLessongroupDrift(unittest.TestCase):
    """Conflicting duplicate-label rows refuse the create (409)."""

    def setUp(self):
        from campus.api.resources.timetable import (
            TimetablesResource,
            timetable_lessongroup_collection,
        )

        self.resource = TimetablesResource()
        self.resource.init_storage()
        self.collection = timetable_lessongroup_collection
        self.marker = uuid.uuid4().hex[:6]

    def _seed_drift(self, label: str) -> str:
        """Two rows sharing a label with distinct ids (legacy drift).

        The label carries the test's marker so the seeded drift cannot
        collide with other tests' labels (storage persists across
        tests in the process).
        """
        label = f"{label}-{self.marker}"
        for suffix in ("a", "b"):
            self.collection.insert_one({
                "id": f"uid-lesson-group-{self.marker}-{suffix}",
                "timetable_id": f"uid-timetable-{self.marker}-{suffix}",
                "label": label,
            })
        return label

    def test_drift_conflicts(self):
        """new() raises ConflictError naming the label."""
        label = self._seed_drift("25A-Math")
        with self.assertRaises(api_errors.ConflictError) as ctx:
            self.resource.new(
                metadata=_metadata("v1.xml"),
                lessongroups=_groups([label]),
            )
        self.assertIn(label, str(ctx.exception))

    def test_untouched_label_is_reusable_after_unrelated_drift(self):
        """Drift on one label does not block creates without it."""
        self._seed_drift("25A-Math")
        timetable = self.resource.new(
            metadata=_metadata("v1.xml"),
            lessongroups=_groups(["25B-Chem"]),
        )
        self.assertEqual(
            {e.label for e in timetable.entries}, {"25B-Chem"}
        )


class TestSubjcombiMappingSurvivesVersionSwitch(unittest.TestCase):
    """The two-version lifecycle: a mapping set on v1 resolves on v2."""

    def setUp(self):
        from campus.api.resources import subjcombi
        from campus.api.resources.timetable import TimetablesResource

        self.subjcombi = subjcombi
        self.resource = TimetablesResource()
        self.resource.init_storage()
        self.marker = uuid.uuid4().hex[:6]
        self.user = f"student-{self.marker}@campus.test"

    def _create(self, filename: str, labels: list[str]):
        return self.resource.new(
            metadata=_metadata(f"{self.marker}-{filename}"),
            lessongroups=_groups(labels),
        )

    def test_mapping_survives_switch(self):
        """set_mapping on v1 → v2 reuses the id → mapping still resolves."""
        v1 = self._create("v1.xml", ["25A-Math"])
        group_id = v1.entries[0].lessongroup_id

        self.subjcombi.set_mapping(
            user_id=self.user,
            lessongroup_id=group_id,
            actor_id="admin@campus.test",
        )
        resolved, source = self.subjcombi.resolve(self.user)
        self.assertEqual(source, "mapping")
        self.assertEqual(resolved, group_id)

        v2 = self._create("v2.xml", ["25A-Math"])
        self.assertEqual(v2.entries[0].lessongroup_id, group_id)
        resolved, source = self.subjcombi.resolve(self.user)
        self.assertEqual(source, "mapping")
        self.assertEqual(resolved, group_id)

    def test_mapping_to_dropped_group_still_resolves(self):
        """A mapping to a group absent from v2 keeps resolving to it."""
        v1 = self._create("v1.xml", ["25A-Math", "25A-Phy"])
        phy_id = next(
            e.lessongroup_id for e in v1.entries if e.label == "25A-Phy"
        )
        self.subjcombi.set_mapping(
            user_id=self.user,
            lessongroup_id=phy_id,
            actor_id="admin@campus.test",
        )
        self._create("v2.xml", ["25A-Math"])
        resolved, source = self.subjcombi.resolve(self.user)
        self.assertEqual(source, "mapping")
        self.assertEqual(resolved, phy_id)


if __name__ == '__main__':
    unittest.main()
