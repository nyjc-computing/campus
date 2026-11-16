"""Integration tests for campus.api timetable attachments.

The per-version attachment surface (timetable-v2 Manage Timetables):
files-backed records under the ``timetables/<id>/attachments/`` slug
namespace, admin-gated writes, and the namespace guard on the generic
files surface that keeps the binding unforgeable.
"""

import uuid

from campus.common import schema
from tests.fixtures.circles import grant_circle_admin
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers
from tests.integration.base import IntegrationTestCase


def _unique_slug(name: str) -> str:
    """A slug unique to this test run; bucket objects survive record wipes."""
    return f"tests/{uuid.uuid4().hex[:8]}/{name}"


class TestTimetableAttachments(IntegrationTestCase):
    """Integration tests for /timetable/<id>/attachments."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.service_manager.apps_app
        cls.user_id = schema.UserID("tt-attach.admin@campus.test")
        cls.outsider_id = schema.UserID("tt-attach.student@campus.test")

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        grant_circle_admin(str(self.user_id), "timetable")
        self.timetable_id = self._create_timetable()

    def _headers(self, user_id=None):
        # Fresh token per request: minting a token invalidates the
        # previous credential record.
        uid = user_id or self.user_id
        return get_bearer_auth_headers(create_test_token(uid))

    def _create_timetable(self, filename: str | None = None) -> str:
        filename = filename or f"attach-{uuid.uuid4().hex[:6]}.xml"
        response = self.client.post(
            "/api/v1/timetable/",
            json={
                "metadata": {
                    "filename": filename,
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-12-31T00:00:00Z",
                    "label": "Attachment test",
                },
                "data": {"lessongroups": []},
            },
            headers=self._headers(),
        )
        assert response.status_code == 200, response.get_json()
        return response.get_json()["data"]["id"]

    def _upload(self, filename="breaks.pdf", body=b"%PDF-1.4 attachment", user_id=None):
        return self.client.post(
            f"/api/v1/timetable/{self.timetable_id}/attachments/"
            f"?filename={filename}",
            data=body,
            headers={**self._headers(user_id), "Content-Type": "application/pdf"},
        )

    def test_create_metadata_carries_label(self):
        response = self.client.get(
            f"/api/v1/timetable/{self.timetable_id}/metadata",
            headers=self._headers(),
        )
        assert response.status_code == 200
        assert response.get_json()["label"] == "Attachment test"

    def test_upload_creates_attachment_record(self):
        response = self._upload()
        assert response.status_code == 201, response.get_data(as_text=True)
        record = response.get_json()
        assert record["id"].startswith("uid-file-")
        assert record["name"] == "breaks.pdf"
        assert record["content_type"] == "application/pdf"
        assert record["size"] == len(b"%PDF-1.4 attachment")
        assert record["slug"].startswith(
            f"timetables/{self.timetable_id}/attachments/"
        )
        assert record["uploaded_by_user_id"] == str(self.user_id)

    def test_upload_requires_filename_and_body(self):
        no_name = self.client.post(
            f"/api/v1/timetable/{self.timetable_id}/attachments/",
            data=b"%PDF-1.4",
            headers={**self._headers(), "Content-Type": "application/pdf"},
        )
        assert no_name.status_code == 400
        no_body = self.client.post(
            f"/api/v1/timetable/{self.timetable_id}/attachments/?filename=x.pdf",
            headers={**self._headers(), "Content-Type": "application/pdf"},
        )
        assert no_body.status_code == 400

    def test_upload_unknown_timetable_is_404(self):
        response = self.client.post(
            "/api/v1/timetable/uid-timetable-gone/attachments/?filename=x.pdf",
            data=b"x",
            headers={**self._headers(), "Content-Type": "application/pdf"},
        )
        assert response.status_code == 404

    def test_list_returns_records_newest_first(self):
        first = self._upload(filename="a.pdf")
        second = self._upload(filename="b.pdf")
        assert first.status_code == 201 and second.status_code == 201
        listing = self.client.get(
            f"/api/v1/timetable/{self.timetable_id}/attachments/",
            headers=self._headers(),
        )
        assert listing.status_code == 200
        records = listing.get_json()["data"]
        names = [record["name"] for record in records]
        assert names == ["b.pdf", "a.pdf"]

    def test_content_serves_stored_bytes(self):
        record = self._upload().get_json()
        response = self.client.get(
            f"/api/v1/timetable/{self.timetable_id}/attachments/{record['id']}/content/",
            headers=self._headers(),
        )
        assert response.status_code == 200
        assert response.data == b"%PDF-1.4 attachment"
        assert response.content_type == "application/pdf"

    def test_delete_removes_record_and_content(self):
        record = self._upload().get_json()
        removed = self.client.delete(
            f"/api/v1/timetable/{self.timetable_id}/attachments/{record['id']}/",
            headers=self._headers(),
        )
        assert removed.status_code == 200
        gone = self.client.get(
            f"/api/v1/timetable/{self.timetable_id}/attachments/{record['id']}/content/",
            headers=self._headers(),
        )
        assert gone.status_code == 404

    def test_attachment_ids_do_not_cross_versions(self):
        other_id = self._create_timetable(filename="attach-other.xml")
        record = self._upload().get_json()
        alien = self.client.delete(
            f"/api/v1/timetable/{other_id}/attachments/{record['id']}/",
            headers=self._headers(),
        )
        assert alien.status_code == 404
        alien_content = self.client.get(
            f"/api/v1/timetable/{other_id}/attachments/{record['id']}/content/",
            headers=self._headers(),
        )
        assert alien_content.status_code == 404

    def test_writes_require_timetable_admin(self):
        # An authenticated non-member gets the same 403 the timetable
        # mutation routes give — attachments are timetable data.
        denied = self._upload(user_id=self.outsider_id)
        assert denied.status_code == 403
        record = self._upload().get_json()
        denied_delete = self.client.delete(
            f"/api/v1/timetable/{self.timetable_id}/attachments/{record['id']}/",
            headers=self._headers(self.outsider_id),
        )
        assert denied_delete.status_code == 403

    def test_timetable_delete_cascades_attachments(self):
        record = self._upload().get_json()
        removed = self.client.delete(
            f"/api/v1/timetable/{self.timetable_id}/",
            headers=self._headers(),
        )
        assert removed.status_code == 200, removed.get_json()
        gone = self.client.get(
            f"/api/v1/files/{record['id']}/",
            headers=self._headers(),
        )
        assert gone.status_code == 404


class TestAttachmentNamespaceGuard(IntegrationTestCase):
    """Writes under the ``timetables/`` slug namespace are gated even
    through the GENERIC files surface — a plain-authenticated caller
    cannot forge or deface an attachment by addressing its slug or id.
    Reads stay open."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.service_manager.apps_app
        cls.admin_id = schema.UserID("ns.admin@campus.test")
        cls.user_id = schema.UserID("ns.plain@campus.test")

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        grant_circle_admin(str(self.admin_id), "timetable")

    def _headers(self, user_id):
        return get_bearer_auth_headers(create_test_token(user_id))

    def _upload_as_admin(self, slug):
        return self.client.put(
            f"/api/v1/files/by-slug/{slug}",
            data=b"%PDF-1.4 admin",
            headers={**self._headers(self.admin_id), "Content-Type": "application/pdf"},
        )

    def test_namespace_put_denies_non_admin(self):
        slug = f"timetables/uid-timetable-{uuid.uuid4().hex[:6]}/attachments/evil.pdf"
        response = self.client.put(
            f"/api/v1/files/by-slug/{slug}",
            data=b"evil",
            headers={**self._headers(self.user_id), "Content-Type": "application/pdf"},
        )
        assert response.status_code == 403

    def test_namespace_put_allows_admin(self):
        slug = f"timetables/uid-timetable-{uuid.uuid4().hex[:6]}/attachments/doc.pdf"
        response = self._upload_as_admin(slug)
        assert response.status_code == 201

    def test_namespace_delete_by_slug_denies_non_admin(self):
        slug = f"timetables/uid-timetable-{uuid.uuid4().hex[:6]}/attachments/doc.pdf"
        assert self._upload_as_admin(slug).status_code == 201
        denied = self.client.delete(
            f"/api/v1/files/by-slug/{slug}",
            headers=self._headers(self.user_id),
        )
        assert denied.status_code == 403

    def test_id_addressed_write_and_delete_denied_for_namespace_files(self):
        slug = f"timetables/uid-timetable-{uuid.uuid4().hex[:6]}/attachments/doc.pdf"
        record = self._upload_as_admin(slug).get_json()
        denied_put = self.client.put(
            f"/api/v1/files/{record['id']}/content/",
            data=b"defaced",
            headers={**self._headers(self.user_id), "Content-Type": "application/pdf"},
        )
        assert denied_put.status_code == 403
        denied_delete = self.client.delete(
            f"/api/v1/files/{record['id']}/",
            headers=self._headers(self.user_id),
        )
        assert denied_delete.status_code == 403
        # Reads stay open, like every other file record.
        read = self.client.get(
            f"/api/v1/files/{record['id']}/",
            headers=self._headers(self.user_id),
        )
        assert read.status_code == 200

    def test_outside_namespace_writes_stay_open(self):
        # The guard is scoped to the attachments namespace; the wider
        # files surface keeps its authentication-only behavior.
        response = self.client.put(
            f"/api/v1/files/by-slug/{_unique_slug('notes.txt')}",
            data=b"hello",
            headers={**self._headers(self.user_id), "Content-Type": "text/plain"},
        )
        assert response.status_code == 201
