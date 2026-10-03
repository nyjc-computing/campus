"""Unit tests for the circles resource @meta handling.

Regression coverage for #501/#760: the @meta bootstrap record lives in
the circles collection but is not itself a circle, so CirclesResource.list()
must exclude it instead of failing to hydrate it (the root cause of the
dev GET /circles/ 500).
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


if __name__ == "__main__":
    unittest.main()
