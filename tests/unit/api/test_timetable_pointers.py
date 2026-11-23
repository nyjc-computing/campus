"""Unit tests for derived timetable pointer state (#1222).

current(T) is the version whose validity window covers T as a
Singapore school date — latest start_date wins overlapping windows;
next is the wholly-future version with the earliest start_date, its
effective_from that start date. There is no pointer document: the
windows are written with the version create / metadata patch, and the
tests pass explicit `at` instants, so no clock mocking is needed.
"""

import datetime
import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors
from campus.common.utils import utc_time

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

SGT = datetime.timezone(datetime.timedelta(hours=8))


def _rfc3339(dt: datetime.datetime) -> str:
    return utc_time.to_rfc3339(dt)


class TestDerivedPointerState(unittest.TestCase):
    """Validity-window derivation semantics."""

    def setUp(self):
        from campus.api.resources.timetable import (
            TimetablesResource,
            timetable_collection,
        )

        # Derived state reads the version rows themselves: reset them
        # per test (test storage persists across tests in the process).
        timetable_collection.delete_matching({})
        self.timetables = TimetablesResource()
        self.timetables.init_storage()
        self.admin = "admin@campus.test"
        self.now = utc_time.now()

    def _create_timetable(
            self,
            tag: str,
            start: datetime.datetime,
            end: datetime.datetime,
    ) -> str:
        timetable = self.timetables.new(
            metadata={
                "filename": f"pointers-{uuid.uuid4().hex[:8]}-{tag}.xml",
                "start_date": _rfc3339(start),
                "end_date": _rfc3339(end),
            },
            lessongroups=[],
        )
        return timetable.id

    def _window_around_now(self, **delta) -> tuple[datetime.datetime, datetime.datetime]:
        """A window that started yesterday (school dates) and ends at a
        delta from now — covering today by construction."""
        start = self.now - datetime.timedelta(days=1)
        end = utc_time.after(self.now, **delta)
        return start, end

    def test_covering_window_is_current(self):
        start, end = self._window_around_now(days=30)
        tt_a = self._create_timetable("a", start, end)
        self.assertEqual(self.timetables.get_current(), tt_a)
        state = self.timetables.pointers_state()
        self.assertEqual(state["current"], tt_a)
        self.assertIsNone(state["next"])
        self.assertIsNone(state["effective_from"])

    def test_latest_start_wins_overlapping_windows(self):
        start_old = self.now - datetime.timedelta(days=10)
        start_new = self.now - datetime.timedelta(days=1)
        end = utc_time.after(self.now, days=30)
        self._create_timetable("old", start_old, end)
        tt_new = self._create_timetable("new", start_new, end)
        self.assertEqual(self.timetables.get_current(), tt_new)

    def test_gap_between_windows_serves_null(self):
        # Every window is wholly past: nothing covers today.
        self._create_timetable(
            "past",
            self.now - datetime.timedelta(days=40),
            self.now - datetime.timedelta(days=10),
        )
        self.assertIsNone(self.timetables.get_current())
        state = self.timetables.pointers_state()
        self.assertIsNone(state["current"])

    def test_get_current_at_explicit_instant(self):
        start = self.now - datetime.timedelta(days=1)
        end = utc_time.after(self.now, days=30)
        tt_a = self._create_timetable("a", start, end)
        # Inside the window: current. A day past the end: not.
        self.assertEqual(
            self.timetables.get_current(at=utc_time.after(self.now, hours=1)),
            tt_a,
        )
        self.assertIsNone(
            self.timetables.get_current(at=utc_time.after(self.now, days=31)),
        )

    def test_end_date_is_inclusive(self):
        # The window's last day (as a school date) still covers.
        start = self.now - datetime.timedelta(days=1)
        end = utc_time.after(self.now, hours=1)
        tt_a = self._create_timetable("a", start, end)
        # An instant on the same school date as end_date: covered.
        self.assertEqual(self.timetables.get_current(), tt_a)

    def test_next_is_earliest_future_start(self):
        start_far = utc_time.after(self.now, days=10)
        start_soon = utc_time.after(self.now, days=2)
        horizon = utc_time.after(self.now, days=300)
        self._create_timetable("far", start_far, horizon)
        tt_soon = self._create_timetable("soon", start_soon, horizon)
        nxt = self.timetables.get_next()
        self.assertEqual(nxt["timetable_id"], tt_soon)
        self.assertEqual(nxt["effective_from"], _rfc3339(start_soon))
        state = self.timetables.pointers_state()
        self.assertEqual(state["next"], tt_soon)
        self.assertEqual(state["effective_from"], _rfc3339(start_soon))

    def test_past_or_covering_window_is_never_next(self):
        # A covering version and a past version, nothing future.
        covering_start = self.now - datetime.timedelta(days=1)
        self._create_timetable(
            "past",
            self.now - datetime.timedelta(days=40),
            self.now - datetime.timedelta(days=10),
        )
        self._create_timetable(
            "covering",
            covering_start,
            utc_time.after(self.now, days=30),
        )
        self.assertIsNotNone(self.timetables.get_current())
        self.assertIsNone(self.timetables.get_next())

    def test_start_date_boundary_flips_to_next_on_the_day(self):
        # A version starting tomorrow (school date) is not current
        # today and is the next pending switch; at tomorrow's midnight
        # (school time) it becomes current and the pending switch is
        # gone. Anchored to Singapore midnight so the test cannot
        # flake on the wall clock.
        sgt_midnight_tomorrow = datetime.datetime.combine(
            (self.now.astimezone(SGT) + datetime.timedelta(days=1)).date(),
            datetime.time(0, 0),
            tzinfo=SGT,
        )
        start = sgt_midnight_tomorrow
        end = utc_time.after(self.now, days=300)
        tt_a = self._create_timetable("a", start, end)
        self.assertIsNone(self.timetables.get_current())
        nxt = self.timetables.get_next()
        self.assertEqual(nxt["timetable_id"], tt_a)
        self.assertEqual(nxt["effective_from"], _rfc3339(start))
        # A minute before the start date: still future.
        before = start - datetime.timedelta(minutes=1)
        self.assertIsNone(self.timetables.get_current(at=before))
        # On the start date: current. (The pending switch as of NOW is
        # still this version — get_next has no as-of parameter.)
        on_day = start + datetime.timedelta(hours=1)
        self.assertEqual(self.timetables.get_current(at=on_day), tt_a)

    def test_unparseable_rows_are_skipped(self):
        """A row without a usable window cannot be current or next and
        must not break the derived state (#1222 leniency)."""
        from campus.api.resources.timetable import timetable_collection

        timetable_collection.insert_one({
            "id": "uid-timetable-junkrow",
            "filename": "",
        })
        start, end = self._window_around_now(days=30)
        tt_a = self._create_timetable("a", start, end)
        self.assertEqual(self.timetables.get_current(), tt_a)
        self.assertEqual(self.timetables.pointers_state()["current"], tt_a)

    def test_delete_guard_refuses_derived_current_and_next(self):
        start, end = self._window_around_now(days=30)
        tt_current = self._create_timetable("current", start, end)
        tt_next = self._create_timetable(
            "next",
            utc_time.after(self.now, days=60),
            utc_time.after(self.now, days=300),
        )
        with self.assertRaises(api_errors.ConflictError):
            self.timetables.delete(tt_current)
        with self.assertRaises(api_errors.ConflictError):
            self.timetables.delete(tt_next)
