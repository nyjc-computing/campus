"""Test cases for campus.common.introspect module."""

import unittest
import sys
from types import ModuleType

from campus.common.introspect import get_caller_module


def helper_function_that_calls_get_caller_module() -> ModuleType:
    """Helper function that acts as an intermediary to test get_caller_module().
    
    This function serves as the 'target' that calls get_caller_module().
    The test method that calls this function will be the 'caller'.
    """
    return get_caller_module()


class TestGetCallerModule(unittest.TestCase):
    """Test cases for get_caller_module function."""

    def test_get_caller_module_returns_correct_module(self):
        """Test that get_caller_module returns the module of the calling function."""
        # Call the helper function, which will call get_caller_module()
        # The caller should be this test module
        result_module = helper_function_that_calls_get_caller_module()
        
        # The caller module should be this test module
        expected_module = sys.modules[__name__]
        
        self.assertEqual(result_module, expected_module)
        self.assertEqual(result_module.__name__, __name__)

    def test_get_caller_module_returns_module_type(self):
        """Test that get_caller_module returns a ModuleType instance."""
        result_module = helper_function_that_calls_get_caller_module()
        
        self.assertIsInstance(result_module, ModuleType)

    def test_get_caller_module_with_nested_calls(self):
        """Test get_caller_module with multiple levels of function calls."""
        
        def level_two():
            return helper_function_that_calls_get_caller_module()
        
        def level_one():
            return level_two()
        
        # Even with nested calls, the caller should still be this test module
        result_module = level_one()
        expected_module = sys.modules[__name__]
        
        self.assertEqual(result_module, expected_module)


if __name__ == '__main__':
    unittest.main()
