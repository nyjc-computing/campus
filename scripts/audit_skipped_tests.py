#!/usr/bin/env python3
"""Audit @unittest.skip markers: run skipped tests and report stale ones.

Skip markers rot: the underlying bug gets fixed but nobody re-runs the
skipped test to remove its marker. PRs #615 and #617 removed 21 stale
"API BUG" markers found exactly this way - several described bugs that
had been fixed months earlier.

This tool runs skipped tests with the skip neutralized and reports
PASS/FAIL per test, so markers can be re-verified in seconds instead of
through manual archaeology.

IMPORTANT implementation note: @unittest.skip wraps the test function in
a skip_wrapper that raises SkipTest at call time. Flipping
``__unittest_skip__`` on the wrapper is NOT enough - the test still
skips and a naive "did TestResult pass?" check reports a false PASS.
This tool swaps the original function back in via ``__wrapped__``.

Usage:
    python scripts/audit_skipped_tests.py                      # tests/contract
    python scripts/audit_skipped_tests.py tests/integration    # another tree
    python scripts/audit_skipped_tests.py --reason "API BUG"   # filter by marker text

Exit code is always 0 unless the arguments are invalid: this is a triage
report, not a pass/fail gate. PASS lines are stale markers whose skips
can be deleted (after checking the linked issue); FAIL lines are live.
"""

import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path

# Make `tests` and `campus` importable when run as a plain script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def collect_skipped_tests(start_dir: str, reason_filter: str | None):
    """Yield (module, class, method, reason, loader) for skipped tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir, top_level_dir=str(PROJECT_ROOT))
    stack = [suite]
    seen: set[str] = set()
    while stack:
        item = stack.pop()
        if isinstance(item, unittest.TestSuite):
            stack.extend(item)
            continue
        test_id = item.id()
        if not test_id or test_id in seen:
            continue
        seen.add(test_id)
        method_name = getattr(item, "_testMethodName", None)
        if not method_name:
            continue
        func = getattr(type(item), method_name, None)
        if func is None:
            continue
        reason = getattr(func, "__unittest_skip_why__", "") or ""
        if not getattr(func, "__unittest_skip__", False):
            continue
        if reason_filter and reason_filter not in reason:
            continue
        yield test_id, reason, type(item), method_name


def run_one(test_class, method_name) -> tuple[str, str]:
    """Run a single test with setUpClass/tearDownClass. Returns (status, detail)."""
    wrapped = getattr(getattr(test_class, method_name), "__wrapped__", None)
    if wrapped is None:
        return "CANNOT-UNWRAP", "skip decorator did not set __wrapped__"
    setattr(test_class, method_name, wrapped)
    test = unittest.TestLoader().loadTestsFromName(method_name, test_class)
    outcome = io.StringIO()
    with contextlib.redirect_stdout(outcome), contextlib.redirect_stderr(outcome):
        result = unittest.TestSuite([test]).run(unittest.TestResult())
    if result.skipped:
        return "STILL-SKIPPED", "unwrap failed - test skipped anyway"
    if result.wasSuccessful():
        return "PASS", ""
    errors = (result.failures or []) + (result.errors or [])
    detail = ""
    if errors:
        lines = errors[0][1].strip().splitlines()
        detail = lines[-1][:160] if lines else ""
    return "FAIL", detail


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "start_dir", nargs="?", default="tests/contract",
        help="directory to scan (default: tests/contract)")
    parser.add_argument(
        "--reason", default=None,
        help="only audit markers whose reason contains this substring")
    args = parser.parse_args(argv)

    start = str(PROJECT_ROOT / args.start_dir) if not Path(args.start_dir).is_absolute() else args.start_dir
    skipped = list(collect_skipped_tests(start, args.reason))
    if not skipped:
        print(f"No skipped tests found in {args.start_dir}"
              + (f" matching {args.reason!r}" if args.reason else ""))
        return 0

    counts = {"PASS": 0, "FAIL": 0, "STILL-SKIPPED": 0, "CANNOT-UNWRAP": 0}
    for test_id, reason, test_class, method_name in skipped:
        status, detail = run_one(test_class, method_name)
        counts[status] = counts.get(status, 0) + 1
        print(f"{status:5}  {test_id}")
        print(f"       skip reason: {reason}")
        if detail:
            print(f"       {detail}")

    print()
    print(f"Total skipped audited: {len(skipped)} "
          f"(PASS {counts['PASS']}, FAIL {counts['FAIL']}, "
          f"other {counts['STILL-SKIPPED'] + counts['CANNOT-UNWRAP']})")
    if counts["PASS"]:
        print("PASS lines are stale markers: the test passes with the skip "
              "removed - delete the marker (and close/Update the linked issue).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
