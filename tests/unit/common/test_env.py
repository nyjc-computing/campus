"""Unit tests for campus.common.env module.

These tests verify that the environment proxy module works correctly,
including thread-safe initialization and proper module behavior.

Test Principles:
- Test interface contracts, not implementation
- Test thread safety and concurrent access
- Test module behavior without sys.modules replacement
- Keep tests independent and focused
"""

import os
import sys
import types
import unittest
from threading import Thread
from unittest.mock import patch

from campus.common import env


class TestEnvModuleInitialization(unittest.TestCase):
    """Test that the env module is properly initialized as a module."""

    def test_env_module_is_module(self):
        """Test that campus.common.env is a regular module."""
        # The env module should be a regular module, not a proxy instance
        import campus.common.env as env_import
        self.assertIsInstance(env_import, types.ModuleType)

    def test_all_imports_point_to_same_module(self):
        """Test that all imports of campus.common.env point to the same module."""
        # Import the module in different ways
        from campus.common import env as env1
        import campus.common.env as env2

        # All imports should point to the same module object
        self.assertIs(env1, env2)
        self.assertIs(sys.modules['campus.common.env'], env1)
        self.assertIsInstance(env1, types.ModuleType)


class TestEnvModuleFunctions(unittest.TestCase):
    """Test the module-level functions."""

    def setUp(self):
        """Set up test environment variables."""
        self.test_env_vars = {
            'TEST_VAR_1': 'value1',
            'TEST_VAR_2': 'value2',
        }
        for key, value in self.test_env_vars.items():
            os.environ[key] = value

    def tearDown(self):
        """Clean up test environment variables."""
        for key in self.test_env_vars:
            os.environ.pop(key, None)

    def test_get_function(self):
        """Test the get() function."""
        self.assertEqual(env.get('TEST_VAR_1'), 'value1')
        self.assertEqual(env.get('TEST_VAR_2'), 'value2')
        self.assertIsNone(env.get('NONEXISTENT_VAR'))
        self.assertEqual(env.get('NONEXISTENT_VAR', 'default'), 'default')

    def test_contains_function(self):
        """Test the contains() function."""
        self.assertTrue(env.contains('TEST_VAR_1'))
        self.assertFalse(env.contains('NONEXISTENT_VAR'))

    def test_keys_function(self):
        """Test the keys() function."""
        keys = env.keys()
        self.assertIsInstance(keys, list)
        self.assertIn('TEST_VAR_1', keys)
        self.assertIn('TEST_VAR_2', keys)

    def test_require_function(self):
        """Test the require() function."""
        # Should not raise when variables exist
        env.require('TEST_VAR_1', 'TEST_VAR_2')

        # Should raise when variables are missing
        with self.assertRaises(OSError) as cm:
            env.require('TEST_VAR_1', 'NONEXISTENT_VAR')
        self.assertIn('NONEXISTENT_VAR', str(cm.exception))

    def test_register_getsecret_function(self):
        """Test registering and using a custom getsecret function."""
        # Register a custom function
        def custom_getsecret(name: str) -> str:
            return f'custom:{name}'

        env.register_getsecret(custom_getsecret)

        # Test that the registered function is called
        result = env.getsecret('TEST_SECRET')
        self.assertEqual(result, 'custom:TEST_SECRET')

        # Clean up - reset to None
        env.register_getsecret(lambda name: None)  # Reset
        # Actually, we can't reset it since there's no unregister function
        # This is a limitation - the registered function persists for the test run


class TestEnvGetSecret(unittest.TestCase):
    """Test the getsecret() function."""

    def setUp(self):
        """Save current getsecret function state."""
        # Save the current getsecret function if any
        self.original_getsecret_func = getattr(env, '_getsecret_func', None)

    def tearDown(self):
        """Restore getsecret function state."""
        # Restore the original function
        if self.original_getsecret_func is not None:
            env.register_getsecret(self.original_getsecret_func)

    def test_getsecret_from_env_var(self):
        """Test getsecret() returns environment variable if set."""
        os.environ['TEST_SECRET'] = 'env_value'

        result = env.getsecret('TEST_SECRET')
        self.assertEqual(result, 'env_value')

        # Clean up
        del os.environ['TEST_SECRET']

    def test_getsecret_calls_registered_function(self):
        """Test getsecret() calls registered function when env var not set."""
        # Register a test function
        def test_getsecret(name: str) -> str:
            return f'registered:{name}'

        env.register_getsecret(test_getsecret)

        # Call getsecret for a non-existent env var
        result = env.getsecret('NONEXISTENT_SECRET')
        self.assertEqual(result, 'registered:NONEXISTENT_SECRET')

    def test_getsecret_prefers_env_var_over_registered_function(self):
        """Test getsecret() prefers env var even when registered function exists."""
        # Register a test function
        def test_getsecret(name: str) -> str:
            return f'registered:{name}'

        env.register_getsecret(test_getsecret)

        # Set env var
        os.environ['TEST_SECRET'] = 'env_value'

        # Should return env var, not call registered function
        result = env.getsecret('TEST_SECRET')
        self.assertEqual(result, 'env_value')

        # Clean up
        del os.environ['TEST_SECRET']

    def test_getsecret_raises_when_no_env_var_and_no_registered_function(self):
        """Test getsecret() raises OSError when neither env var nor registered function."""
        # Make sure no registered function and no env var
        # We can't easily unregister, so we'll test with a function that raises
        def raising_getsecret(name: str) -> str:
            raise OSError(f"Secret {name!r} not found")

        env.register_getsecret(raising_getsecret)

        # Should raise OSError
        with self.assertRaises(OSError) as cm:
            env.getsecret('NONEXISTENT_SECRET')
        self.assertIn('NONEXISTENT_SECRET', str(cm.exception))


class TestEnvAttributeAccess(unittest.TestCase):
    """Test attribute-style access to environment variables."""

    def setUp(self):
        """Set up test environment variables."""
        os.environ['TEST_ATTR_1'] = 'attr_value1'
        os.environ['TEST_ATTR_2'] = 'attr_value2'

    def tearDown(self):
        """Clean up test environment variables."""
        os.environ.pop('TEST_ATTR_1', None)
        os.environ.pop('TEST_ATTR_2', None)
        os.environ.pop('TEST_ATTR_NEW', None)

    def test_get_attribute(self):
        """Test getting environment variables via attribute access."""
        self.assertEqual(env.TEST_ATTR_1, 'attr_value1')
        self.assertEqual(env.TEST_ATTR_2, 'attr_value2')

    def test_set_attribute(self):
        """Test setting environment variables via set() method."""
        env.set('TEST_ATTR_NEW', 'new_value')
        self.assertEqual(env.TEST_ATTR_NEW, 'new_value')
        self.assertEqual(os.environ['TEST_ATTR_NEW'], 'new_value')

    def test_delete_attribute(self):
        """Test deleting environment variables via delete() method."""
        env.set('TEST_ATTR_NEW', 'temp_value')
        self.assertIn('TEST_ATTR_NEW', os.environ)

        env.delete('TEST_ATTR_NEW')
        self.assertNotIn('TEST_ATTR_NEW', os.environ)

    def test_nonexistent_attribute_raises(self):
        """Test that accessing nonexistent attributes raises AttributeError."""
        with self.assertRaises(AttributeError):
            _ = env.NONEXISTENT_ATTRIBUTE


class TestEnvThreadSafety(unittest.TestCase):
    """Test thread safety of the env module."""

    def test_concurrent_attribute_access(self):
        """Test that concurrent attribute access is thread-safe."""
        os.environ['THREAD_TEST_VAR'] = 'thread_value'

        results = []
        errors = []

        def access_env():
            try:
                # Perform various operations
                value = env.THREAD_TEST_VAR
                env.set('TEST_VAR_1', 'value1')
                value2 = env.TEST_VAR_1
                results.append((value, value2))
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = Thread(target=access_env)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")

        # Verify all threads got consistent results
        self.assertEqual(len(results), 10)
        for result in results:
            self.assertEqual(result[0], 'thread_value')
            self.assertEqual(result[1], 'value1')

    def test_concurrent_module_import(self):
        """Test that concurrent module imports are thread-safe."""
        results = []
        errors = []

        def import_env():
            try:
                # Import the module
                import campus.common.env as env_import
                # Check it's the module type
                results.append(isinstance(env_import, types.ModuleType))
            except Exception as e:
                errors.append(e)

        # Create multiple threads that try to import
        threads = []
        for _ in range(5):
            thread = Thread(target=import_env)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")

        # Verify all imports got the module
        self.assertEqual(len(results), 5)
        self.assertTrue(all(results), "Not all imports got the module")


if __name__ == '__main__':
    unittest.main()
