"""Unit tests for the venue resource semantics (campus#1099).

Venues are documents-backed CRUD with a deliberately fluid schema:
freeform `metadata` + freeform markdown `notes`. PATCH replaces given
fields and leaves absent fields alone; `notes=None` clears. Tests
drive the resource directly (ungated, like subjcombi's).
"""

import unittest

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestVenueCrud(unittest.TestCase):
    """Create/get/list/update/delete over the documents backend."""

    def setUp(self):
        from campus.api.resources import venue
        self.venue = venue

    def test_new_get_round_trip(self):
        created = self.venue.new(
            metadata={"name": "B1-01", "capacity": 40},
            notes="Projector **broken**.",
        )
        self.assertTrue(created.id.startswith("uid-venue-"))
        fetched = self.venue.get(created.id)
        self.assertEqual(fetched.id, created.id)
        self.assertEqual(fetched.metadata, {"name": "B1-01", "capacity": 40})
        self.assertEqual(fetched.notes, "Projector **broken**.")
        self.assertIsNone(fetched.updated_at)

    def test_new_defaults_to_empty_metadata(self):
        created = self.venue.new()
        self.assertEqual(created.metadata, {})
        self.assertIsNone(created.notes)
        fetched = self.venue.get(created.id)
        self.assertEqual(fetched.metadata, {})
        self.assertIsNone(fetched.notes)

    def test_get_unknown_raises_not_found(self):
        with self.assertRaises(api_errors.NotFoundError):
            self.venue.get("uid-venue-doesnotexist")

    def test_list_includes_created_venues(self):
        a = self.venue.new(metadata={"name": "Hall"})
        b = self.venue.new(metadata={"name": "Lab"})
        listed = self.venue.list_all()
        ids = {v.id for v in listed}
        self.assertIn(a.id, ids)
        self.assertIn(b.id, ids)


class TestVenuePatch(unittest.TestCase):
    """PATCH semantics: given fields replace, absent fields stay."""

    def setUp(self):
        from campus.api.resources import venue
        self.venue = venue
        self.created = self.venue.new(
            metadata={"name": "B1-01", "capacity": 40},
            notes="Original note.",
        )

    def test_metadata_replaces_whole_dict(self):
        updated = self.venue.update(
            self.created.id, metadata={"name": "B1-02"}
        )
        self.assertEqual(updated.metadata, {"name": "B1-02"})
        # notes untouched when only metadata given
        self.assertEqual(updated.notes, "Original note.")
        self.assertIsNotNone(updated.updated_at)

    def test_notes_set_and_clear(self):
        updated = self.venue.update(self.created.id, notes="New note.")
        self.assertEqual(updated.notes, "New note.")
        cleared = self.venue.update(self.created.id, notes=None)
        self.assertIsNone(cleared.notes)
        # metadata untouched by both
        self.assertEqual(
            cleared.metadata, {"name": "B1-01", "capacity": 40}
        )

    def test_no_fields_is_invalid_request(self):
        with self.assertRaises(api_errors.InvalidRequestError):
            self.venue.update(self.created.id)

    def test_update_unknown_raises_not_found(self):
        with self.assertRaises(api_errors.NotFoundError):
            self.venue.update("uid-venue-doesnotexist", notes="x")

    def test_delete_removes_and_404s(self):
        self.venue.delete(self.created.id)
        with self.assertRaises(api_errors.NotFoundError):
            self.venue.get(self.created.id)
        with self.assertRaises(api_errors.NotFoundError):
            self.venue.delete(self.created.id)


if __name__ == "__main__":
    unittest.main()
