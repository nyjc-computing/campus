"""Performance test for TimetablesResource.new() bulk inserts (#576).

timetable.new() used to insert entries, lesson groups and members with
one storage call per record, which timed out (60 s) with a full
timetable's data. The insert_many() overrides (#576, #590, #591)
batch these inserts; this test exercises new() with a realistically
sized timetable and asserts a generous completion bound.
"""

import time
import unittest

from campus.common import env

# Configure test storage before importing any campus.storage users
env.set('STORAGE_MODE', "1")


class TestTimetableNewPerformance(unittest.TestCase):
    """Exercise timetable.new() at full-timetable scale."""

    NUM_GROUPS = 20
    ENTRIES_PER_GROUP = 25

    @classmethod
    def setUpClass(cls):
        # campus.api.resources.timetable is the TimetablesResource instance
        from campus.api import resources as api_resources

        cls.resource = api_resources.timetable
        cls.resource.init_storage()

    def tearDown(self):
        for record in self.resource.list():
            self.resource[record.id].delete()

    def _build_lessongroups(self) -> list[dict]:
        """Build a full-sized set of groups, members and entries."""
        return [
            {
                "label": f"2510-{subject}{group}",
                "members": [f"teacher-{group}-{i}" for i in range(3)],
                "entries": [
                    {
                        "weekday": f"Day {i // self.ENTRIES_PER_GROUP}",
                        "timeslot": f"{800 + (i % 10) * 100}",
                        "venue": f"5-{i % 50}",
                    }
                    for i in range(self.ENTRIES_PER_GROUP)
                ],
            }
            for group in range(self.NUM_GROUPS)
            for subject in ("Math", "Chem")
        ]

    def test_new_with_full_timetable_completes_quickly(self):
        """new() inserts a full timetable's records well within budget."""
        metadata = {
            "filename": "perf-test-timetable.xml",
            "start_date": "2026-01-01T00:00:00Z",
            "end_date": "2026-12-31T00:00:00Z",
        }
        lessongroups = self._build_lessongroups()
        expected_groups = len(lessongroups)
        expected_entries = expected_groups * self.ENTRIES_PER_GROUP
        expected_members = expected_groups * 3

        start = time.perf_counter()
        timetable = self.resource.new(metadata, lessongroups)
        elapsed = time.perf_counter() - start
        print(
            f"\ntimetable.new() with {expected_entries} entries, "
            f"{expected_groups} groups, {expected_members} members: "
            f"{elapsed:.2f}s"
        )

        # All records landed
        entries = self.resource[timetable.id].entries.list()
        self.assertEqual(len(entries), expected_entries)
        self.assertLess(
            elapsed,
            10.0,
            "timetable.new() regressed to per-row insert performance"
        )


if __name__ == '__main__':
    unittest.main()
