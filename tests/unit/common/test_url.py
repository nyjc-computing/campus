"""Unit tests for campus.common.utils.url canonical origin resolution.

`canonical_origin` (and thus `full_url_for`) requires an explicit
PUBLIC_URL env var — the only way to express plain-HTTP local
development origins (#649). The legacy `https://{HOSTNAME}` fallback
was removed (#652): deployments that only set HOSTNAME must migrate.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import flask

from campus.common.utils import url


def _env(**overrides: str | None) -> dict[str, str | None]:
    """Snapshot the env vars these tests mutate."""
    return {name: os.environ.get(name) for name in overrides}


def _restore_env(saved: dict[str, str | None]) -> None:
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


class _AppContextTestCase(unittest.TestCase):
    """Base providing a Flask app with a `finalize_login` endpoint and
    env save/restore around each test."""

    def setUp(self):
        self.saved = _env(PUBLIC_URL=None, HOSTNAME=None)
        self.app = flask.Flask(__name__)
        self.app.config["SERVER_NAME"] = "in-process.test"

        @self.app.get("/finalize_login")
        def finalize_login():
            return ""

    def tearDown(self):
        _restore_env(self.saved)


class TestCanonicalOrigin(_AppContextTestCase):
    """canonical_origin requires PUBLIC_URL."""

    def test_public_url_http_localhost_with_port(self):
        os.environ["PUBLIC_URL"] = "http://localhost:5000"
        with self.app.app_context():
            self.assertEqual(url.canonical_origin(), "http://localhost:5000")

    def test_public_url_https_domain(self):
        os.environ["PUBLIC_URL"] = "https://classroom.example.com"
        with self.app.app_context():
            self.assertEqual(
                url.canonical_origin(), "https://classroom.example.com"
            )

    def test_public_url_trailing_slash_is_normalized(self):
        os.environ["PUBLIC_URL"] = "http://localhost:5000/"
        with self.app.app_context():
            self.assertEqual(url.canonical_origin(), "http://localhost:5000")

    def test_missing_public_url_raises(self):
        with self.app.app_context(), self.assertRaises(OSError):
            url.canonical_origin()

    def test_hostname_alone_no_longer_suffices(self):
        # The https://{HOSTNAME} fallback was removed (campus#652)
        os.environ["HOSTNAME"] = "classroom.example.com"
        with self.app.app_context(), self.assertRaises(OSError):
            url.canonical_origin()

    def test_public_url_missing_scheme_rejected(self):
        os.environ["PUBLIC_URL"] = "localhost:5000"
        with self.assertRaises(ValueError):
            url.canonical_origin()

    def test_public_url_with_path_rejected(self):
        os.environ["PUBLIC_URL"] = "https://classroom.example.com/app"
        with self.assertRaises(ValueError):
            url.canonical_origin()

    def test_public_url_with_query_rejected(self):
        os.environ["PUBLIC_URL"] = "https://classroom.example.com?next=/"
        with self.assertRaises(ValueError):
            url.canonical_origin()


class TestFullUrlFor(_AppContextTestCase):
    """full_url_for builds absolute URLs from PUBLIC_URL."""

    def test_public_url_drives_callback_url(self):
        os.environ["PUBLIC_URL"] = "http://localhost:5000"
        with self.app.test_request_context("/login"):
            self.assertEqual(
                url.full_url_for("finalize_login"),
                "http://localhost:5000/finalize_login",
            )

    def test_missing_public_url_raises(self):
        with self.app.test_request_context("/login"), \
                self.assertRaises(OSError):
            url.full_url_for("finalize_login")

    def test_explicit_hostname_overrides_public_url(self):
        os.environ["PUBLIC_URL"] = "http://localhost:5000"
        with self.app.test_request_context("/login"):
            self.assertEqual(
                url.full_url_for("finalize_login", hostname="override.test"),
                "https://override.test/finalize_login",
            )

    def test_endpoint_with_scheme_rejected(self):
        with self.app.test_request_context("/login"), \
                self.assertRaises(ValueError):
            url.full_url_for("https://evil.test/finalize_login")


class TestFullUrlForFlaskDependency(unittest.TestCase):
    """full_url_for is the only flask-requiring function in
    campus.common.utils; the import is deferred to call time so the
    module (and campus.common) imports without a web framework (#861).
    """

    def test_full_url_for_raises_helpful_error_without_flask(self):
        # Hiding flask from sys.modules simulates a project without
        # Flask installed; the caller expects a guided ImportError.
        with patch.dict(sys.modules, {"flask": None}), \
                self.assertRaises(ImportError) as ctx:
            url.full_url_for("some_endpoint")
        self.assertIn("does not depend on Flask", str(ctx.exception))

    def test_import_common_does_not_pull_flask(self):
        """`import campus.common` must not import flask or werkzeug.

        Runs in a subprocess for a clean sys.modules (this test process
        imports flask at module scope).
        """
        repo_root = Path(__file__).resolve().parents[3]
        code = (
            "import sys\n"
            "import campus.common\n"
            "pulled = [m for m in ('flask', 'werkzeug') if m in sys.modules]\n"
            "assert not pulled, f'campus.common pulled in {pulled}'\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        self.assertEqual(
            result.returncode, 0,
            f"stderr:\n{result.stderr}",
        )


class TestConfigureForCodespace(unittest.TestCase):
    """configure_for_codespace derives PUBLIC_URL from the forwarded
    domain (Codespaces is always HTTPS), preserving the #396 fix."""

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
