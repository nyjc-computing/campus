"""Unit tests for campus.common.utils.utc_time module.

These tests verify that UTC time utility functions fulfill their interface
contracts. They focus on testing behavior and edge cases, not implementation
details.

Test Principles:
- Test interface contracts, not implementation
- Test pure function behavior with clear I/O
- Test edge cases and error conditions
- Keep tests independent and focused
"""

import unittest
from datetime import datetime, timedelta, timezone

from campus.common.utils import utc_time


class TestUTCTimeNow(unittest.TestCase):
    """Test the now() function."""

    def test_now_returns_datetime_instance(self):
        """Test that now() returns a datetime instance."""
        result = utc_time.now()
        self.assertIsInstance(result, datetime)

    def test_now_returns_utc_timezone(self):
        """Test that now() returns a datetime with UTC timezone."""
        result = utc_time.now()
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_now_returns_current_time(self):
        """Test that now() returns approximately the current time."""
        before = datetime.now(timezone.utc)
        result = utc_time.now()
        after = datetime.now(timezone.utc)

        # Should be between before and after (within 1 second tolerance)
        self.assertLessEqual(before, result)
        self.assertLessEqual(result, after)

        delta = (after - before).total_seconds()
        self.assertLess(delta, 1.0, "Test execution took too long")


class TestUTCTimeAfter(unittest.TestCase):
    """Test the after() function."""

    def test_after_without_time_adds_to_now(self):
        """Test that after() without time parameter adds to current time."""
        before = utc_time.now()
        result = utc_time.after(hours=1)
        after = utc_time.now()

        # Should be approximately 1 hour from before
        delta = result - before
        self.assertAlmostEqual(delta.total_seconds(), 3600, delta=5)

        # Result should be in the future relative to before, but past relative to after
        self.assertGreater(result, before)

    def test_after_with_specific_time(self):
        """Test that after() with time parameter adds to that time."""
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_time.after(time=base_time, days=1)

        expected = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_after_with_multiple_deltas(self):
        """Test that after() correctly handles multiple time deltas."""
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_time.after(time=base_time, days=1, hours=2, minutes=30)

        expected = datetime(2025, 1, 2, 14, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_after_with_negative_delta(self):
        """Test that after() works with negative deltas (past times)."""
        base_time = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_time.after(time=base_time, days=-1)

        expected = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(result, expected)

    def test_after_returns_utc_timezone(self):
        """Test that after() returns datetime with UTC timezone."""
        result = utc_time.after(hours=1)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_after_with_seconds(self):
        """Test that after() works with seconds parameter."""
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_time.after(time=base_time, seconds=90)

        expected = datetime(2025, 1, 1, 12, 1, 30, tzinfo=timezone.utc)
        self.assertEqual(result, expected)


class TestUTCTimeIsExpired(unittest.TestCase):
    """Test the is_expired() function."""

    def test_is_expired_with_past_datetime(self):
        """Test that is_expired() returns True for past datetimes."""
        past_time = utc_time.after(hours=-2)
        self.assertTrue(utc_time.is_expired(past_time))

    def test_is_expired_with_future_datetime(self):
        """Test that is_expired() returns False for future datetimes."""
        future_time = utc_time.after(hours=2)
        self.assertFalse(utc_time.is_expired(future_time))

    def test_is_expired_with_threshold(self):
        """Test that is_expired() respects threshold parameter."""
        now = utc_time.now()

        # Time just barely in the past (0.5 seconds ago)
        almost_expired = utc_time.after(time=now, seconds=-0.5)

        # With threshold of 1 second, should not be expired
        self.assertFalse(utc_time.is_expired(
            almost_expired, at_time=now, threshold=1))

        # With threshold of 0, should be expired
        self.assertTrue(utc_time.is_expired(
            almost_expired, at_time=now, threshold=0))

    def test_is_expired_with_at_time_parameter(self):
        """Test that is_expired() can check expiry at specific time."""
        check_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Time before check_time
        before = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(utc_time.is_expired(before, at_time=check_time))

        # Time after check_time
        after = datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(utc_time.is_expired(after, at_time=check_time))

    def test_is_expired_with_timestamp_float(self):
        """Test that is_expired() works with float timestamps."""
        # Create a timestamp from 2 hours ago
        past_dt = utc_time.after(hours=-2)
        past_timestamp = past_dt.timestamp()

        self.assertTrue(utc_time.is_expired(past_timestamp))

    def test_is_expired_threshold_edge_cases(self):
        """Test is_expired() with various threshold values."""
        now = utc_time.now()

        test_cases = [
            # (time_offset_seconds, threshold, expected_expired, description)
            (-10, 0, True, "10 seconds ago with no threshold"),
            (-10, 15, False, "10 seconds ago within 15s threshold"),
            (10, 0, False, "10 seconds in future"),
            (-0.5, 1, False, "0.5 seconds ago within 1s threshold"),
            (-2, 1, True, "2 seconds ago beyond 1s threshold"),
            (-5, 5, False, "5 seconds ago with exactly 5s threshold"),
        ]

        for offset, threshold, expected, desc in test_cases:
            with self.subTest(desc=desc):
                test_time = utc_time.after(time=now, seconds=offset)
                result = utc_time.is_expired(
                    test_time, at_time=now, threshold=threshold)
                self.assertEqual(result, expected, f"Failed: {desc}")


class TestUTCTimeRFC3339(unittest.TestCase):
    """Test RFC3339 format conversion functions."""

    def test_to_rfc3339_format(self):
        """Test that to_rfc3339() produces valid RFC3339 string."""
        dt = datetime(2025, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = utc_time.to_rfc3339(dt)

        self.assertIsInstance(result, str)
        # Should contain date and time components
        self.assertIn('2025', result)
        self.assertIn('14', result)
        self.assertIn('30', result)

    def test_from_rfc3339_parsing(self):
        """Test that from_rfc3339() parses RFC3339 strings."""
        rfc3339_str = "2025-01-15T14:30:45Z"
        result = utc_time.from_rfc3339(rfc3339_str)

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.second, 45)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_rfc3339_roundtrip(self):
        """Test that RFC3339 conversion roundtrips correctly."""
        original = datetime(2025, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        rfc3339_str = utc_time.to_rfc3339(original)
        restored = utc_time.from_rfc3339(rfc3339_str)

        # Should be equal (RFC3339 may not preserve microseconds)
        self.assertEqual(original.replace(microsecond=0),
                         restored.replace(microsecond=0))

    def test_rfc3339_roundtrip_with_microseconds(self):
        """Test RFC3339 roundtrip with microsecond precision."""
        original = utc_time.now()
        rfc3339_str = utc_time.to_rfc3339(original)
        restored = utc_time.from_rfc3339(rfc3339_str)

        # Should preserve at least second precision
        self.assertEqual(original.replace(microsecond=0),
                         restored.replace(microsecond=0))


class TestUTCTimeTimestamp(unittest.TestCase):
    """Test Unix timestamp conversion functions."""

    def test_to_timestamp_returns_int(self):
        """Test that to_timestamp() returns an integer."""
        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_time.to_timestamp(dt)

        self.assertIsInstance(result, int)

    def test_to_timestamp_value(self):
        """Test that to_timestamp() produces correct Unix timestamp."""
        # Unix epoch
        epoch = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = utc_time.to_timestamp(epoch)
        self.assertEqual(result, 0)
        # Known timestamp: 2025-01-01 00:00:00 UTC
        dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = utc_time.to_timestamp(dt)
        # This should be a positive number greater than or equal to the
        # known timestamp for 2025-01-01 00:00:00 UTC
        self.assertGreaterEqual(result, 1735689600)  # 2025-01-01 in seconds

    def test_from_timestamp_returns_datetime(self):
        """Test that from_timestamp() returns datetime with UTC timezone."""
        result = utc_time.from_timestamp(1735689600)  # 2025-01-01 00:00:00

        self.assertIsInstance(result, datetime)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_timestamp_roundtrip(self):
        """Test that timestamp conversion roundtrips correctly."""
        original = datetime(2025, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        timestamp = utc_time.to_timestamp(original)
        restored = utc_time.from_timestamp(timestamp)

        # Timestamps are in seconds, so lose sub-second precision
        self.assertEqual(original.replace(microsecond=0),
                         restored.replace(microsecond=0))

    def test_timestamp_roundtrip_current_time(self):
        """Test timestamp roundtrip with current time."""
        original = utc_time.now()
        timestamp = utc_time.to_timestamp(original)
        restored = utc_time.from_timestamp(timestamp)

        # Should match to second precision
        self.assertEqual(original.replace(microsecond=0),
                         restored.replace(microsecond=0))


if __name__ == '__main__':
    unittest.main()
