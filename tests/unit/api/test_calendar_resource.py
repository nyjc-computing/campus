"""Unit tests for the school-calendar resource.

Date-keyed rows (campus.model.CalendarDay, the ISO date IS the id):
upsert creates or updates; writes validate the date format and the
TT-day vocabulary; range reads filter inclusively; the bulk upsert
validates everything before writing anything. Tests drive the resource
directly; each test uses fresh dates so test storage persisting across
tests in the process cannot collide.
"""

import unittest
import uuid

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestCalendarResource(unittest.TestCase):
    """Upsert, validation, range reads, bulk seed, delete."""

    def setUp(self):
        from campus.api.resources.calendar import CalendarResource

        CalendarResource.init_storage()
        self.calendar = CalendarResource()
        self.tag = uuid.uuid4().hex[:6]

    def _date(self, month: int, day: int) -> str:
        # 2027 dates: the calendar is empty until a test writes it, and
        # each method uses its own month band so process-persistent test
        # storage cannot collide between tests.
        return f"2027-{month:02d}-{day:02d}"

    def test_upsert_creates_then_updates(self):
        date_key = self._date(1, 11)
        record = self.calendar.upsert_date(
            date_key, j1_code="Mon A", j2_code="Mon A", term_week="T1 W1"
        )
        self.assertEqual(record["id"], date_key)
        self.assertEqual(record["j1_code"], "Mon A")
        self.assertIsNotNone(record["created_at"])

        updated = self.calendar.upsert_date(date_key, j1_code="Mon B", j2_code="Free")
        self.assertEqual(updated["j1_code"], "Mon B")
        self.assertEqual(updated["j2_code"], "Free")
        # The update must not disturb the original created_at.
        self.assertEqual(updated["created_at"], record["created_at"])

    def test_malformed_dates_are_refused(self):
        for raw in ("2027-1-11", "20270111", "2027-02-30", "not-a-date", ""):
            with self.subTest(raw=raw), self.assertRaises(api_errors.InvalidRequestError):
                self.calendar.get_date(raw)

    def test_unknown_day_codes_are_refused(self):
        with self.assertRaises(api_errors.InvalidRequestError):
            self.calendar.upsert_date(self._date(3, 1), j1_code="Sunday X")
        with self.assertRaises(api_errors.InvalidRequestError):
            self.calendar.upsert_date(self._date(3, 1), j2_code="free")

    def test_range_reads_filter_inclusively_and_sort(self):
        for month, day in ((1, 11), (1, 12), (1, 13)):
            self.calendar.upsert_date(
                self._date(month, day), j1_code="Mon A", j2_code="Mon A"
            )
        days = self.calendar.get_range(self._date(1, 12), self._date(1, 13))
        self.assertEqual(
            [record["id"] for record in days],
            [self._date(1, 12), self._date(1, 13)],
        )
        self.assertEqual(
            [record["id"] for record in self.calendar.get_range(None, None)],
            sorted(record["id"] for record in self.calendar.get_range(None, None)),
        )

    def test_bulk_upsert_validates_before_writing(self):
        rows = [
            {"date": self._date(2, 3), "j1_code": "Wed A", "j2_code": "Wed A",
             "term_week": "T2 W1"},
            {"date": self._date(2, 4), "j1_code": "Thu A", "j2_code": "Thu A",
             "term_week": "T2 W1"},
        ]
        written = self.calendar.upsert_many(rows)
        self.assertEqual(len(written), 2)
        self.assertIsNotNone(self.calendar.get_date(self._date(2, 3)))

        # A bad row anywhere refuses the WHOLE payload: the good row
        # below (already stored) is left untouched, the new row is not
        # written.
        with self.assertRaises(api_errors.InvalidRequestError):
            self.calendar.upsert_many([
                {"date": self._date(2, 5), "j1_code": "Fri A", "j2_code": "Fri A"},
                {"date": self._date(2, 8), "j1_code": "Saturday Z"},
            ])
        self.assertIsNone(self.calendar.get_date(self._date(2, 5)))

    def test_bulk_upsert_refuses_duplicate_dates(self):
        with self.assertRaises(api_errors.InvalidRequestError):
            self.calendar.upsert_many([
                {"date": self._date(4, 1), "j1_code": "Thu B"},
                {"id": self._date(4, 1), "j2_code": "Thu B"},
            ])

    def test_delete_removes_the_row(self):
        date_key = self._date(9, 13)
        self.calendar.upsert_date(date_key, j1_code="Mon B", j2_code="Mon B")
        self.calendar.delete_date(date_key)
        self.assertIsNone(self.calendar.get_date(date_key))
        with self.assertRaises(api_errors.NotFoundError):
            self.calendar.delete_date(date_key)
