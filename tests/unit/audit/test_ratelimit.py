"""Unit tests for the audit ingest rate limiter.

Verifies token-bucket math (consume, deny, refill), bucket-key
identity priority, all-or-nothing batch semantics, env-config parsing,
and stale-bucket cleanup.

File: tests/unit/audit/test_ratelimit.py
Issue: #831 (Phase 3 of #538)
"""

import unittest

RATE_TABLE = "rate_limit_buckets"


class TestBucketKey(unittest.TestCase):
    """Bucket-key encoding follows the identity priority order."""

    def test_client_and_user_pair(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(
            ratelimit.bucket_key("c1", "u1"),
            "client=c1;user=u1",
        )

    def test_user_only(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(ratelimit.bucket_key(None, "u1"), "user=u1")

    def test_client_only(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(ratelimit.bucket_key("c1", None), "client=c1")

    def test_api_key_fallback(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(
            ratelimit.bucket_key(None, None, api_key_id="k1"),
            "apikey=k1",
        )

    def test_api_key_fallback_without_key(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(
            ratelimit.bucket_key(None, None, api_key_id=None),
            "apikey=unknown",
        )


class TestRateLimitParsing(unittest.TestCase):
    """AUDIT_RATE_LIMIT_PER_MINUTE parsing fails open to the default."""

    def setUp(self):
        import os

        self._saved = os.environ.pop("AUDIT_RATE_LIMIT_PER_MINUTE", None)

    def tearDown(self):
        import os

        if self._saved is not None:
            os.environ["AUDIT_RATE_LIMIT_PER_MINUTE"] = self._saved
        else:
            os.environ.pop("AUDIT_RATE_LIMIT_PER_MINUTE", None)

    def test_default_when_unset(self):
        from campus.audit.resources import ratelimit

        self.assertEqual(
            ratelimit.get_rate_limit_per_minute(),
            ratelimit.DEFAULT_RATE_LIMIT_PER_MINUTE,
        )

    def test_valid_env_override(self):
        import os

        from campus.audit.resources import ratelimit

        os.environ["AUDIT_RATE_LIMIT_PER_MINUTE"] = "42"
        self.assertEqual(ratelimit.get_rate_limit_per_minute(), 42)

    def test_invalid_env_fails_open(self):
        import os

        from campus.audit.resources import ratelimit

        os.environ["AUDIT_RATE_LIMIT_PER_MINUTE"] = "not-a-number"
        self.assertEqual(
            ratelimit.get_rate_limit_per_minute(),
            ratelimit.DEFAULT_RATE_LIMIT_PER_MINUTE,
        )

    def test_zero_env_fails_open(self):
        import os

        from campus.audit.resources import ratelimit

        os.environ["AUDIT_RATE_LIMIT_PER_MINUTE"] = "0"
        self.assertEqual(
            ratelimit.get_rate_limit_per_minute(),
            ratelimit.DEFAULT_RATE_LIMIT_PER_MINUTE,
        )


class TestTokenBucket(unittest.TestCase):
    """Token-bucket consume/deny/refill math against test storage."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.audit pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order.
        from campus.audit.resources import ratelimit

        ratelimit.init_storage()
        cls.ratelimit = ratelimit

    def setUp(self):
        self.ratelimit.bucket_storage.delete_matching({})
        # Reset the hourly cleanup gate so cleanup tests are hermetic.
        self.ratelimit._last_cleanup = 0.0

    def _row(self, key: str) -> dict | None:
        rows = self.ratelimit.bucket_storage.get_matching({"id": key})
        return rows[0] if rows else None

    def test_new_bucket_starts_full(self):
        limit = 10
        tripped, retry_after = self.ratelimit._consume_buckets(
            {"user=u1": limit}, limit, now=1000.0
        )
        self.assertIsNone(tripped)
        self.assertEqual(retry_after, 0)
        row = self._row("user=u1")
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row["tokens"], 0.0)

    def test_new_bucket_denies_batch_larger_than_capacity(self):
        """A fresh bucket still denies counts above capacity (no
        negative-token rows); retry-after is a full window."""
        limit = 1
        tripped, retry_after = self.ratelimit._consume_buckets(
            {"user=u1": 2}, limit, now=1000.0
        )
        self.assertEqual(tripped, "user=u1")
        self.assertEqual(retry_after, 60)
        self.assertIsNone(self._row("user=u1"))

    def test_denied_when_exhausted(self):
        limit = 2
        # Bucket already at 0 tokens, refilled exactly at `now`.
        self.ratelimit.bucket_storage.insert_one({
            "id": "user=u1", "tokens": 0.0, "last_refill": 1000.0,
        })
        tripped, retry_after = self.ratelimit._consume_buckets(
            {"user=u1": 1}, limit, now=1000.0
        )
        self.assertEqual(tripped, "user=u1")
        # Refill rate = 2/60 per second; one token needs 30s.
        self.assertEqual(retry_after, 30)
        # Denied batch consumes nothing.
        row = self._row("user=u1")
        self.assertAlmostEqual(row["tokens"], 0.0)
        self.assertAlmostEqual(row["last_refill"], 1000.0)

    def test_refill_accrues_over_time(self):
        limit = 60  # refill rate = 1 token per second
        self.ratelimit.bucket_storage.insert_one({
            "id": "user=u1", "tokens": 0.0, "last_refill": 1000.0,
        })
        tripped, _ = self.ratelimit._consume_buckets(
            {"user=u1": 1}, limit, now=1030.0
        )
        self.assertIsNone(tripped)
        row = self._row("user=u1")
        self.assertAlmostEqual(row["tokens"], 29.0)

    def test_refill_is_capped_at_capacity(self):
        limit = 10
        self.ratelimit.bucket_storage.insert_one({
            "id": "user=u1", "tokens": 1.0, "last_refill": 1000.0,
        })
        tripped, _ = self.ratelimit._consume_buckets(
            {"user=u1": 1}, limit, now=99999.0
        )
        self.assertIsNone(tripped)
        row = self._row("user=u1")
        self.assertAlmostEqual(row["tokens"], limit - 1.0)

    def test_batch_all_or_nothing(self):
        """A denial on one bucket leaves other buckets untouched."""
        limit = 1
        self.ratelimit.bucket_storage.insert_one({
            "id": "user=u2", "tokens": 0.0, "last_refill": 1000.0,
        })
        tripped, _ = self.ratelimit._consume_buckets(
            {"user=u1": 1, "user=u2": 1}, limit, now=1000.0
        )
        self.assertEqual(tripped, "user=u2")
        # u1's token was NOT consumed despite being affordable.
        self.assertIsNone(self._row("user=u1"))

    def test_multi_span_batch_consumes_matching_count(self):
        limit = 5
        tripped, _ = self.ratelimit._consume_buckets(
            {"user=u1": 3}, limit, now=1000.0
        )
        self.assertIsNone(tripped)
        row = self._row("user=u1")
        self.assertAlmostEqual(row["tokens"], 2.0)

    def test_consume_for_spans_groups_by_identity(self):
        import os

        class Span:
            def __init__(self, client_id, user_id):
                self.client_id = client_id
                self.user_id = user_id

        limit = 5
        os.environ["AUDIT_RATE_LIMIT_PER_MINUTE"] = str(limit)
        self.addCleanup(os.environ.pop, "AUDIT_RATE_LIMIT_PER_MINUTE", None)

        spans = [Span("c1", "u1"), Span("c1", "u1"), Span(None, None)]
        tripped, _ = self.ratelimit.consume_for_spans(
            spans, api_key_id="k1"
        )
        self.assertIsNone(tripped)
        pair = self._row("client=c1;user=u1")
        fallback = self._row("apikey=k1")
        self.assertAlmostEqual(pair["tokens"], limit - 2)
        self.assertAlmostEqual(fallback["tokens"], limit - 1)


class TestBucketCleanup(unittest.TestCase):
    """Stale buckets are swept opportunistically."""

    @classmethod
    def setUpClass(cls):
        from campus.audit.resources import ratelimit

        ratelimit.init_storage()
        cls.ratelimit = ratelimit

    def setUp(self):
        self.ratelimit.bucket_storage.delete_matching({})
        self.ratelimit._last_cleanup = 0.0

    def test_stale_bucket_removed(self):
        rl = self.ratelimit
        rl.bucket_storage.insert_one({
            "id": "user=old", "tokens": 1.0, "last_refill": 0.0,
        })
        rl._maybe_cleanup(now=rl.BUCKET_TTL_SECONDS + 1.0)
        rows = rl.bucket_storage.get_matching({"id": "user=old"})
        self.assertEqual(rows, [])

    def test_fresh_bucket_kept(self):
        rl = self.ratelimit
        rl.bucket_storage.insert_one({
            "id": "user=new", "tokens": 1.0, "last_refill": 1000.0,
        })
        rl._maybe_cleanup(now=1001.0)
        rows = rl.bucket_storage.get_matching({"id": "user=new"})
        self.assertEqual(len(rows), 1)

    def test_cleanup_gated_by_interval(self):
        rl = self.ratelimit
        rl.bucket_storage.insert_one({
            "id": "user=old", "tokens": 1.0, "last_refill": 0.0,
        })
        # First call marks the sweep time but the row is already stale
        # relative to that same call, so it is removed.
        rl._maybe_cleanup(now=rl.BUCKET_TTL_SECONDS + 1.0)
        self.assertEqual(rl.bucket_storage.get_matching({"id": "user=old"}), [])
        # Within the interval, a new stale row is left alone.
        rl.bucket_storage.insert_one({
            "id": "user=old2", "tokens": 1.0, "last_refill": 0.0,
        })
        rl._maybe_cleanup(now=rl.BUCKET_TTL_SECONDS + 2.0)
        self.assertEqual(
            len(rl.bucket_storage.get_matching({"id": "user=old2"})), 1
        )


if __name__ == "__main__":
    unittest.main()
