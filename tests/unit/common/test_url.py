"""Unit tests for deploy.configure_for_codespace PUBLIC_URL wiring.

Lives in the campus monorepo (not the campus-common repo) because it
exercises campus.deploy, a campus-suite module; the rest of this file's
coverage of campus.common.utils.url moved to campus-common with the
carve (#970 phase 3).
"""

import os
import unittest

import flask


def _env(**overrides: str | None) -> dict[str, str | None]:
    """Snapshot the env vars these tests mutate."""
    return {name: os.environ.get(name) for name in overrides}


def _restore_env(saved: dict[str, str | None]) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class TestConfigureForCodespace(unittest.TestCase):
    def setUp(self):
        self.saved = _env(
            PUBLIC_URL=None,
            HOSTNAME=None,
            PORT=None,
            CODESPACE_NAME=None,
            GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN=None,
        )

    def tearDown(self):
        _restore_env(self.saved)

    def test_public_url_set_from_codespace_domain(self):
        from campus import deploy

        os.environ["CODESPACE_NAME"] = "fuzzy-waddle-giggle"
        os.environ["GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"] = "app.github.dev"
        app = flask.Flask(__name__)
        deploy.configure_for_codespace(app)
        self.assertEqual(os.environ["HOSTNAME"],
                         "fuzzy-waddle-giggle-5000.app.github.dev")
        self.assertEqual(os.environ["PUBLIC_URL"],
                         "https://fuzzy-waddle-giggle-5000.app.github.dev")
