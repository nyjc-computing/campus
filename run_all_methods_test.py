import unittest

from tests.shared import init

if __name__ == "__main__":
    # Verbose reporting
    print("Running Campus all_client_methods...")
    init()
    # Discover tests in the 'tests' directory matching the pattern 'test_*.py'
    suite = unittest.TestLoader().discover(start_dir="tests", pattern="all_client_methods.py")
    # Run the discovered tests
    unittest.TextTestRunner(verbosity=2).run(suite)
