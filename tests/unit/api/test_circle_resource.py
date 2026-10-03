"""Unit tests for the circles resource @meta handling.

Regression coverage for #501/#760: the @meta bootstrap record lives in
the circles collection but is not itself a circle, so CirclesResource.list()
must exclude it instead of failing to hydrate it (the root cause of the
dev GET /circles/ 500).

Also covers #501/#761: best-effort circle name uniqueness (create +
rename) and PATCH-on-missing-circle surfacing as ConflictError (the
memory collection backend used to silently no-op update_by_id).
"""

import unittest

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestCirclesResourceList(unittest.TestCase):
    """CirclesResource.list() must exclude the @meta bookkeeping record."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def test_list_excludes_meta_record(self):
        """list() skips the @meta record instead of failing hydration."""
        from campus.api.resources.circle import CirclesResource, circle_storage

        # init_storage seeds the @meta record, root and admin circles —
        # the same state that triggers the dev 500 without the filter.
        CirclesResource.init_storage()

        circles = CirclesResource().list()

        names = [circle.name for circle in circles]
        self.assertIn("nyjc.edu.sg", names)
        self.assertIn("campus-admin", names)
        # Hydrated circles only: every record must carry circle fields
        self.assertTrue(all(circle.tag for circle in circles))

        # The filter excludes but never removes the meta record
        metas = circle_storage.get_matching({"@meta": True})
        self.assertEqual(len(metas), 1)


class TestCirclesResourceNameUniqueness(unittest.TestCase):
    """Circle names are unique (best-effort, exact match) on create + rename."""

    def setUp(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def tearDown(self):
        from campus.api.resources.circle import circle_storage
        circle_storage.delete_matching({})

    def _new_circle(self, name: str, tag: str = "test"):
        from campus.api import resources
        return resources.circle.new(name=name, tag=tag)

    def test_new_rejects_duplicate_name(self):
        """new() raises ConflictError when the name is already taken."""
        from campus.common.errors import api_errors

        self._new_circle("Dup Circle", tag="first")
        with self.assertRaises(api_errors.ConflictError):
            self._new_circle("Dup Circle", tag="second")

    def test_update_rejects_duplicate_name(self):
        """update() raises ConflictError when renaming onto another circle."""
        from campus.common.errors import api_errors

        self._new_circle("First Circle")
        second = self._new_circle("Second Circle")

        from campus.api import resources
        with self.assertRaises(api_errors.ConflictError):
            resources.circle[str(second.id)].update(name="First Circle")

        # The failed rename changed nothing
        unchanged = resources.circle[str(second.id)].get()
        self.assertEqual(unchanged.name, "Second Circle")

    def test_update_own_name_is_noop(self):
        """update() allows renaming a circle to its own name."""
        from campus.api import resources

        circle = self._new_circle("Stable Circle")
        resources.circle[str(circle.id)].update(name="Stable Circle")

        unchanged = resources.circle[str(circle.id)].get()
        self.assertEqual(unchanged.name, "Stable Circle")

    def test_update_missing_circle_raises_conflict(self):
        """update() raises ConflictError (not a silent no-op) for a missing circle."""
        from campus.api import resources
        from campus.common.errors import api_errors

        with self.assertRaises(api_errors.ConflictError):
            resources.circle["no_such_circle"].update(name="New Name")


if __name__ == "__main__":
    unittest.main()
