#!/usr/bin/env python3
"""Campus Test Runner

A flexible test runner for the Campus project that supports different test categories
and modules with a unified interface.

Usage:
    python tests/run_tests.py unit                    # Run all unit tests
    python tests/run_tests.py integration             # Run all integration tests
    python tests/run_tests.py all                     # Run all tests
    python tests/run_tests.py unit --module apps      # Run unit tests for apps module
    python tests/run_tests.py integration -v          # Run integration tests with verbose output

Supported modules: apps, vault, yapper, common, client
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_unittest_discover(test_path: str, verbose: bool = False) -> int:
    """Run unittest discover on the specified path.
    
    Args:
        test_path: Path to discover tests in (relative to project root)
        verbose: Whether to run with verbose output
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    cmd = ["poetry", "run", "python", "-m", "unittest", "discover", test_path]
    if verbose:
        cmd.append("-v")
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode
    except FileNotFoundError:
        print("Error: poetry not found. Make sure poetry is installed and in PATH.")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Campus Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/run_tests.py unit                    # All unit tests
  python tests/run_tests.py integration             # All integration tests  
  python tests/run_tests.py all                     # All tests
  python tests/run_tests.py unit --module apps      # Unit tests for apps only
  python tests/run_tests.py integration --module vault -v  # Verbose integration tests for vault

Supported modules: apps, vault, yapper, common, client
        """
    )
    
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "all"],
        help="Type of tests to run"
    )
    
    parser.add_argument(
        "--module", "-m",
        choices=["apps", "vault", "yapper", "common", "client"],
        help="Specific module to test"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Build test path based on arguments
    test_path = ""  # Initialize variable
    
    if args.test_type == "all":
        if args.module:
            print("Error: --module cannot be used with 'all' test type")
            return 1
        test_path = "tests"
        print("Running all tests (unit + integration)")
    elif args.test_type == "unit":
        if args.module:
            test_path = f"tests/unit/{args.module}"
            print(f"Running unit tests for {args.module} module")
        else:
            test_path = "tests/unit"
            print("Running all unit tests")
    elif args.test_type == "integration":
        if args.module:
            test_path = f"tests/integration/{args.module}"
            print(f"Running integration tests for {args.module} module")
        else:
            test_path = "tests/integration"
            print("Running all integration tests")
    
    # Check if test path exists
    full_test_path = project_root / test_path
    if not full_test_path.exists():
        print(f"Error: Test path '{test_path}' does not exist")
        return 1
    
    # Run the tests
    exit_code = run_unittest_discover(test_path, args.verbose)
    
    print("=" * 60)
    if exit_code == 0:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
