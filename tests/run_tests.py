#!/usr/bin/env python3
"""Campus Test Runner

A flexible test runner for the Campus project that supports different test categories
and modules with a unified interface.

Usage:
    python tests/run_tests.py unit                # all unit tests (60s timeout)
    python tests/run_tests.py integration         # all integration tests (300s timeout)
    python tests/run_tests.py all                 # all tests (360s timeout)
    python tests/run_tests.py unit --module apps  # unit tests for apps module
    python tests/run_tests.py integration -v      # integration tests with verbose output
    python tests/run_tests.py unit --timeout 30   # unit tests with 30s timeout
    python tests/run_tests.py unit --no-timeout   # unit tests without timeout (for debugging)

Supported modules: apps, vault, yapper, common, client

Exit Codes:
    0   - All tests passed successfully
    1   - General error (missing poetry, invalid arguments, test path not found)
    2   - Test failures (some tests failed but completed)
    124 - Timeout (tests exceeded time limit)
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_unittest_discover(
        test_path: str,
        verbose: bool = False,
        timeout: int | None = None
) -> int:
    """Run unittest discover on the specified path.

    Args:
        test_path: Path to discover tests in (relative to project root)
        verbose: Whether to run with verbose output
        timeout: Maximum time in seconds to allow tests to run (None for no timeout)

    Returns:
        Exit code:
        - 0: All tests passed
        - 1: Poetry not found or other system error
        - 2: Some tests failed (returned by unittest)
        - 124: Tests timed out
    """
    cmd = ["poetry", "run", "python", "-m", "unittest", "discover", test_path]
    if verbose:
        cmd.append("-v")

    print(f"Running: {' '.join(cmd)}")
    if timeout:
        print(f"Timeout: {timeout} seconds")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, cwd=project_root,
                                check=False, timeout=timeout)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"\n❌ Tests timed out after {timeout} seconds")
        print("This might indicate:")
        print("  - Tests are running too slowly")
        print("  - Tests are hanging or stuck")
        print("  - Network/external dependencies are slow")
        print("\nTip: Run without timeout (--no-timeout) to debug hanging tests")
        return 124  # Standard timeout exit code
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
  python tests/run_tests.py unit                    # All unit tests (60s timeout)
  python tests/run_tests.py integration             # All integration tests (300s timeout)  
  python tests/run_tests.py all                     # All tests (360s timeout)
  python tests/run_tests.py unit --module apps      # Unit tests for apps only
  python tests/run_tests.py integration --module vault -v  # Verbose integration tests for vault
  python tests/run_tests.py unit --timeout 30       # Unit tests with custom 30s timeout
  python tests/run_tests.py unit --no-timeout       # Unit tests without timeout (debugging)

Supported modules: apps, vault, yapper, common, client

Exit codes:
  0   - All tests passed successfully
  1   - General error (missing poetry, invalid arguments, test path not found)
  2   - Test failures (some tests failed but completed)
  124 - Timeout (tests exceeded time limit)
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

    parser.add_argument(
        "--timeout", "-t",
        type=int,
        help="Timeout in seconds (default: 60 for unit tests, 300 for integration tests)"
    )

    parser.add_argument(
        "--no-timeout",
        action="store_true",
        help="Disable timeout (useful for debugging hanging tests)"
    )

    args = parser.parse_args()

    # Determine timeout value
    timeout = None
    if not args.no_timeout:
        if args.timeout:
            timeout = args.timeout
        else:
            # Set sensible defaults matching CI constraints
            if args.test_type == "unit":
                timeout = 60  # 1 minute for unit tests
            elif args.test_type == "integration":
                timeout = 300  # 5 minutes for integration tests
            else:  # "all"
                timeout = 360  # 6 minutes for all tests

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
    exit_code = run_unittest_discover(test_path, args.verbose, timeout)

    print("=" * 60)
    if exit_code == 0:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
