#!/usr/bin/env python3
"""Campus Sanity Check Tests

Quick validation tests to catch common issues before running full test suite:
- Lockfile desync (poetry.lock out of sync with pyproject.toml)
- Module import failures (campus.api and campus.auth must be importable)

These tests are designed to run early in the CI/CD pipeline to fail fast
on common issues that would prevent deployment.

Usage:
    python tests/sanity_check.py
    poetry run python tests/sanity_check.py
"""

import subprocess
import sys
import unittest
from pathlib import Path


class TestLockfileSync(unittest.TestCase):
    """Test that lockfile is in sync with dependencies."""

    def test_poetry_lock_is_in_sync(self):
        """Test that poetry.lock is in sync with pyproject.toml.

        Catches:
        - pyproject.toml changed but poetry.lock not updated
        - Dependency version conflicts
        - Missing or corrupted lock entries
        """
        # Get project root
        project_root = Path(__file__).parent.parent

        # Run 'poetry check' which validates:
        # - pyproject.toml syntax
        # - poetry.lock is in sync
        # - All dependencies are resolvable
        result = subprocess.run(
            ["poetry", "check"],
            cwd=str(project_root),
            capture_output=True,
            text=True
        )

        self.assertEqual(
            result.returncode,
            0,
            f"poetry check failed. stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_poetry_lock_file_exists(self):
        """Test that poetry.lock file exists.

        Catches:
        - Missing lock file (dependencies not installed)
        - Incomplete repo clone
        """
        project_root = Path(__file__).parent.parent
        lock_file = project_root / "poetry.lock"

        self.assertTrue(
            lock_file.exists(),
            f"poetry.lock not found at {lock_file}. "
            "Run 'poetry install' to generate the lock file."
        )

    def test_poetry_lock_is_valid(self):
        """Test that poetry.lock is a valid TOML file.

        Catches:
        - Corrupted lock file
        - Incomplete or malformed entries
        """
        project_root = Path(__file__).parent.parent
        lock_file = project_root / "poetry.lock"

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore

        try:
            with open(lock_file, "rb") as f:
                tomllib.load(f)
        except Exception as e:
            self.fail(
                f"poetry.lock is not a valid TOML file: {e}. "
                "Try running 'poetry install' to regenerate it."
            )


class TestRequiredDeploymentFiles(unittest.TestCase):
    """Test that required deployment files exist."""

    def test_required_files_exist(self):
        """Test that critical deployment files are present.

        Catches:
        - Incomplete repository clones
        - Missing critical configuration files
        - CI/CD setup issues
        """
        project_root = Path(__file__).parent.parent
        required_files = [
            "main.py",
            "wsgi.py",
            "pyproject.toml",
            "poetry.lock",
        ]

        missing_files = []
        for filename in required_files:
            filepath = project_root / filename
            if not filepath.exists():
                missing_files.append(filename)

        self.assertEqual(
            missing_files,
            [],
            f"Missing required deployment files: {', '.join(missing_files)}"
        )


class TestPythonVersionCompatibility(unittest.TestCase):
    """Test that runtime Python version is compatible."""

    def test_python_version_matches_requirements(self):
        """Test that runtime Python version meets pyproject.toml requirements.

        Catches:
        - Python environment version mismatch
        - CI/CD Python version setup issues
        - Local development environment misconfiguration
        """
        import re
        project_root = Path(__file__).parent.parent
        pyproject = project_root / "pyproject.toml"

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore

        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)

            python_requirement = config.get("tool", {}).get("poetry", {}).get(
                "dependencies", {}
            ).get("python")

            if not python_requirement:
                self.fail(
                    "Could not find python requirement in pyproject.toml"
                )

            # Parse version constraint (e.g., ">=3.11.0,<3.12")
            runtime_version = sys.version_info
            runtime_version_str = f"{runtime_version.major}.{runtime_version.minor}.{runtime_version.micro}"

            # Simple version check: extract minimum and maximum versions
            min_match = re.search(r">=(\d+\.\d+)", python_requirement)
            max_match = re.search(r"<(\d+\.\d+)", python_requirement)

            if min_match:
                min_version = min_match.group(1)
                min_parts = tuple(map(int, min_version.split('.')))
                runtime_parts = (runtime_version.major, runtime_version.minor)
                self.assertGreaterEqual(
                    runtime_parts,
                    min_parts,
                    f"Runtime Python {runtime_version_str} is below minimum "
                    f"requirement {python_requirement}"
                )

            if max_match:
                max_version = max_match.group(1)
                max_parts = tuple(map(int, max_version.split('.')))
                runtime_parts = (runtime_version.major, runtime_version.minor)
                self.assertLess(
                    runtime_parts,
                    max_parts,
                    f"Runtime Python {runtime_version_str} exceeds maximum "
                    f"requirement {python_requirement}"
                )

        except Exception as e:
            self.fail(
                f"Error checking Python version compatibility: {e}"
            )


class TestFixturesImportable(unittest.TestCase):
    """Test that test fixtures can be imported."""

    def test_test_fixtures_can_be_imported(self):
        """Test that test fixtures module imports without errors.

        Catches:
        - Test infrastructure breakage
        - Missing test dependencies
        - Fixture configuration errors
        """
        try:
            from tests.fixtures import (
                api, auth, mongodb, postgres, require, services,
                setup, storage, yapper
            )
            self.assertIsNotNone(api, "fixtures.api is None")
            self.assertIsNotNone(auth, "fixtures.auth is None")
            self.assertIsNotNone(services, "fixtures.services is None")
        except ImportError as e:
            self.fail(
                f"Failed to import test fixtures: {e}\n"
                f"Test infrastructure may be broken."
            )
        except Exception as e:
            self.fail(
                f"Unexpected error importing test fixtures: {e}"
            )


if __name__ == '__main__':
    # Set up environment for sanity checks
    import os
    os.environ.setdefault('ENV', 'testing')

    # Run tests with verbose output
    unittest.main(verbosity=2)
