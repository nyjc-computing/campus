"""Unit tests for the effective-dated timetable pointer trail (#1075).

current(T) is the latest trail row at or before T; a pending switch
(one per deployment) is superseded by a newer schedule or cancelled
outright; legacy @metadata pointers keep resolving as a fallback.
Tests pass explicit `at` times, so no clock mocking is needed.
"""

import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors
from campus.common.utils import utc_time

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestTimetablePointerTrail(unittest.TestCase):
    """Effective-dated pointer semantics."""

    def setUp(self):
        import contextlib

        import campus.storage
        from campus.api.resources.timetable import (
            TimetablesResource,
            timetable_collection,
            timetable_effective_collection,
        )

        # The pointer trail is deployment-global: reset it per test
        # (test storage persists across tests in the process).
        timetable_effective_collection.delete_matching({})
        with contextlib.suppress(campus.storage.errors.NotFoundError):
            timetable_collection.delete_by_id("@metadata")
        self.timetables = TimetablesResource()
        self.timetables.init_storage()
        self.admin = "admin@campus.test"
        self.tt_a = self._create_timetable("a")
        self.tt_b = self._create_timetable("b")

    def _create_timetable(self, tag: str) -> str:
        timetable = self.timetables.new(
            metadata={
                "filename": f"pointers-{uuid.uuid4().hex[:8]}-{tag}.xml",
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-12-31T00:00:00Z",
            },
            lessongroups=[],
        )
        return timetable.id

    def test_flip_current_and_state(self):
        self.timetables.flip_current(self.tt_a, actor_id=self.admin)
        self.assertEqual(self.timetables.get_current(), self.tt_a)
        state = self.timetables.pointers_state()
        self.assertEqual(state["current"], self.tt_a)
        self.assertIsNone(state["next"])
        self.assertIsNone(state["effective_from"])

    def test_scheduled_switch_flips_by_read_time(self):
        soon = utc_time.after(hours=1)
        later = utc_time.after(hours=2)
        self.timetables.flip_current(self.tt_a, actor_id=self.admin)
        self.timetables.schedule_next(
            self.tt_b, effective_from=soon, actor_id=self.admin
        )
        self.assertEqual(self.timetables.get_current(), self.tt_a)
        nxt = self.timetables.get_next()
        self.assertEqual(nxt["timetable_id"], self.tt_b)
        self.assertEqual(nxt["effective_from"], utc_time.to_rfc3339(soon))
        # After the effective time, the switch has happened.
        self.assertEqual(self.timetables.get_current(at=later), self.tt_b)

    def test_reschedule_supersedes_pending_switch(self):
        soon = utc_time.after(hours=1)
        later = utc_time.after(hours=2)
        first = self.timetables.schedule_next(
            self.tt_a, effective_from=soon, actor_id=self.admin
        )
        second = self.timetables.schedule_next(
            self.tt_b, effective_from=later, actor_id=self.admin
        )
        # The pending view points only at the latest schedule.
        self.assertEqual(self.timetables.get_next()["timetable_id"], self.tt_b)
        history = self._pointer_history()
        self.assertEqual(len(history), 2)
        stored_first = next(r for r in history if r["id"] == first["id"])
        self.assertEqual(stored_first["superseded_by"], second["id"])

    def _pointer_history(self):
        from campus.api.resources.timetable import timetable_effective_collection
        return timetable_effective_collection.get_matching({})

    def test_undated_next_stages_but_does_not_flip(self):
        self.timetables.flip_current(self.tt_a, actor_id=self.admin)
        self.timetables.schedule_next(
            self.tt_b, effective_from=None, actor_id=self.admin
        )
        nxt = self.timetables.get_next()
        self.assertEqual(nxt["timetable_id"], self.tt_b)
        self.assertIsNone(nxt["effective_from"])
        # Undated switches never flip by themselves.
        self.assertEqual(self.timetables.get_current(), self.tt_a)

    def test_cancel_pending_switch(self):
        self.timetables.schedule_next(
            self.tt_a, effective_from=utc_time.after(hours=1),
            actor_id=self.admin,
        )
        self.timetables.cancel_next(actor_id=self.admin)
        self.assertIsNone(self.timetables.get_next())
        self.assertIsNone(self.timetables.get_current())

    def test_flip_current_keeps_future_switch_pending(self):
        soon = utc_time.after(hours=1)
        self.timetables.flip_current(self.tt_a, actor_id=self.admin)
        self.timetables.schedule_next(
            self.tt_b, effective_from=soon, actor_id=self.admin
        )
        self.timetables.flip_current(self.tt_a, actor_id=self.admin)
        self.assertEqual(self.timetables.get_current(), self.tt_a)
        self.assertEqual(self.timetables.get_next()["timetable_id"], self.tt_b)

    def test_unknown_timetable_pointer_rejected(self):
        with self.assertRaises(api_errors.NotFoundError):
            self.timetables.flip_current(
                "uid-timetable-nonexistent", actor_id=self.admin
            )

    def test_legacy_metadata_pointer_fallback(self):
        from campus.api.resources.timetable import _upsert, timetable_collection
        # Bare-id shape.
        _upsert(timetable_collection, "@metadata", {"current": self.tt_a})
        self.assertEqual(self.timetables.get_current(), self.tt_a)
        # Object shape.
        _upsert(
            timetable_collection,
            "@metadata",
            {"current": {"timetable_id": self.tt_b}},
        )
        self.assertEqual(self.timetables.get_current(), self.tt_b)
