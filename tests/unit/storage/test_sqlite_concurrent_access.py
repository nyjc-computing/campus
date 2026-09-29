"""campus.tests.unit.storage.test_sqlite_concurrent_access

Concurrency tests for the SQLite table backend's shared connection.

The backend shares one sqlite3.Connection per database path across all
threads (check_same_thread=False). Statement interleaving on a single
connection is undefined behaviour: it produced torn reads
("Could not decode to UTF-8 column ...") and "another row available"
errors that surfaced as flaky integration test failures (#557 residual;
observed in CI on 2026-09-29, Integration Tests 3.12 attempt 1).

These tests exercise concurrent mixed read/write access and fail if any
statement-level error escapes, and double as a no-deadlock check for the
per-connection locking (the RLock re-entry in update_by_id). The original
interleaving is timing-dependent and does not reproduce deterministically
on every machine - these tests pass on unlocked code on fast Windows
hosts - so their primary value is guarding against regressions that make
contention fail loudly or hang.

IMPORTANT: Lazy imports are required to avoid storage initialization
before test mode is configured (see AGENTS.md - Storage Initialization Order).
"""

import sys
import threading
import unittest


class TestSQLiteConcurrentAccess(unittest.TestCase):
    """Concurrent statement execution against the shared connection."""

    ROW_COUNT = 40
    THREADS = 6
    ITERATIONS = 60

    @classmethod
    def setUpClass(cls):
        """Configure test storage and create the table once."""
        import campus.storage.testing
        from campus.model.client import Client

        campus.storage.testing.configure_test_storage()
        campus.storage.testing.configure_test_db()

        # Force rapid GIL thread switching to maximize the chance of
        # statement interleaving on the shared connection - the default
        # switch interval rarely yields the race on fast machines.
        cls._orig_switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

        cls.table = campus.storage.tables.get_db("concurrency_test")
        cls.table.init_from_model("concurrency_test", Client)

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage."""
        sys.setswitchinterval(cls._orig_switch_interval)
        import campus.storage.testing
        campus.storage.testing.clear_all_data()

    def setUp(self):
        """Seed deterministic rows before each test."""
        import campus.storage.testing
        campus.storage.testing.clear_all_data()
        for i in range(self.ROW_COUNT):
            self.table.insert_one({
                "id": f"row-{i:04d}",
                "created_at": f"2026-01-01T00:00:{i % 60:02d}Z",
                "name": f"client-{i:04d}",
                "description": f"row {i}",
                "is_public": False,
                "redirect_uris": [],
            })

    def _run_concurrently(self, worker) -> list[Exception]:
        """Run worker(thread_idx) on THREADS threads, collect exceptions."""
        errors: list[Exception] = []
        barrier = threading.Barrier(self.THREADS)

        def wrapped(idx: int):
            try:
                barrier.wait()
                worker(idx)
            except Exception as e:  # noqa: BLE001 - collect for assertion
                errors.append(e)

        threads = [
            threading.Thread(target=wrapped, args=(i,))
            for i in range(self.THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return errors

    def test_concurrent_reads_and_writes(self):
        """Mixed get_by_id/get_matching/update_by_id from several threads.

        Reproduces the #557 failure pattern: the flaky CI run died inside
        update_by_id (read-modify-write) racing get_matching-style reads
        on the shared connection.
        """
        def worker(idx: int):
            for i in range(self.ITERATIONS):
                row_id = f"row-{(i * 7 + idx) % self.ROW_COUNT:04d}"
                # Read-modify-write (the exact path that raced in CI)
                self.table.update_by_id(
                    row_id,
                    {"description": f"updated by thread {idx} iter {i}"},
                )
                # Point reads
                self.table.get_by_id(row_id)
                # Scans (exact match on the value just written)
                self.table.get_matching({
                    "description": f"updated by thread {idx} iter {i}"
                })

        errors = self._run_concurrently(worker)
        self.assertEqual(errors, [])

        # All rows survive the contention
        remaining = self.table.get_matching({})
        self.assertEqual(len(remaining), self.ROW_COUNT)

    def test_concurrent_inserts_and_deletes(self):
        """Concurrent insert_one/delete_by_id do not corrupt the table."""

        def worker(idx: int):
            for i in range(self.ITERATIONS):
                row_id = f"new-{idx}-{i:04d}"
                self.table.insert_one({
                    "id": row_id,
                    "created_at": "2026-01-01T00:00:00Z",
                    "name": f"new-{idx}-{i:04d}",
                    "description": "concurrent insert",
                    "is_public": False,
                    "redirect_uris": [],
                })
                self.table.delete_by_id(row_id)

        errors = self._run_concurrently(worker)
        self.assertEqual(errors, [])

        # Only the seeded rows remain
        remaining = self.table.get_matching({})
        self.assertEqual(len(remaining), self.ROW_COUNT)


if __name__ == "__main__":
    unittest.main()
