"""Unit tests for the cleanup job implementations (campus.cleanup.jobs).

Each job is idempotent, chunked (keyset-paginated by id) and counted.
Nothing here touches a real database: the fixtures force the testing
storage backend (SQLite tables / memory collections).
"""

import unittest

from campus.common import schema


def _future_moment(base, seconds: int) -> schema.DateTime:
    return schema.DateTime.utcafter(base, seconds=seconds)


class TestRateLimitBucketSweep(unittest.TestCase):
    """sweep_rate_limit_buckets: strict-TTL deletes, exact counts."""

    @classmethod
    def setUpClass(cls):
        from campus.audit.resources import ratelimit

        ratelimit.init_storage()
        cls.storage = ratelimit.bucket_storage

    def setUp(self):
        self.storage.delete_matching({})

    def _insert(self, bucket_id: str, last_refill: float) -> None:
        self.storage.insert_one({
            "id": bucket_id, "tokens": 1.0, "last_refill": last_refill,
        })

    def test_stale_buckets_removed_and_counted(self):
        from campus.cleanup import jobs

        self._insert("user=old1", 0.0)
        self._insert("user=old2", 0.0)
        deleted = jobs.sweep_rate_limit_buckets(now=7200.0)
        self.assertEqual(deleted, 2)
        self.assertEqual(self.storage.get_matching({}), [])

    def test_fresh_buckets_kept(self):
        from campus.cleanup import jobs

        self._insert("user=new", 1000.0)
        deleted = jobs.sweep_rate_limit_buckets(now=1001.0)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.storage.get_matching({})), 1)

    def test_ttl_boundary_is_strict(self):
        """A bucket exactly at the TTL is not yet stale (strict lt)."""
        from campus.audit.resources import ratelimit
        from campus.cleanup import jobs

        self._insert("user=edge", 0.0)
        deleted = jobs.sweep_rate_limit_buckets(
            now=ratelimit.BUCKET_TTL_SECONDS)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.storage.get_matching({})), 1)

    def test_chunked_across_batch_boundaries(self):
        """Keyset pagination sweeps everything even when every chunk
        is smaller than the batch (and each delete shifts the row
        set under the cursor)."""
        from campus.cleanup import jobs

        for index in range(5):
            self._insert(f"user=old{index}", 0.0)
        deleted = jobs.sweep_rate_limit_buckets(now=7200.0, batch_size=2)
        self.assertEqual(deleted, 5)
        self.assertEqual(self.storage.get_matching({}), [])


class TestAuthSessionSweep(unittest.TestCase):
    """sweep_auth_sessions: model-predicate expiry, chunked."""

    @classmethod
    def setUpClass(cls):
        import campus.storage

        cls.storage = campus.storage.get_collection("auth_sessions")

    def setUp(self):
        self.storage.delete_matching({})

    def _insert(self, expiry_seconds: int = 3600):
        import campus.model as model

        auth_session = model.AuthSession(
            provider="campus",
            client_id="uid-client-test",
            user_id="uid-user-test",
            redirect_uri="https://example.com/callback",
            expiry_seconds=expiry_seconds,
        )
        self.storage.insert_one(auth_session.to_storage())
        return auth_session

    def test_expired_session_removed_and_counted(self):
        from campus.cleanup import jobs

        auth_session = self._insert(expiry_seconds=3600)
        future = _future_moment(auth_session.created_at, seconds=7200)
        deleted = jobs.sweep_auth_sessions(at_time=future)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.storage.get_matching(
            {"id": auth_session.id}), [])

    def test_live_session_kept(self):
        from campus.cleanup import jobs

        auth_session = self._insert(expiry_seconds=3600)
        deleted = jobs.sweep_auth_sessions()
        self.assertEqual(deleted, 0)
        self.assertEqual(
            len(self.storage.get_matching({"id": auth_session.id})), 1)

    def test_chunked_across_batch_boundaries(self):
        from campus.cleanup import jobs

        sessions = [self._insert(expiry_seconds=3600) for _ in range(3)]
        future = _future_moment(sessions[0].created_at, seconds=7200)
        deleted = jobs.sweep_auth_sessions(at_time=future, batch_size=1)
        self.assertEqual(deleted, 3)
        self.assertEqual(self.storage.get_matching({}), [])

    def test_mixed_expiry_only_removes_expired(self):
        from campus.cleanup import jobs

        short = self._insert(expiry_seconds=1)
        long_lived = self._insert(expiry_seconds=3600)
        future = _future_moment(short.created_at, seconds=3600)
        deleted = jobs.sweep_auth_sessions(at_time=future)
        self.assertEqual(deleted, 1)
        remaining = {record["id"]
                     for record in self.storage.get_matching({})}
        self.assertEqual(remaining, {long_lived.id})


class TestDeviceCodeSweep(unittest.TestCase):
    """sweep_device_codes: model-predicate expiry, chunked."""

    @classmethod
    def setUpClass(cls):
        import campus.storage

        cls.storage = campus.storage.get_collection("device_codes")

    def setUp(self):
        self.storage.delete_matching({})

    def _insert(self, expiry_seconds: int = 3600):
        import campus.model as model

        device_code = model.DeviceCode(
            device_code="dc-test",
            user_code="uc-test",
            client_id="uid-client-test",
            expiry_seconds=expiry_seconds,
        )
        self.storage.insert_one(device_code.to_storage())
        return device_code

    def test_expired_code_removed_and_counted(self):
        from campus.cleanup import jobs

        device_code = self._insert(expiry_seconds=3600)
        future = _future_moment(device_code.created_at, seconds=7200)
        deleted = jobs.sweep_device_codes(at_time=future)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.storage.get_matching(
            {"id": device_code.id}), [])

    def test_pending_code_kept(self):
        from campus.cleanup import jobs

        device_code = self._insert(expiry_seconds=3600)
        deleted = jobs.sweep_device_codes()
        self.assertEqual(deleted, 0)
        self.assertEqual(
            len(self.storage.get_matching({"id": device_code.id})), 1)


if __name__ == "__main__":
    unittest.main()
