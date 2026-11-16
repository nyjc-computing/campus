"""Serving tests for the committed OpenAPI artifacts (#1029).

deploy.create_app must serve the committed
``campus/{service}/docs/openapi.json`` at ``/{service-prefix}/openapi.json``,
publicly (no authentication).
"""

import json
import os
import unittest

from tests.unit.openapi import _service_env


class TestOpenAPIServing(unittest.TestCase):
    """/{prefix}/openapi.json serves the committed artifact, publicly."""

    @classmethod
    def setUpClass(cls):
        cls._saved_environ = dict(os.environ)
        _service_env.bootstrap()
        cls.clients = {}
        for service in _service_env.SERVICES:
            app = _service_env.make_app(service)
            cls.clients[service] = app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._saved_environ)

    def _artifact(self, service: str) -> dict:
        return json.loads(
            _service_env.artifact_path(service).read_text(encoding="utf-8")
        )

    def test_spec_served_from_committed_artifact(self) -> None:
        for service in _service_env.SERVICES:
            prefix = service.split(".", 1)[1]
            resp = self.clients[service].get(f"/{prefix}/openapi.json")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json(), self._artifact(service))

    def test_spec_is_public(self) -> None:
        # No credentials of any kind: still 200, never 401/403/redirect.
        for service in _service_env.SERVICES:
            prefix = service.split(".", 1)[1]
            resp = self.clients[service].get(f"/{prefix}/openapi.json")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("openapi", resp.get_json())

    def test_spec_content_type_is_json(self) -> None:
        for service in _service_env.SERVICES:
            prefix = service.split(".", 1)[1]
            resp = self.clients[service].get(f"/{prefix}/openapi.json")
            self.assertEqual(resp.content_type, "application/json")


if __name__ == "__main__":
    unittest.main()
