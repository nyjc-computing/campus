"""Test the migration backup helpers (#27 phase 3, #746).

Covers the backup envelope (write/read round-trip, foreign-format
rejection, non-JSON value serialization), restore semantics
(validation before write, collection filter, dry run) and the CLI.
No live database: storage is faked at campus.storage.get_collection,
imported lazily inside each test (storage backends must not initialize
before test mode is set).
"""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from migrations._backup import read_backup, restore, write_backup


class FakeCollection:
    """Records update_by_id calls."""

    def __init__(self):
        self.updated = []

    def update_by_id(self, doc_id, update):
        self.updated.append((doc_id, update))


def _doc(id, **extra):
    return {"id": id, **extra}


class BackupTestCase(unittest.TestCase):
    """Shared temp-dir fixture."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.dir = Path(self.tmpdir.name)

    def _path(self, name="backup.json"):
        return self.dir / name

    def _fakes(self):
        """Patch campus.storage.get_collection to per-name fakes."""
        fakes = {}

        def get_collection(name):
            return fakes.setdefault(name, FakeCollection())

        patcher = patch(
            "campus.storage.get_collection", side_effect=get_collection)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fakes


class TestWriteBackup(BackupTestCase):

    def test_envelope_fields_and_round_trip(self):
        collections = {"tokens": [_doc("t1", scope="read")],
                       "auth_sessions": [_doc("s1"), _doc("s2")]}
        count = write_backup(
            self._path(), "005", "005_backfill_scope_string.py", collections)
        self.assertEqual(count, 3)
        envelope = read_backup(self._path())
        self.assertEqual(envelope["format"], "campus-migration-backup/1")
        self.assertEqual(envelope["revision"], "005")
        self.assertEqual(envelope["filename"], "005_backfill_scope_string.py")
        # created_at is an ISO UTC timestamp
        self.assertIsInstance(
            datetime.fromisoformat(envelope["created_at"]), datetime)
        self.assertEqual(envelope["collections"], collections)

    def test_serializes_non_json_values(self):
        write_backup(
            self._path(), "005", "005_x.py",
            {"tokens": [_doc("t1", expires_at=datetime(2026, 10, 3))]})
        envelope = read_backup(self._path())
        self.assertEqual(
            envelope["collections"]["tokens"][0]["expires_at"],
            "2026-10-03 00:00:00")

    def test_empty_collections_writes_empty_envelope(self):
        count = write_backup(self._path(), "006", "006_x.py", {})
        self.assertEqual(count, 0)
        self.assertEqual(read_backup(self._path())["collections"], {})


class TestReadBackup(BackupTestCase):

    def test_rejects_foreign_json(self):
        for bad in (
            json.dumps({"format": "some-other-tool/1", "collections": {}}),
            json.dumps([1, 2, 3]),
            json.dumps({"collections": {}}),  # format missing
        ):
            path = self._path()
            path.write_text(bad, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_backup(path)

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            read_backup(self._path("absent.json"))


class TestRestore(BackupTestCase):

    def _write_backup(self, collections, name="backup.json"):
        path = self._path(name)
        write_backup(path, "005", "005_x.py", collections)
        return path

    def test_restores_all_collections_by_id(self):
        path = self._write_backup({
            "tokens": [_doc("t1", scope="read write")],
            "auth_sessions": [_doc("s1", scope="read")],
        })
        fakes = self._fakes()
        restored = restore(path)
        self.assertEqual(restored, {"tokens": 1, "auth_sessions": 1})
        self.assertEqual(
            fakes["tokens"].updated,
            [("t1", {"id": "t1", "scope": "read write"})])
        self.assertEqual(
            fakes["auth_sessions"].updated,
            [("s1", {"id": "s1", "scope": "read"})])

    def test_collection_filter(self):
        path = self._write_backup({
            "tokens": [_doc("t1")],
            "auth_sessions": [_doc("s1")],
        })
        fakes = self._fakes()
        restored = restore(path, collections=["tokens"])
        self.assertEqual(restored, {"tokens": 1})
        self.assertEqual(len(fakes["tokens"].updated), 1)
        self.assertNotIn("auth_sessions", fakes)

    def test_dry_run_writes_nothing(self):
        path = self._write_backup({"tokens": [_doc("t1")]})
        fakes = self._fakes()
        restored = restore(path, dry_run=True)
        self.assertEqual(restored, {"tokens": 1})
        self.assertEqual(fakes, {})

    def test_rejects_documents_without_id_before_writing(self):
        path = self._write_backup({
            "tokens": [_doc("t1"), {"scope": "no id here"}],
        })
        fakes = self._fakes()
        with self.assertRaises(ValueError):
            restore(path)
        self.assertEqual(fakes, {})


class TestMain(BackupTestCase):
    """CLI-level smoke tests for show/restore."""

    def _run(self, argv):
        from migrations._backup import main
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_show_prints_summary(self):
        path = self._path()
        write_backup(path, "005", "005_x.py",
                     {"tokens": [_doc("t1"), _doc("t2")]})
        exit_code, stdout, _ = self._run(["show", str(path)])
        self.assertEqual(exit_code, 0)
        self.assertIn("005_x.py", stdout)
        self.assertIn("revision 005", stdout)
        self.assertIn("tokens: 2 document(s)", stdout)

    def test_restore_dry_run_flag_writes_nothing(self):
        path = self._path()
        write_backup(path, "005", "005_x.py", {"tokens": [_doc("t1")]})
        fakes = self._fakes()
        exit_code, stdout, _ = self._run(
            ["restore", str(path), "--dry-run"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(fakes, {})
        self.assertIn("dry run", stdout)

    def test_restore_missing_file_errors_cleanly(self):
        exit_code, _, stderr = self._run(
            ["restore", str(self._path("absent.json"))])
        self.assertEqual(exit_code, 1)
        self.assertIn("error:", stderr)

    def test_restore_foreign_format_errors_cleanly(self):
        path = self._path()
        path.write_text(json.dumps({"format": "nope"}), encoding="utf-8")
        exit_code, _, stderr = self._run(["restore", str(path)])
        self.assertEqual(exit_code, 1)
        self.assertIn("error:", stderr)


if __name__ == "__main__":
    unittest.main()
