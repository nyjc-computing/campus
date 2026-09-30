"""Sanity guard: every test file must be reachable by a test runner.

How tests actually run in this repo (see tests/run_tests.py):

- ``unit``, ``integration``, ``performance``, ``contract`` categories use
  ``python -m unittest discover tests/<category>``. Discovery silently
  skips any *sub*directory that is not an importable package (missing
  ``__init__.py``) - this once hid an entire file
  (``tests/integration/api/test_assignments.py``) from every suite and
  CI run without any warning.
- ``sanity`` runs ``tests/sanity_check.py``, which only executes the
  TestCase classes it explicitly imports.

This guard fails when a ``tests/**/test_*.py`` file is not reachable by
either mechanism, and when an allowlisted exception becomes stale (the
file is reachable again but still listed).
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"

# Categories run via `unittest discover tests/<category>`.
DISCOVERY_CATEGORIES = {"unit", "integration", "performance", "contract"}
# Category run via explicit imports in tests/sanity_check.py.
IMPORT_CATEGORIES = {"sanity"}

# Test files deliberately unreachable by the runners, each with a reason
# and (where applicable) the issue that will remove the entry. Delete the
# entry when it becomes stale - the guard enforces this.
UNREACHABLE_ALLOWLIST = {
    "integration/api/test_assignments.py": (
        "pending #328: fails on the questions-path endpoint bug; activate "
        "discovery (add tests/integration/api/__init__.py) when fixed"
    ),
    "api/test_error_responses.py": (
        "tests/api is not a run_tests.py category, so this file never runs; "
        "give it a home (e.g. fold into tests/unit/common) or delete it"
    ),
    "scripts/test_integration.py": (
        "standalone manual script, intentionally outside all categories"
    ),
    "flask_test/test_basic.py": (
        "smoke script for the flask_test infrastructure, not a suite member"
    ),
    "integration/flask_test/test_storage.py": (
        "pytest-style plain functions (no unittest.TestCase); manual script, "
        "not runnable by the unittest runner"
    ),
}


def _category_of(rel: Path) -> str | None:
    return rel.parts[0] if len(rel.parts) > 1 else None


def _package_dirs_ok(path: Path, category_root: Path) -> bool:
    """Every directory strictly below the category root must be a package."""
    return all(
        (parent / "__init__.py").exists()
        for parent in path.parents
        if category_root in parent.parents
    )


def _sanity_imported_by_runner(stem: str) -> bool:
    sanity_check = TESTS_DIR / "sanity_check.py"
    return f"from sanity.{stem} import" in sanity_check.read_text(encoding="utf-8")


class TestTestDiscovery(unittest.TestCase):
    """Guard against test files silently excluded from the runners."""

    def test_every_test_file_is_reachable(self):
        """All test_*.py files under tests/ run via a runner or allowlist."""
        offenders = []
        for path in sorted(TESTS_DIR.rglob("test_*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(TESTS_DIR)
            if rel.as_posix() in UNREACHABLE_ALLOWLIST:
                continue
            category = _category_of(rel)
            if category in DISCOVERY_CATEGORIES:
                if not _package_dirs_ok(path, TESTS_DIR / category):
                    offenders.append(
                        f"{rel.as_posix()}: a directory between "
                        f"tests/{category}/ and the file lacks __init__.py "
                        f"(unittest discovery silently skips it)")
            elif category in IMPORT_CATEGORIES:
                if not _sanity_imported_by_runner(rel.stem):
                    offenders.append(
                        f"{rel.as_posix()}: not imported by "
                        f"tests/sanity_check.py (sanity only runs what it "
                        f"imports)")
            else:
                offenders.append(
                    f"{rel.as_posix()}: not under any run_tests.py category "
                    f"(never executed)")
        self.assertEqual(
            offenders, [],
            "Test files unreachable by any runner "
            "(fix the packaging/import, or allowlist with a reason):\n  "
            + "\n  ".join(offenders))

    def test_allowlist_entries_are_still_unreachable(self):
        """Allowlisted files must still be unreachable, else prune the list."""
        stale = []
        for rel, _reason in UNREACHABLE_ALLOWLIST.items():
            path = TESTS_DIR / rel
            if not path.exists():
                stale.append(f"{rel}: file no longer exists")
                continue
            path.relative_to(TESTS_DIR).as_posix()
            category = _category_of(path.relative_to(TESTS_DIR))
            reachable = (
                category in DISCOVERY_CATEGORIES
                and _package_dirs_ok(path, TESTS_DIR / category)
            ) or (
                category in IMPORT_CATEGORIES
                and _sanity_imported_by_runner(path.stem)
            )
            if reachable:
                stale.append(f"{rel}: now reachable - remove from allowlist")
        self.assertEqual(
            stale, [],
            "Stale entries in UNREACHABLE_ALLOWLIST (test_discovery.py):\n  "
            + "\n  ".join(stale))


if __name__ == "__main__":
    unittest.main()
