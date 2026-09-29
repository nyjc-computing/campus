"""Unit tests for Timetable models."""

import unittest

from campus.common.errors import ValidationError
from campus.common import schema
from campus.model import Timetable, TimetableMetadata


class TestTimetableMetadata(unittest.TestCase):
    """Tests for TimetableMetadata construction and validation."""

    def test_valid_metadata(self):
        """Constructing TimetableMetadata with a valid filename succeeds."""
        meta = TimetableMetadata(
            filename="2026.xml",
            start_date="2026-01-01T00:00:00Z",
            end_date="2026-12-31T00:00:00Z"
        )
        self.assertEqual(meta.filename, "2026.xml")

    def test_empty_filename_rejected(self):
        """Empty filename raises ValidationError with a filename field error.

        Regression test for #600: timetable.new() used to accept and
        store a timetable with an empty filename.
        """
        with self.assertRaises(ValidationError) as ctx:
            TimetableMetadata(
                filename="",
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-12-31T00:00:00Z"
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.error_code, "VALIDATION_FAILED")
        fields = [e["field"] for e in ctx.exception.field_errors]
        self.assertIn("filename", fields)


class TestTimetable(unittest.TestCase):
    """Tests for the Timetable API model."""

    def test_timetable_inherits_filename_validation(self):
        """Timetable rejects an empty filename like its metadata base."""
        with self.assertRaises(ValidationError):
            Timetable(
                filename=schema.String(""),
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-12-31T00:00:00Z",
                entries=[]
            )

    def test_timetable_valid(self):
        """Timetable with a valid filename and entries constructs."""
        tt = Timetable(
            filename="2026.xml",
            start_date="2026-01-01T00:00:00Z",
            end_date="2026-12-31T00:00:00Z",
            entries=[]
        )
        self.assertEqual(tt.filename, "2026.xml")
        self.assertEqual(tt.entries, [])


if __name__ == '__main__':
    unittest.main()
