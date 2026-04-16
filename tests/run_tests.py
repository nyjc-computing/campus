#!/usr/bin/env python3
"""Campus Test Runner

A unified, cross-platform test runner for the Campus project.

Supports Windows, Linux, and macOS with automatic platform detection.

Recommended usage (all platforms):
    poetry run python tests/run_tests.py unit              # unit tests
    poetry run python tests/run_tests.py integration       # integration tests
    poetry run python tests/run_tests.py performance       # performance tests
    poetry run python tests/run_tests.py sanity            # sanity checks
    poetry run python tests/run_tests.py type              # type checks (pyright)
    poetry run python tests/run_tests.py all               # all tests

    # With timeout
    poetry run python tests/run_tests.py unit --timeout 60
    poetry run python tests/run_tests.py all --timeout 60  # applies to unit/integration/performance only

    # Other options
    poetry run python tests/run_tests.py unit --module common -v   # specific module, verbose
    poetry run python tests/run_tests.py unit --silent            # minimal output

Exit Codes:
    0   - All tests passed
    1   - General error
    2   - Test failures
    124 - Timeout
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ===== Constants =====
DEFAULT_UNIT_TIMEOUT = 60
DEFAULT_INTEGRATION_TIMEOUT = 300
DEFAULT_PERFORMANCE_TIMEOUT = 600

# Test categories
TEST_CATEGORIES = ["unit", "integration", "performance", "sanity", "type", "all"]
MODULE_CHOICES = ["apps", "vault", "yapper", "common", "client"]

# Platform detection
IS_WINDOWS = sys.platform == "win32"

# Venv binary locations by platform
# Windows uses Scripts/, Unix (Linux/macOS) uses bin/
VENV_BIN_DIR = "Scripts" if IS_WINDOWS else "bin"
PYTHON_EXE = "python.exe" if IS_WINDOWS else "python"
PYRIGHT_EXE = "pyright.exe" if IS_WINDOWS else "pyright"


def get_venv_executable(executable: str) -> Path | None:
    """Get the path to an executable in the venv, if it exists.

    Cross-platform function that checks the correct venv binary directory
    based on the operating system.

    Args:
        executable: Name of the executable WITHOUT extension
                   (e.g., "python", "pyright", not "python.exe")

    Returns:
        Path to the executable, or None if not found
    """
    exe_name = f"{executable}.exe" if IS_WINDOWS else executable
    venv_path = project_root / ".venv" / VENV_BIN_DIR / exe_name
    return venv_path if venv_path.exists() else None


def get_python_executable() -> str:
    """Get the Python executable to use for running tests.

    Priority order:
    1. .venv python (detected via platform-specific path)
    2. System python (for poetry run workflows)

    Returns:
        Path to Python executable as a string
    """
    if venv_python := get_venv_executable("python"):
        return str(venv_python)
    return "python"


def set_test_environment() -> None:
    """Set environment variables for testing."""
    os.environ.setdefault("ENV", "testing")
    os.environ.setdefault("STORAGE_MODE", "1")


def run_command(
    cmd: list[str],
    timeout: int | None = None,
    silent: bool = False,
    cwd: Path | None = None
) -> int:
    """Run a command and return its exit code.

    Args:
        cmd: Command to run (list of strings)
        timeout: Maximum time in seconds (None for no timeout)
        silent: Whether to suppress output
        cwd: Working directory (defaults to project root)

    Returns:
        Exit code from the command
    """
    if cwd is None:
        cwd = project_root

    if not silent:
        print(f"Running: {' '.join(cmd)}")
        if timeout:
            print(f"Timeout: {timeout} seconds")
        print("=" * 60)

    try:
        capture_output = silent
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=False,
            timeout=timeout,
            capture_output=capture_output,
            text=True
        )

        if silent and result.returncode != 0:
            print("Command failed. Output:")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)

        return result.returncode

    except subprocess.TimeoutExpired:
        if silent:
            print(f"Command timed out after {timeout} seconds")
        else:
            print(f"\nTests timed out after {timeout} seconds")
        return 124

    except FileNotFoundError as e:
        print(f"Error: {e.filename} not found")
        return 1

    except Exception as e:
        print(f"Error running command: {e}")
        return 1


def run_unittest_discover(
    test_type: str,
    module: str | None = None,
    verbose: bool = False,
    timeout: int | None = None,
    silent: bool = False
) -> int:
    """Run unittest discover for a test type.

    Args:
        test_type: "unit" or "integration"
        module: Optional specific module to test
        verbose: Enable verbose output
        timeout: Maximum time in seconds
        silent: Suppress output

    Returns:
        Exit code
    """
    set_test_environment()
    python = get_python_executable()

    # Build test path
    if module:
        test_path = f"tests/{test_type}/{module}"
        if not (project_root / test_path).exists():
            print(f"Error: Test path '{test_path}' does not exist")
            return 1
    else:
        test_path = f"tests/{test_type}"

    cmd = [python, "-m", "unittest", "discover", test_path]
    if verbose:
        cmd.append("-v")

    return run_command(cmd, timeout=timeout, silent=silent)


def run_sanity_checks(silent: bool = False) -> int:
    """Run sanity checks from tests/sanity_check.py."""
    set_test_environment()
    python = get_python_executable()
    cmd = [python, "tests/sanity_check.py"]
    return run_command(cmd, timeout=None, silent=silent)


def run_type_checks(silent: bool = False) -> int:
    """Run pyright type checks."""
    set_test_environment()

    if venv_pyright := get_venv_executable("pyright"):
        cmd = [str(venv_pyright), "campus"]
    else:
        cmd = ["pyright", "campus"]

    return run_command(cmd, timeout=None, silent=silent)


def main():
    parser = argparse.ArgumentParser(
        description="Campus Test Runner (Cross-platform: Windows, Linux, macOS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python tests/run_tests.py unit                # Unit tests
  poetry run python tests/run_tests.py integration         # Integration tests
  poetry run python tests/run_tests.py performance         # Performance tests
  poetry run python tests/run_tests.py sanity              # Sanity checks
  poetry run python tests/run_tests.py type                # Type checks
  poetry run python tests/run_tests.py all                 # All tests

  poetry run python tests/run_tests.py unit --timeout 60   # With timeout
  poetry run python tests/run_tests.py unit --module common -v  # Specific module, verbose

Supported modules: apps, vault, yapper, common, client

Cross-platform notes:
  - Automatically detects venv location for your platform
  - Windows: .venv/Scripts/python.exe
  - Linux/macOS: .venv/bin/python

Exit codes:
    0   - All tests passed
    1   - General error
    2   - Test failures
    124 - Timeout
        """
    )

    parser.add_argument(
        "test_type",
        choices=TEST_CATEGORIES,
        help="Type of tests to run"
    )

    parser.add_argument(
        "--module", "-m",
        choices=MODULE_CHOICES,
        help="Specific module to test (only for unit/integration)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--timeout", "-t",
        type=int,
        help="Timeout in seconds for unit/integration tests"
    )

    parser.add_argument(
        "--no-timeout",
        action="store_true",
        help="Disable timeout"
    )

    parser.add_argument(
        "--silent", "-s",
        action="store_true",
        help="Silent mode (minimal output)"
    )

    args = parser.parse_args()

    # Determine timeout value
    timeout = None
    if not args.no_timeout:
        if args.timeout:
            timeout = args.timeout
        elif args.test_type in ("unit", "all"):
            timeout = DEFAULT_UNIT_TIMEOUT
        elif args.test_type == "integration":
            timeout = DEFAULT_INTEGRATION_TIMEOUT
        elif args.test_type == "performance":
            timeout = DEFAULT_PERFORMANCE_TIMEOUT

    # Track results
    exit_code = 0
    results = []

    # Helper to run a test category
    def run_category(name: str, fn) -> None:
        nonlocal exit_code
        if not args.silent:
            print(f"\n{'=' * 60}")
            print(f"Running {name}")
            print('=' * 60)
        code = fn()
        results.append((name, code))
        if code != 0:
            exit_code = code

    # Unit tests
    if args.test_type == "unit":
        exit_code = run_unittest_discover(
            "unit", args.module, args.verbose, timeout, args.silent
        )

    # Integration tests
    elif args.test_type == "integration":
        exit_code = run_unittest_discover(
            "integration", args.module, args.verbose, timeout, args.silent
        )

    # Performance tests
    elif args.test_type == "performance":
        exit_code = run_unittest_discover(
            "performance", args.module, args.verbose, timeout, args.silent
        )

    # Sanity checks
    elif args.test_type == "sanity":
        exit_code = run_sanity_checks(args.silent)

    # Type checks
    elif args.test_type == "type":
        exit_code = run_type_checks(args.silent)

    # All tests
    elif args.test_type == "all":
        if args.module:
            print("Error: --module cannot be used with 'all' test type")
            return 1

        # Run in order: sanity → type → unit → integration
        # (sanity/type are fast, unit/integration may have external deps)

        run_category("sanity checks", lambda: run_sanity_checks(args.silent))
        run_category("type checks", lambda: run_type_checks(args.silent))

        # Unit tests (with timeout)
        run_category(
            "unit tests",
            lambda: run_unittest_discover("unit", None, args.verbose, timeout, args.silent)
        )

        # Integration tests (with timeout)
        run_category(
            "integration tests",
            lambda: run_unittest_discover(
                "integration", None, args.verbose,
                timeout or DEFAULT_INTEGRATION_TIMEOUT, args.silent
            )
        )

        # Performance tests (with timeout)
        run_category(
            "performance tests",
            lambda: run_unittest_discover(
                "performance", None, args.verbose,
                timeout or DEFAULT_PERFORMANCE_TIMEOUT, args.silent
            )
        )

        # Print summary
        if not args.silent:
            print("\n" + "=" * 60)
            print("Summary:")
            for name, code in results:
                status = "PASS" if code == 0 else f"FAIL (exit {code})"
                print(f"  {name}: {status}")

    # Print final result
    if not args.silent:
        print("=" * 60)
        if exit_code == 0:
            print("All tests passed!")
        else:
            print("Some tests failed")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
