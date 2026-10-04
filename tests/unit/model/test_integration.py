"""Unit tests for the Integration registry model (#688).

The registry endpoint publishes public catalog metadata only;
from_resource()/to_resource() mirror the endpoint response shape.
"""

import unittest

from campus.model import integration


def _make_resource() -> dict:
    return {
        "provider": "google.classroom",
        "slug": "classroom",
        "base_provider": "google",
        "title": "Google Classroom",
        "description": "Connect Google Classroom for coursework tooling.",
        "scopes": ["classroom.rosters"],
        "connectable": True,
        "authorize_path": "/auth/v1/google/classroom/authorize",
    }


class TestIntegrationResource(unittest.TestCase):
    """from_resource()/to_resource() round-trip the registry shape."""

    def test_from_resource(self):
        integ = integration.Integration.from_resource(_make_resource())
        self.assertEqual(integ.provider, "google.classroom")
        self.assertEqual(integ.slug, "classroom")
        self.assertEqual(integ.base_provider, "google")
        self.assertEqual(integ.title, "Google Classroom")
        self.assertEqual(integ.scopes, ["classroom.rosters"])
        self.assertTrue(integ.connectable)
        self.assertEqual(
            integ.authorize_path, "/auth/v1/google/classroom/authorize"
        )

    def test_resource_roundtrip(self):
        integ = integration.Integration.from_resource(_make_resource())
        self.assertEqual(integ.to_resource(), _make_resource())

    def test_from_resource_defaults(self):
        resource = _make_resource()
        for key in ("scopes", "connectable", "authorize_path"):
            resource.pop(key)
        integ = integration.Integration.from_resource(resource)
        self.assertEqual(integ.scopes, [])
        self.assertFalse(integ.connectable)
        self.assertEqual(integ.authorize_path, "")
