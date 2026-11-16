"""Tests for campus.config (service URL delegation + policy constants).

URL resolution lives in campus.common.services; these tests pin the
campus.config delegation surface: the re-exported table and the
get_base_url behavior the suite (and its consumers) rely on.
"""

import contextlib
import os
import unittest

from campus import config


def _delete_quietly(name: str) -> None:
    with contextlib.suppress(KeyError):
        del os.environ[name]


class ServiceURLTestCase(unittest.TestCase):
    """Isolate the environment variables URL resolution consults."""

    def setUp(self):
        self.patch_env(
            ENV="development",
            DEPLOY="",
            PUBLIC_URL="https://gateway.example",
            CAMPUS_AUTH_URL="",
            AUTH_URL="",
            CAMPUS_API_URL="",
            API_URL="",
            CAMPUS_AUDIT_URL="",
            AUDIT_URL="",
            CAMPUS_BASE_URL="",
            BASE_URL="",
            CAMPUS_ENV="",
        )

    def patch_env(self, **values):
        """Set env vars for the test, restoring the previous values after."""
        for name, value in values.items():
            previous = os.environ.get(name)
            os.environ[name] = value
            if previous is None:
                self.addCleanup(_delete_quietly, name)
            else:
                self.addCleanup(os.environ.__setitem__, name, previous)


class TestBaseUrlDelegation(ServiceURLTestCase):
    """campus.config.get_base_url delegates to campus.common.services."""

    def test_per_service_override(self):
        os.environ["CAMPUS_AUTH_URL"] = "https://auth-override.example"
        self.assertEqual(
            config.get_base_url("campus.auth"),
            "https://auth-override.example",
        )

    def test_base_url_fallback_for_every_service(self):
        os.environ["BASE_URL"] = "https://base.example"
        for app_name in ("campus.auth", "campus.api", "campus.audit"):
            self.assertEqual(config.get_base_url(app_name), "https://base.example")

    def test_testing_resolves_canonical_origin(self):
        os.environ["ENV"] = "testing"
        self.assertEqual(
            config.get_base_url("campus.api"),
            "https://gateway.example",
        )

    def test_self_deployment_resolves_canonical_origin(self):
        os.environ["DEPLOY"] = "campus.audit"
        os.environ["BASE_URL"] = "https://base.example"
        self.assertEqual(
            config.get_base_url("campus.audit"),
            "https://gateway.example",
        )

    def test_unconfigured_service_error(self):
        with self.assertRaisesRegex(ValueError, "campus.profile"):
            config.get_base_url("campus.profile")


if __name__ == "__main__":
    unittest.main()
