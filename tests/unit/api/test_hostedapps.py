"""Unit tests for the hostedapps resource (campus-classroom#81).

Hosted apps are single-file HTML apps published to Campus app hosting:
the slug is the app's stable address (immutable, unique — referenced by
published document questions), while the bytes are CONTENT-ADDRESSED —
stored under the sha256 of the content, so replacing an app under the
same slug re-points it at the new hash and the old blob is dropped once
nothing references it. Records are campus.model.HostedApp storage dicts;
the model validates slug, content-hash shape, and status.
"""

import hashlib
import unittest

from campus.common import env
from campus.common.errors import api_errors

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")

import campus.storage.errors as campus_storage  # noqa: E402
from campus.api.resources.hostedapps import (  # noqa: E402
    HostedAppResource,
    HostedAppsResource,
    get_hostedapps_bucket,
    hostedapps_storage,
)


def _content(marker: str) -> bytes:
    return (
        f"<!DOCTYPE html><html><head><title>{marker}</title></head>"
        f"<body>{marker}</body></html>"
    ).encode("utf-8")


class TestValidateSlug(unittest.TestCase):
    """Hosted-app slugs are single-segment lowercase addresses."""

    def test_valid_slugs_pass_through(self):
        from campus.api.resources.hostedapps import validate_slug
        for slug in ("breaks", "quest-dom", "a.b_c-1", "2"):
            self.assertEqual(validate_slug(slug), slug)

    def test_invalid_slugs_rejected(self):
        from campus.api.resources.hostedapps import validate_slug
        for slug in ("", "Quest", "has space", "has/slash", "a" * 513):
            with self.assertRaises(api_errors.InvalidRequestError, msg=slug):
                validate_slug(slug)


class TestHostedAppsResource(unittest.TestCase):
    """Upsert/list/content semantics on the memory storage backend."""

    def setUp(self):
        self.resource = HostedAppsResource()
        # Fresh store per test: the module-level collection is the
        # memory backend's store; clear it between tests.
        hostedapps_storage.delete_matching({})

    def test_new_creates_content_addressed_record(self):
        data = _content("one")
        record = self.resource.new(
            "one", data, "text/html", "uid-client-1", "uid-user-1",
            name="App One",
        )
        self.assertEqual(record["slug"], "one")
        self.assertEqual(record["name"], "App One")
        self.assertEqual(
            record["content_hash"],
            hashlib.sha256(data).hexdigest(),
        )
        self.assertEqual(record["status"], "published")
        self.assertEqual(record["uploaded_by_user_id"], "uid-user-1")

    def test_duplicate_slug_conflicts(self):
        self.resource.new("one", _content("one"), "text/html", "uid-client-1")
        with self.assertRaises(api_errors.ConflictError):
            self.resource.new(
                "one", _content("other"), "text/html", "uid-client-1")

    def test_content_round_trip(self):
        data = _content("roundtrip")
        self.resource.new("rt", data, "text/html", "uid-client-1")
        content, record = (
            HostedAppResource.get_content_by_slug("rt")
        )
        self.assertEqual(content, data)
        self.assertEqual(record["slug"], "rt")

    def test_replace_repoints_hash_and_drops_old_blob(self):
        self.resource.new("two", _content("v1"), "text/html", "uid-client-1")
        old_hash = (
            HostedAppResource.get_by_slug("two")
        )["content_hash"]

        record, created = (
            HostedAppResource.update_content_by_slug(
                "two", _content("v2"), "text/html", "uid-client-1",
                user_id="uid-user-2",
            )
        )
        self.assertFalse(created)
        new_hash = hashlib.sha256(_content("v2")).hexdigest()
        self.assertEqual(record["content_hash"], new_hash)
        # Old blob dropped (no other record referenced it).
        with self.assertRaises(campus_storage.NotFoundError):
            get_hostedapps_bucket().get(old_hash)
        content, _ = (
            HostedAppResource.get_content_by_slug("two")
        )
        self.assertEqual(content, _content("v2"))

    def test_replace_keeps_name_when_name_absent(self):
        self.resource.new(
            "three", _content("v1"), "text/html", "uid-client-1",
            name="Kept Name",
        )
        record, _ = (
            HostedAppResource.update_content_by_slug(
                "three", _content("v2"), "text/html", "uid-client-1",
            )
        )
        self.assertEqual(record["name"], "Kept Name")

    def test_shared_content_survives_single_delete(self):
        """Identical content under two slugs shares one hash — deleting
        one app must leave the other's bytes reachable."""
        data = _content("shared")
        self.resource.new("alpha", data, "text/html", "uid-client-1")
        self.resource.new("beta", data, "text/html", "uid-client-1")

        HostedAppResource.delete_by_slug("alpha")
        content, _ = (
            HostedAppResource.get_content_by_slug("beta")
        )
        self.assertEqual(content, data)

        HostedAppResource.delete_by_slug("beta")
        with self.assertRaises(api_errors.NotFoundError):
            HostedAppResource.get_content_by_slug("beta")

    def test_list_prefix(self):
        self.resource.new("app-one", _content("1"), "text/html", "uid-client-1")
        self.resource.new("app-two", _content("2"), "text/html", "uid-client-1")
        self.resource.new("other", _content("3"), "text/html", "uid-client-1")
        slugs = [r["slug"] for r in self.resource.list(prefix="app-")]
        self.assertEqual(slugs, ["app-one", "app-two"])

    def test_missing_content_answers_not_found(self):
        with self.assertRaises(api_errors.NotFoundError):
            HostedAppResource.get_content_by_slug("ghost")
        with self.assertRaises(api_errors.NotFoundError):
            HostedAppResource.get_by_slug("ghost")

    def test_invalid_slug_fails_at_resource_boundary(self):
        """The resource validates slugs before the model sees them —
        the API boundary raises the api error, not the model's
        ValueError (model-level cases live in campus-model tests)."""
        with self.assertRaises(api_errors.InvalidRequestError):
            self.resource.new("Bad Slug", _content("x"), "text/html", "c")


if __name__ == "__main__":
    unittest.main()
