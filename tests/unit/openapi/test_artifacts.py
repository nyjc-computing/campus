"""Drift + version-pin enforcement for committed OpenAPI artifacts (#1029).

Per campus#1029's enforcement loop, one test per service asserts:
(a) the committed ``campus/{svc}/docs/openapi.json`` equals a freshly
    generated spec (drift), and
(b) its ``info.version`` equals the declared campus-suite version
    (pin). A PR that changes routes without regenerating and bumping
    fails here.
"""

import json
import os
import unittest

from openapi_spec_validator import validate

from tests.unit.openapi import _service_env

SERVICES = _service_env.SERVICES


class TestOpenAPIArtifacts(unittest.TestCase):
    """Committed artifacts: drift, version pin, structural validity."""

    @classmethod
    def setUpClass(cls):
        cls._saved_environ = dict(os.environ)
        _service_env.bootstrap()
        cls.version = _service_env.suite_version()
        cls.generated: dict[str, dict] = {
            service: _service_env.build_spec(service, cls.version)
            for service in SERVICES
        }

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved_environ)

    def _artifact(self, service: str) -> dict:
        return json.loads(
            _service_env.artifact_path(service).read_text(encoding="utf-8")
        )

    def test_artifacts_are_valid_openapi(self) -> None:
        for service in SERVICES:
            validate(self.generated[service])

    def test_committed_artifact_matches_generation(self) -> None:
        for service in SERVICES:
            self.assertEqual(
                self._artifact(service),
                self.generated[service],
                f"{service}/docs/openapi.json has drifted from the "
                "generated spec. Regenerate (the fixture bootstrap in "
                "tests/unit/openapi/_service_env.py shows the env the "
                "generation needs) and bump the suite version in "
                "pyproject.toml (campus#1029).",
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
