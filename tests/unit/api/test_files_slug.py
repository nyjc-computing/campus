"""Unit tests for the files resource slug grammar and record projection.

The slug grammar underpins the by-slug file routes: slugs are
slash-separated path labels captured greedily by a <path:slug>
converter, so the grammar (not the router) is what keeps slugs
unambiguous against the id-based content route — in particular the
reserved slug 'content', which would otherwise match both
/files/by-slug/content/ and /files/<file_id>/content/.
"""

import unittest

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


class TestValidateSlug(unittest.TestCase):
    """validate_slug() accepts path-like slugs and rejects ambiguity."""

    def test_valid_slugs_pass_through(self):
        from campus.api.resources.files import validate_slug
        for slug in (
            "breaks.pdf",
            "timetable/specials/breaks",
            "a/content",  # slash slug containing the reserved segment
            "A.b_c-1/2",
        ):
            self.assertEqual(validate_slug(slug), slug)

    def test_empty_or_oversized_rejected(self):
        from campus.api.resources.files import validate_slug
        with self.assertRaises(api_errors.InvalidRequestError):
            validate_slug("")
        with self.assertRaises(api_errors.InvalidRequestError):
            validate_slug("a" * 513)

    def test_invalid_characters_rejected(self):
        from campus.api.resources.files import validate_slug
        for slug in ("bad slug", "slug?", "slug#fragment", "sl~ug"):
            with self.assertRaises(api_errors.InvalidRequestError):
                validate_slug(slug)

    def test_empty_segments_and_dot_segments_rejected(self):
        from campus.api.resources.files import validate_slug
        for slug in ("/leading", "trailing/", "double//slash", ".", "a/../b", "a/./b"):
            with self.assertRaises(api_errors.InvalidRequestError):
                validate_slug(slug)

    def test_reserved_slugs_rejected(self):
        from campus.api.resources.files import validate_slug
        with self.assertRaises(api_errors.InvalidRequestError):
            validate_slug("content")


class TestRecordProjection(unittest.TestCase):
    """to_resource() projects stored records to their API shape."""

    def test_to_resource_keeps_resource_fields(self):
        from campus.api.resources.files import FileResource
        record = {
            "id": "uid-file-abc",
            "slug": "timetable/breaks",
            "name": "breaks.pdf",
            "size": 3,
            "content_type": "application/pdf",
            "created_at": "2026-10-29T00:00:00Z",
            "updated_at": "2026-10-29T00:00:00Z",
            "uploaded_by_client_id": "uid-client-x",
            "uploaded_by_user_id": None,
        }
        resource = FileResource.to_resource(record)
        self.assertEqual(resource, record)


if __name__ == "__main__":
    unittest.main()
