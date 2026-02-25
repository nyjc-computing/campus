"""Unit tests for OpenAPI specification validation.

These tests validate that OpenAPI specs are syntactically valid and conform
to the OpenAPI 3.0 specification. Tests focus on structural validity rather
than specific endpoints to minimize maintenance burden.
"""

import pathlib
import unittest

from openapi_spec_validator import validate


class TestOpenAPISpec(unittest.TestCase):
    """Test OpenAPI specification validity."""

    def _validate_spec_file(self, path: pathlib.Path) -> dict:
        """Validate an OpenAPI spec file and return the parsed spec.

        Args:
            path: Path to the OpenAPI spec YAML file

        Returns:
            The parsed OpenAPI spec as a dict

        Raises:
            AssertionError: If the spec is invalid
        """
        import yaml

        spec_content = path.read_text(encoding='utf-8')
        spec = yaml.safe_load(spec_content)

        # Validate against OpenAPI 3.0 spec
        try:
            validate(spec)
        except ValueError as e:
            raise AssertionError(f"OpenAPI spec validation failed: {e}") from e

        return spec

    def test_auth_openapi_spec_is_valid(self) -> None:
        """Test that the auth service OpenAPI spec is valid."""
        spec_path = pathlib.Path(__file__).parent.parent.parent.parent
        spec_path = spec_path / "campus" / "auth" / "docs" / "openapi.yaml"

        self.assertTrue(spec_path.exists(), f"Spec file not found: {spec_path}")

        spec = self._validate_spec_file(spec_path)

        # Basic structural checks
        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("info", spec)
        self.assertIn("title", spec["info"])
        self.assertIn("version", spec["info"])
        self.assertIn("paths", spec)
        self.assertIn("components", spec)

    def test_api_openapi_spec_is_valid(self) -> None:
        """Test that the API service OpenAPI spec is valid."""
        spec_path = pathlib.Path(__file__).parent.parent.parent.parent
        spec_path = spec_path / "campus" / "api" / "docs" / "openapi.yaml"

        self.assertTrue(spec_path.exists(), f"Spec file not found: {spec_path}")

        spec = self._validate_spec_file(spec_path)

        # Basic structural checks
        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("info", spec)
        self.assertIn("title", spec["info"])
        self.assertIn("version", spec["info"])
        self.assertIn("paths", spec)
        self.assertIn("components", spec)
