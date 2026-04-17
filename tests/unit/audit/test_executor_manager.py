"""Unit tests for campus.audit.middleware.tracing.ExecutorManager.

These tests verify that the ExecutorManager class properly manages the
lifecycle of ThreadPoolExecutor instances with clear state tracking
and idempotent operations.

Test Principles:
- Test lifecycle management (creation, shutdown, recreation)
- Test idempotency guarantees for shutdown and recreate operations
- Test state tracking properties and helper methods
- Test error handling for lifecycle violations
- Do not test actual ThreadPoolExecutor behavior (that's CPython's responsibility)
"""

import concurrent.futures
import unittest
from unittest.mock import Mock, patch

from campus.audit.middleware.tracing import ExecutorManager


class TestExecutorManagerInitialization(unittest.TestCase):
    """Test ExecutorManager initialization and configuration."""

    def test_default_initialization(self):
        """Test that ExecutorManager initializes with default configuration."""
        manager = ExecutorManager()

        # Verify initial state
        self.assertFalse(manager.is_initialized)
        self.assertFalse(manager.is_shutdown)
        self.assertIsNone(manager._executor)

    def test_custom_initialization(self):
        """Test that ExecutorManager accepts custom configuration."""
        manager = ExecutorManager(
            max_workers=4,
            thread_name_prefix="custom_prefix"
        )

        # Verify configuration is stored
        self.assertEqual(manager._max_workers, 4)
        self.assertEqual(manager._thread_name_prefix, "custom_prefix")


class TestExecutorManagerLifecycle(unittest.TestCase):
    """Test ExecutorManager lifecycle operations."""

    def test_get_executor_creates_on_first_call(self):
        """Test that get_executor() creates executor on first call."""
        manager = ExecutorManager()

        executor = manager.get_executor()

        # Verify executor was created
        self.assertIsNotNone(executor)
        self.assertIsInstance(executor, concurrent.futures.ThreadPoolExecutor)
        self.assertTrue(manager.is_initialized)
        self.assertFalse(manager.is_shutdown)

    def test_get_executor_returns_same_instance(self):
        """Test that get_executor() returns the same instance on subsequent calls."""
        manager = ExecutorManager()

        executor1 = manager.get_executor()
        executor2 = manager.get_executor()

        # Verify same instance is returned
        self.assertIs(executor1, executor2)

    def test_shutdown_sets_state_correctly(self):
        """Test that shutdown() properly sets shutdown state."""
        manager = ExecutorManager()

        # Create and then shutdown executor
        manager.get_executor()
        manager.shutdown(wait=True)

        # Verify state is updated
        self.assertTrue(manager.is_shutdown)
        self.assertTrue(manager.is_initialized)

    def test_shutdown_is_idempotent(self):
        """Test that multiple shutdown() calls are safe (no errors)."""
        manager = ExecutorManager()

        # Create executor
        manager.get_executor()

        # Multiple shutdowns should not raise errors
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)  # Second call should be safe
        manager.shutdown(wait=True)  # Third call should be safe

        # State should remain shutdown
        self.assertTrue(manager.is_shutdown)

    def test_get_executor_after_shutdown_raises_error(self):
        """Test that get_executor() raises RuntimeError after shutdown."""
        manager = ExecutorManager()

        # Create and shutdown executor
        manager.get_executor()
        manager.shutdown(wait=True)

        # Attempting to get executor should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            manager.get_executor()

        # Verify error message is helpful
        self.assertIn("shut down", str(context.exception))
        self.assertIn("recreate", str(context.exception))

    def test_recreate_after_shutdown(self):
        """Test that recreate() creates new executor after shutdown."""
        manager = ExecutorManager()

        # Create and shutdown executor
        executor1 = manager.get_executor()
        manager.shutdown(wait=True)

        # Recreate executor
        manager.recreate()
        executor2 = manager.get_executor()

        # Verify new executor was created
        self.assertIsNotNone(executor2)
        self.assertIsInstance(executor2, concurrent.futures.ThreadPoolExecutor)
        self.assertFalse(manager.is_shutdown)
        self.assertTrue(manager.is_initialized)

        # Verify it's a different instance
        self.assertIsNot(executor1, executor2)

    def test_recreate_while_running(self):
        """Test that recreate() shuts down running executor before creating new one."""
        manager = ExecutorManager()

        # Create executor
        executor1 = manager.get_executor()

        # Recreate while executor is running
        manager.recreate()
        executor2 = manager.get_executor()

        # Verify new executor was created
        self.assertIsNotNone(executor2)
        self.assertFalse(manager.is_shutdown)

        # Verify it's a different instance
        self.assertIsNot(executor1, executor2)

    def test_recreate_without_prior_initialization(self):
        """Test that recreate() works even without prior executor creation."""
        manager = ExecutorManager()

        # Recreate without ever calling get_executor()
        manager.recreate()

        # Should be able to get executor now
        executor = manager.get_executor()
        self.assertIsNotNone(executor)
        self.assertFalse(manager.is_shutdown)


class TestExecutorManagerStateTracking(unittest.TestCase):
    """Test ExecutorManager state tracking properties."""

    def test_is_initialized_reflects_executor_state(self):
        """Test that is_initialized reflects executor creation state."""
        manager = ExecutorManager()

        # Initially not initialized
        self.assertFalse(manager.is_initialized)

        # After creating executor, should be initialized
        manager.get_executor()
        self.assertTrue(manager.is_initialized)

        # After shutdown, still initialized
        manager.shutdown(wait=True)
        self.assertTrue(manager.is_initialized)

        # After recreate, still initialized
        manager.recreate()
        self.assertTrue(manager.is_initialized)

    def test_is_shutdown_reflects_shutdown_state(self):
        """Test that is_shutdown reflects executor shutdown state."""
        manager = ExecutorManager()

        # Initially not shutdown
        self.assertFalse(manager.is_shutdown)

        # After creating executor, still not shutdown
        manager.get_executor()
        self.assertFalse(manager.is_shutdown)

        # After shutdown, should be shutdown
        manager.shutdown(wait=True)
        self.assertTrue(manager.is_shutdown)

        # After recreate, no longer shutdown
        manager.recreate()
        self.assertFalse(manager.is_shutdown)


class TestExecutorManagerEdgeCases(unittest.TestCase):
    """Test ExecutorManager edge cases and boundary conditions."""

    def test_multiple_shutdown_and_recreate_cycles(self):
        """Test multiple shutdown/recreate cycles work correctly."""
        manager = ExecutorManager()

        # First cycle
        manager.get_executor()
        manager.shutdown(wait=True)
        manager.recreate()

        # Second cycle
        manager.shutdown(wait=True)
        manager.recreate()

        # Third cycle
        manager.shutdown(wait=True)
        manager.recreate()

        # Should still work correctly
        executor = manager.get_executor()
        self.assertIsNotNone(executor)
        self.assertFalse(manager.is_shutdown)

    def test_shutdown_without_create_is_safe(self):
        """Test that shutdown() without prior get_executor() is safe."""
        manager = ExecutorManager()

        # Should not raise error even though executor was never created
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)

        # State should be consistent (not shutdown since never initialized)
        self.assertFalse(manager.is_initialized)
        self.assertFalse(manager.is_shutdown)

    def test_recreate_creates_fresh_executor_after_multiple_shutdowns(self):
        """Test that recreate() works after multiple shutdowns."""
        manager = ExecutorManager()

        # Create executor
        manager.get_executor()

        # Multiple shutdowns
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)

        # Recreate should still work
        manager.recreate()
        executor = manager.get_executor()

        self.assertIsNotNone(executor)
        self.assertFalse(manager.is_shutdown)


class TestExecutorManagerWithMockExecutor(unittest.TestCase):
    """Test ExecutorManager behavior with mocked ThreadPoolExecutor."""

    def test_shutdown_calls_executor_shutdown(self):
        """Test that shutdown() properly calls executor.shutdown()."""
        manager = ExecutorManager()

        # Create a mock executor
        mock_executor = Mock(spec=concurrent.futures.ThreadPoolExecutor)
        manager._executor = mock_executor

        # Shutdown the manager
        manager.shutdown(wait=True)

        # Verify executor.shutdown was called
        mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_shutdown_only_called_once_on_mock(self):
        """Test that shutdown() only calls executor.shutdown() once despite multiple calls."""
        manager = ExecutorManager()

        # Create a mock executor
        mock_executor = Mock(spec=concurrent.futures.ThreadPoolExecutor)
        manager._executor = mock_executor

        # Multiple shutdowns
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)
        manager.shutdown(wait=True)

        # Verify executor.shutdown was only called once
        mock_executor.shutdown.assert_called_once_with(wait=True)


if __name__ == "__main__":
    unittest.main()
