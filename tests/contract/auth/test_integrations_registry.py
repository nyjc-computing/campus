"""HTTP contract tests for the integrations registry endpoint (#688).

Covers GET /integrations/v1/ (#733 Phase 2): the in-code registry
published read-only for consumers — public metadata, the vault-derived
scope cap and connect availability, and no vault secrets. The
endpoint is public; its values mirror the guards the connect route
enforces (unconfigured stub / empty CONNECT_TARGETS ⇒ not
connectable).
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

GOOGLE_CLASSROOM_CLIENT_ID = "test-registry-classroom-client-id"
CLASSROOM_SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _seed_classroom_vault(**overrides: str) -> None:
    """Seed the google.classroom vault label (harness clears per test)."""
    from campus.auth import resources as auth_resources
    keys = {
        "CLIENT_ID": GOOGLE_CLASSROOM_CLIENT_ID,
        "CLIENT_SECRET": "test-registry-classroom-client-secret",
        "SCOPES": " ".join(CLASSROOM_SCOPES),
        "CONNECT_TARGETS": "https://profile.example",
    }
    keys.update(overrides)
    for key, value in keys.items():
        if value is not None:
            auth_resources.vault["google.classroom"][key] = value


class TestIntegrationsRegistryContract(unittest.TestCase):
    """GET /integrations/v1/ — read-only registry for consumers."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )
        _seed_classroom_vault()

    def _get_registry(self):
        return self.client.get("/integrations/v1/")

    def test_registry_is_public_and_lists_registry_entries(self):
        """#688: no auth required; every registry entry appears, keyed
        by its namespaced provider."""
        response = self._get_registry()

        self.assertEqual(response.status_code, 200)
        entries = response.get_json()["integrations"]
        by_provider = {entry["provider"]: entry for entry in entries}
        self.assertEqual(
            sorted(by_provider),
            ["google.calendar", "google.classroom"],
        )
        for entry in entries:
            self.assertEqual(
                sorted(entry),
                sorted([
                    "provider", "slug", "base_provider", "title",
                    "description", "scopes", "connectable",
                    "authorize_path",
                ]),
            )

    def test_connectable_entry_reports_vault_scopes_and_path(self):
        """A configured integration reports its vault SCOPES cap, the
        canonical connect path, and connectable=true."""
        response = self._get_registry()

        classroom = next(
            entry for entry in response.get_json()["integrations"]
            if entry["provider"] == "google.classroom"
        )
        self.assertEqual(classroom["slug"], "classroom")
        self.assertEqual(classroom["base_provider"], "google")
        self.assertEqual(classroom["title"], "Google Classroom")
        self.assertTrue(classroom["description"])
        self.assertEqual(classroom["scopes"], CLASSROOM_SCOPES)
        self.assertTrue(classroom["connectable"])
        self.assertEqual(
            classroom["authorize_path"],
            "/auth/v1/google/classroom/authorize",
        )

    def test_unconfigured_stub_is_not_connectable(self):
        """§2.1: a registry entry with no vault client is inert —
        reported (so consumers can render it disabled) but never
        connectable."""
        from campus.auth import resources as auth_resources
        del auth_resources.vault["google.calendar"]["CLIENT_ID"]
        del auth_resources.vault["google.calendar"]["CLIENT_SECRET"]

        response = self._get_registry()

        calendar = next(
            entry for entry in response.get_json()["integrations"]
            if entry["provider"] == "google.calendar"
        )
        self.assertFalse(calendar["connectable"])
        self.assertEqual(calendar["scopes"], [])

    def test_empty_connect_targets_disables_connect(self):
        """§2.1: empty CONNECT_TARGETS disables the connect flow —
        mirrored here as connectable=false (fail-closed)."""
        _seed_classroom_vault(CONNECT_TARGETS="")

        response = self._get_registry()

        classroom = next(
            entry for entry in response.get_json()["integrations"]
            if entry["provider"] == "google.classroom"
        )
        self.assertFalse(classroom["connectable"])

    def test_registry_never_carries_vault_secrets(self):
        """The catalog is public metadata: vault CLIENT_ID/SECRET
        values never appear in the response."""
        response = self._get_registry()

        body = response.get_data(as_text=True)
        self.assertNotIn(GOOGLE_CLASSROOM_CLIENT_ID, body)
        self.assertNotIn("client_secret", body.lower())
