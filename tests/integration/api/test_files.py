"""Integration tests for campus.api files routes.

Exercises the by-slug (consumer-facing, terminal) and id-based
(management) route families end-to-end against the local test
backends: document collection for records, LocalBucket for content.
"""

import uuid

from campus.common import schema
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers
from tests.integration.base import IntegrationTestCase


def _unique_slug(name: str) -> str:
    """A slug unique to this test run; bucket objects survive record wipes."""
    return f"tests/{uuid.uuid4().hex[:8]}/{name}"


class TestFilesIntegration(IntegrationTestCase):
    """Integration tests for the files resource in campus.api."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()

        import flask
        api_app = cls.service_manager.apps_app
        if not isinstance(api_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = api_app
        cls.user_id = schema.UserID("test.user@campus.test")

    def setUp(self):
        """Set up test environment before each test."""
        super().setUp()

        # Create test user token for bearer auth
        # Re-create before each test since setUp() resets storage
        self.token = create_test_token(self.user_id)
        self.auth_headers = get_bearer_auth_headers(self.token)

    def _put_slug(self, slug: str, body: bytes, content_type: str = "application/pdf",
                  name: str | None = None):
        """PUT a file by slug; returns the test client response."""
        url = f"/api/v1/files/by-slug/{slug}"
        if name:
            url += f"?name={name}"
        return self.client.put(
            url,
            data=body,
            headers={**self.auth_headers, "Content-Type": content_type},
        )

    def test_put_by_slug_creates(self):
        """PUT by-slug creates a file and returns its resource."""
        slug = _unique_slug("breaks.pdf")
        response = self._put_slug(slug, b"%PDF-breaks", name="Break+times")
        assert response.status_code == 201, response.get_data(as_text=True)
        record = response.get_json()
        assert record["slug"] == slug
        assert record["name"] == "Break times"
        assert record["size"] == len(b"%PDF-breaks")
        assert record["content_type"] == "application/pdf"
        assert record["id"].startswith("uid-file-")
        assert record["uploaded_by_user_id"] == self.user_id
        assert record["created_at"] == record["updated_at"]

    def test_put_by_slug_replaces_content(self):
        """Second PUT to the same slug replaces content, returns 200."""
        slug = _unique_slug("breaks.pdf")
        first = self._put_slug(slug, b"version-1")
        assert first.status_code == 201
        file_id = first.get_json()["id"]

        second = self._put_slug(slug, b"version-2-longer", content_type="text/plain")
        assert second.status_code == 200
        record = second.get_json()
        assert record["id"] == file_id  # slug URL stays stable
        assert record["size"] == len(b"version-2-longer")
        assert record["content_type"] == "text/plain"
        assert record["updated_at"] >= record["created_at"]

        served = self.client.get(f"/api/v1/files/by-slug/{slug}",
                                 headers=self.auth_headers)
        assert served.status_code == 200
        assert served.data == b"version-2-longer"
        # Flask appends a charset to text/* mimetypes on the way out
        assert served.content_type.startswith("text/plain")

    def test_get_content_by_slug_serves_bytes(self):
        """GET by-slug serves the raw bytes with stored type and caching."""
        slug = _unique_slug("handbook.pdf")
        self._put_slug(slug, b"%PDF-handbook")
        response = self.client.get(f"/api/v1/files/by-slug/{slug}",
                                   headers=self.auth_headers)
        assert response.status_code == 200
        assert response.data == b"%PDF-handbook"
        assert response.content_type == "application/pdf"
        assert response.headers["ETag"]
        assert "max-age=60" in response.headers["Cache-Control"]

    def test_get_content_by_slug_accepts_trailing_slash(self):
        """A trailing slash on the by-slug URL is normalized away."""
        slug = _unique_slug("breaks.pdf")
        self._put_slug(slug, b"payload")
        response = self.client.get(f"/api/v1/files/by-slug/{slug}/",
                                   headers=self.auth_headers)
        assert response.status_code == 200
        assert response.data == b"payload"

    def test_get_meta_by_slug(self):
        """?meta=1 returns the file resource instead of the bytes."""
        slug = _unique_slug("breaks.pdf")
        created = self._put_slug(slug, b"12345")
        file_id = created.get_json()["id"]
        response = self.client.get(f"/api/v1/files/by-slug/{slug}?meta=1",
                                   headers=self.auth_headers)
        assert response.status_code == 200
        record = response.get_json()
        assert record["id"] == file_id
        assert record["slug"] == slug
        assert record["size"] == 5

    def test_slash_slug_containing_content_segment(self):
        """A slug with a 'content' segment works: by-slug routes are terminal."""
        slug = _unique_slug("content")
        self._put_slug(slug, b"nested")
        response = self.client.get(f"/api/v1/files/by-slug/{slug}",
                                   headers=self.auth_headers)
        assert response.status_code == 200
        assert response.data == b"nested"

    def test_get_by_slug_missing(self):
        """GET by-slug for an unknown slug is a 404."""
        response = self.client.get("/api/v1/files/by-slug/tests/never/here.pdf",
                                   headers=self.auth_headers)
        assert response.status_code == 404

    def test_put_invalid_slug_rejected(self):
        """PUT with a slug violating the grammar is a 400.

        Grammar cases that Werkzeug would normalize at the URL layer
        (dot segments, doubled slashes, leading slash) are covered
        directly by the validate_slug unit tests.
        """
        for slug in ("bad slug", "a/../b", "sl~ug"):
            response = self._put_slug(slug, b"x")
            assert response.status_code == 400, slug

    def test_put_reserved_slug_rejected(self):
        """PUT to the reserved slug 'content' is a 400."""
        response = self._put_slug("content", b"x")
        assert response.status_code == 400

    def test_put_requires_authentication(self):
        """Unauthenticated PUTs are rejected by the api authenticator."""
        response = self.client.put(
            "/api/v1/files/by-slug/tests/unauth.pdf",
            data=b"x",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 401

    def test_get_by_id_and_content(self):
        """GET /{id}/ returns metadata; GET /{id}/content/ the bytes."""
        slug = _unique_slug("breaks.pdf")
        created = self._put_slug(slug, b"%PDF-by-id")
        file_id = created.get_json()["id"]

        meta = self.client.get(f"/api/v1/files/{file_id}/",
                               headers=self.auth_headers)
        assert meta.status_code == 200
        assert meta.get_json()["slug"] == slug

        content = self.client.get(f"/api/v1/files/{file_id}/content/",
                                  headers=self.auth_headers)
        assert content.status_code == 200
        assert content.data == b"%PDF-by-id"
        assert content.content_type == "application/pdf"

    def test_put_content_by_id_replaces(self):
        """PUT /{id}/content/ replaces content; missing id is a 404."""
        slug = _unique_slug("breaks.pdf")
        created = self._put_slug(slug, b"old")
        file_id = created.get_json()["id"]

        response = self.client.put(
            f"/api/v1/files/{file_id}/content/",
            data=b"new-by-id",
            headers={**self.auth_headers, "Content-Type": "text/plain"},
        )
        assert response.status_code == 200
        record = response.get_json()
        assert record["size"] == len(b"new-by-id")
        assert record["content_type"] == "text/plain"

        missing = self.client.put(
            "/api/v1/files/uid-file-zzzzzzzz/content/",
            data=b"x",
            headers={**self.auth_headers, "Content-Type": "text/plain"},
        )
        assert missing.status_code == 404

    def test_delete_by_id_removes_record_and_content(self):
        """DELETE /{id}/ removes the file from both routes."""
        slug = _unique_slug("breaks.pdf")
        created = self._put_slug(slug, b"to-delete")
        file_id = created.get_json()["id"]

        response = self.client.delete(f"/api/v1/files/{file_id}/",
                                      headers=self.auth_headers)
        assert response.status_code == 200
        assert self.client.get(f"/api/v1/files/{file_id}/",
                               headers=self.auth_headers).status_code == 404
        assert self.client.get(f"/api/v1/files/by-slug/{slug}",
                               headers=self.auth_headers).status_code == 404

    def test_delete_by_slug(self):
        """DELETE by-slug removes the file; unknown slug is a 404."""
        slug = _unique_slug("breaks.pdf")
        self._put_slug(slug, b"to-delete")
        response = self.client.delete(f"/api/v1/files/by-slug/{slug}",
                                      headers=self.auth_headers)
        assert response.status_code == 200
        assert self.client.get(f"/api/v1/files/by-slug/{slug}",
                               headers=self.auth_headers).status_code == 404

        missing = self.client.delete("/api/v1/files/by-slug/tests/never/here.pdf",
                                     headers=self.auth_headers)
        assert missing.status_code == 404

    def test_list_with_prefix_filter(self):
        """GET /files/ lists records; ?prefix= filters by slug prefix."""
        timetable_slug = _unique_slug("a.pdf")
        other_slug = _unique_slug("b.pdf").replace("tests/", "other/")
        self._put_slug(timetable_slug, b"1")
        self._put_slug(other_slug, b"2")

        all_files = self.client.get("/api/v1/files/", headers=self.auth_headers)
        assert all_files.status_code == 200
        slugs = [f["slug"] for f in all_files.get_json()["data"]]
        assert timetable_slug in slugs
        assert other_slug in slugs

        filtered = self.client.get("/api/v1/files/?prefix=other/",
                                   headers=self.auth_headers)
        assert filtered.status_code == 200
        assert [f["slug"] for f in filtered.get_json()["data"]] == [other_slug]
