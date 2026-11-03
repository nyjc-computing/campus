"""Drift + version-pin enforcement for committed OpenAPI artifacts (#1029).

Per campus#1029's enforcement loop, one test per service asserts:
(a) the committed ``campus/{svc}/docs/openapi.json`` equals a freshly
    generated spec (drift), and
(b) its ``info.version`` equals the declared campus-suite version
    (pin). A PR that changes routes without regenerating and bumping
    fails here.

Generation runs with the same test fixtures the contract suite uses
(test storage backends; no external services), but WITHOUT the
flask_test campus_python patch, so nothing leaks into the rest of the
unit-suite process.
"""

import json
import os
import pathlib
import tomllib
import unittest

from openapi_spec_validator import validate

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

SERVICES = ("campus.auth", "campus.api", "campus.audit")


def _artifact_path(service: str) -> pathlib.Path:
    return REPO_ROOT / service.replace(".", "/") / "docs" / "openapi.json"


def _suite_version() -> str:
    """The declared campus-suite version, read from pyproject.toml.

    pyproject (not importlib.metadata) is the source: editable-install
    metadata goes stale between a version bump and the next venv sync.
    """
    data = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return data["tool"]["poetry"]["version"]


class TestOpenAPIArtifacts(unittest.TestCase):
    """Committed artifacts: drift, version pin, structural validity."""

    @classmethod
    def setUpClass(cls):
        from tests.fixtures import auth as auth_fixture
        from tests.fixtures import setup
        from tests.fixtures import yapper as yapper_fixture

        cls._saved_environ = dict(os.environ)

        from campus.common import env

        env.set("ENV", env.TESTING)
        setup.set_test_env_vars()
        import campus.storage.testing

        campus.storage.testing.configure_test_storage()
        env.set("CAMPUS_AUTH_URL", "https://campus.test")
        env.set("CAMPUS_API_URL", "https://campus.test")
        env.set("PUBLIC_URL", "https://campus.test")
        auth_fixture.init()
        yapper_fixture.init()

        from campus.flask_campus import openapi

        cls.version = _suite_version()
        cls.generated: dict[str, dict] = {}
        for service in SERVICES:
            os.environ["DEPLOY"] = service
            os.environ["AUDIT_TRACING_ENABLED"] = "0"
            os.environ["AUDIT_EVENTS_ENABLED"] = "0"
            cls.generated[service] = openapi.build_spec_from_module(
                service, version=cls.version
            )

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved_environ)

    def _artifact(self, service: str) -> dict:
        return json.loads(_artifact_path(service).read_text(encoding="utf-8"))

    def test_artifacts_are_valid_openapi(self) -> None:
        for service in SERVICES:
            validate(self.generated[service])

    def test_committed_artifact_matches_generation(self) -> None:
        for service in SERVICES:
            self.assertEqual(
                self._artifact(service),
                self.generated[service],
                f"{service}/docs/openapi.json has drifted from the "
                "generated spec. Regenerate with "
                f"`python -m flask_campus.openapi {service}` "
                "(the fixture-env bootstrap in this test module shows "
                "the env the generation needs) and bump the suite "
                "version in pyproject.toml (campus#1029).",
            )

    def test_info_version_pins_suite_version(self) -> None:
        for service in SERVICES:
            self.assertEqual(
                self._artifact(service)["info"]["version"],
                self.version,
                f"{service}/docs/openapi.json info.version must equal "
                "the campus-suite version; bump pyproject.toml when the "
                "spec changes (minor) and regenerate the artifact "
                "(campus#1029).",
            )


if __name__ == "__main__":
    unittest.main()
