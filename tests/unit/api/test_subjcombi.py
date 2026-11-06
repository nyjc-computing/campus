"""Unit tests for the subjcombi resource trail semantics (#592).

The mapping model is effective-dated append-only records: current =
latest record with effective_from <= query time; pending records are
superseded by newer sets or cancelled outright; effective records are
immutable. Tests drive the resource directly and pass explicit `at`
times, so no clock mocking is needed. Each test uses a fresh user id —
test storage persists across tests in the process.
"""

import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors
from campus.common.utils import utc_time

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestSubjcombiTrail(unittest.TestCase):
    """Effective-dating, supersede and cancel semantics."""

    def setUp(self):
        from campus.api.resources import subjcombi
        from campus.api.resources.timetable import TimetablesResource

        TimetablesResource().init_storage()
        self.subjcombi = subjcombi
        self.user = f"student-{uuid.uuid4().hex[:8]}@campus.test"
        self.admin = "admin@campus.test"
        self.lg_a = "uid-lessongroup-testa"
        self.lg_b = "uid-lessongroup-testb"
        self._seed_lessongroup(self.lg_a)
        self._seed_lessongroup(self.lg_b)

    def _seed_lessongroup(self, lessongroup_id):
        from campus.api.resources.timetable import timetable_lessongroup_collection
        timetable_lessongroup_collection.insert_one({
            "id": lessongroup_id,
            "timetable_id": "uid-timetable-test",
            "label": "25A1",
        })

    def test_immediate_set_is_current_with_trail_fields(self):
        self.subjcombi.set_mapping(self.user, self.lg_a, actor_id=self.admin)
        current = self.subjcombi.get_current(self.user)
        self.assertIsNotNone(current)
        self.assertEqual(current["lessongroup_id"], self.lg_a)
        self.assertIsNone(current["previous_lessongroup_id"])
        self.assertEqual(current["actor_id"], self.admin)

    def test_scheduled_record_takes_effect_by_read_time(self):
        soon = utc_time.after(hours=1)
        later = utc_time.after(hours=2)
        self.subjcombi.set_mapping(
            self.user, self.lg_b, actor_id=self.admin, effective_from=soon
        )
        self.assertIsNone(self.subjcombi.get_current(self.user))
        current = self.subjcombi.get_current(self.user, at=later)
        self.assertEqual(current["lessongroup_id"], self.lg_b)

    def test_second_set_chains_previous_value(self):
        self.subjcombi.set_mapping(
            self.user, self.lg_a, actor_id=self.admin,
            effective_from=utc_time.after(hours=-1),
        )
        self.subjcombi.set_mapping(self.user, self.lg_b, actor_id=self.admin)
        current = self.subjcombi.get_current(self.user)
        self.assertEqual(current["lessongroup_id"], self.lg_b)
        self.assertEqual(current["previous_lessongroup_id"], self.lg_a)
        history = self.subjcombi.get_history(self.user)
        self.assertEqual([r["lessongroup_id"] for r in history],
                         [self.lg_b, self.lg_a])

    def test_new_set_supersedes_pending_record(self):
        soon = utc_time.after(hours=1)
        first = self.subjcombi.set_mapping(
            self.user, self.lg_a, actor_id=self.admin, effective_from=soon
        )
        second = self.subjcombi.set_mapping(
            self.user, self.lg_b, actor_id=self.admin, effective_from=soon
        )
        history = self.subjcombi.get_history(self.user)
        stored_first = next(
            r for r in history if r["id"] == first["id"]
        )
        self.assertEqual(stored_first["superseded_by"], second["id"])
        self.assertEqual(len(self.subjcombi.pending(self.user)), 1)
        self.assertEqual(
            self.subjcombi.pending(self.user)[0]["lessongroup_id"], self.lg_b
        )

    def test_cancel_pending_and_conflicts(self):
        soon = utc_time.after(hours=1)
        record = self.subjcombi.set_mapping(
            self.user, self.lg_a, actor_id=self.admin, effective_from=soon
        )
        cancelled = self.subjcombi.cancel(record["id"], actor_id=self.admin)
        self.assertIsNotNone(cancelled["cancelled_at"])
        self.assertEqual(cancelled["cancelled_by"], self.admin)
        self.assertIsNone(self.subjcombi.get_current(self.user))

        with self.assertRaises(api_errors.ConflictError):
            self.subjcombi.cancel(record["id"], actor_id=self.admin)

        effective = self.subjcombi.set_mapping(
            self.user, self.lg_b, actor_id=self.admin
        )
        with self.assertRaises(api_errors.ConflictError):
            self.subjcombi.cancel(effective["id"], actor_id=self.admin)

    def test_unknown_lessongroup_rejected(self):
        with self.assertRaises(api_errors.InvalidRequestError):
            self.subjcombi.set_mapping(
                self.user,
                "uid-lessongroup-nonexistent",
                actor_id=self.admin,
            )

    def test_parse_effective_from_variants(self):
        import datetime

        parse = self.subjcombi.parse_effective_from
        # Date-only: 07:00 school time = 23:00 UTC the day before.
        self.assertEqual(
            parse("2027-03-01"),
            datetime.datetime(2027, 2, 28, 23, 0,
                              tzinfo=datetime.timezone.utc),
        )
        # Full ISO datetime with Z.
        self.assertEqual(
            parse("2027-03-01T12:00:00Z"),
            datetime.datetime(2027, 3, 1, 12, 0,
                              tzinfo=datetime.timezone.utc),
        )
        # Naive datetime is interpreted as school time.
        self.assertEqual(
            parse("2027-03-01T09:00:00"),
            datetime.datetime(2027, 3, 1, 1, 0,
                              tzinfo=datetime.timezone.utc),
        )
        # Absent = now (immediate).
        self.assertIsNotNone(parse(None))
        with self.assertRaises(api_errors.InvalidRequestError):
            parse("not-a-date")


class TestSubjcombiResolve(unittest.TestCase):
    """Resolution chain: mapping overrides roster, else unmapped."""

    def setUp(self):
        from campus.api.resources import subjcombi
        from campus.api.resources.timetable import TimetablesResource

        TimetablesResource().init_storage()
        self.subjcombi = subjcombi
        self.timetables = TimetablesResource()
        self.mapped = "mapped.student@campus.test"
        self.roster_student = "roster.student@campus.test"
        self.unknown = "nobody@campus.test"

    def test_mapping_overrides_roster_and_unmapped(self):
        timetable = self.timetables.new(
            metadata={
                "filename": "resolve-test.xml",
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-12-31T00:00:00Z",
            },
            lessongroups=[{
                "label": "25A1",
                "members": [self.roster_student],
                "entries": [
                    {"weekday": "MON", "timeslot": "0800", "venue": "B1-01"}
                ],
            }],
        )
        self.timetables.flip_current(timetable.id, actor_id="admin@campus.test")

        # No maintained mapping: the roster answers for its member.
        lessongroup_id = timetable.entries[0].lessongroup_id
        group, source = self.subjcombi.resolve(self.roster_student)
        self.assertEqual(source, "roster")
        self.assertEqual(group, lessongroup_id)

        # A maintained mapping overrides the roster.
        self.subjcombi.set_mapping(
            self.mapped, lessongroup_id, actor_id="admin@campus.test",
        )
        group, source = self.subjcombi.resolve(self.mapped)
        self.assertEqual(source, "mapping")
        self.assertEqual(group, lessongroup_id)

        # Nobody knows the unknown user.
        group, source = self.subjcombi.resolve(self.unknown)
        self.assertIsNone(group)
        self.assertEqual(source, "unmapped")
