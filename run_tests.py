import unittest

from tests.shared import init

if __name__ == "__main__":
    # Verbose reporting
    print("Running Campus test suite...")
    init()
    # Discover tests in the 'tests' directory matching the pattern 'test_*.py'
    suite = unittest.TestLoader().discover(start_dir="tests", pattern="test_*.py")
    # Run the discovered tests
    unittest.TextTestRunner(verbosity=2).run(suite)
