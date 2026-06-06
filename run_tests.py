#!/usr/bin/env python3
"""
PSH Test Runner

This script runs the full PSH test suite with proper handling for tests that
require special pytest configuration (e.g., subshell tests that need capture disabled).

Usage:
    python run_tests.py                    # Run all tests with smart handling
    python run_tests.py --parallel         # Parallel execution (pytest-xdist)
    python run_tests.py --parallel 8       # Parallel with 8 workers
    python run_tests.py --all-nocapture    # Run ALL tests with -s flag
    python run_tests.py --quick            # Run only fast tests
    python run_tests.py --help             # Show help
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description, env=None, parallel=False):
    """Run a command and return the result.

    When *parallel* is True, the output is captured so we can detect the
    pytest-xdist teardown race (``INTERNALERROR ... cannot send``) that
    produces exit-code 3 even though all tests passed.  In that case we
    report success based on the pytest summary line instead.
    """
    print(f"\n{'=' * 80}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('=' * 80)

    if not parallel:
        result = subprocess.run(cmd, cwd=Path(__file__).parent, env=env)
        return result.returncode

    # In parallel mode, capture output to detect and suppress the known
    # pytest-xdist teardown race (BrokenPipeError / "cannot send").
    result = subprocess.run(
        cmd, cwd=Path(__file__).parent, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    # Strip INTERNALERROR traceback lines — they are xdist teardown noise.
    clean_lines = [
        line for line in result.stdout.splitlines()
        if not line.startswith('INTERNALERROR>')
    ]
    print('\n'.join(clean_lines))

    if result.returncode == 0:
        return 0

    # Exit code 3 with "cannot send (already closed?)" is a known
    # pytest-xdist teardown race — harmless if no tests actually failed.
    if result.returncode == 3 and 'cannot send (already closed?)' in result.stdout:
        # Check whether the summary line reports any real failures.
        # The pytest summary looks like "=== 1739 passed, 264 skipped ... ==="
        # Note: must distinguish "N failed" from "N xfailed" — only the
        # former indicates real test failures.
        for line in reversed(result.stdout.splitlines()):
            if 'passed' in line and re.search(r'(?<!\w)failed(?!\w)', line):
                # Real failures present — print the full output so the
                # user can see what went wrong, then honour the exit code.
                print(result.stdout)
                return result.returncode
            if 'passed' in line:
                # All tests passed (possibly with xfails); teardown noise.
                return 0

    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run PSH tests with proper handling for special test requirements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Smart mode (recommended)
  python run_tests.py --parallel         # Parallel mode (auto worker count)
  python run_tests.py --parallel 8       # Parallel with 8 workers
  python run_tests.py --all-nocapture    # All tests with -s (simpler but noisy)
  python run_tests.py --quick            # Fast tests only
  python run_tests.py --verbose          # Verbose output
  python run_tests.py --subshells-only   # Just subshell tests
        """
    )

    parser.add_argument(
        '--all-nocapture', '-s',
        action='store_true',
        help='Run ALL tests with -s flag (disable capture everywhere). Simpler but loses pytest output capture benefits.'
    )

    parser.add_argument(
        '--quick', '-q',
        action='store_true',
        help='Run only fast tests (skip slow performance tests)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (show each test)'
    )

    parser.add_argument(
        '--subshells-only',
        action='store_true',
        help='Run only subshell tests (with -s flag)'
    )

    parser.add_argument(
        '--no-subshells',
        action='store_true',
        help='Skip subshell tests entirely'
    )

    parser.add_argument(
        '--parallel', '-p',
        nargs='?',
        const='auto',
        default=None,
        metavar='N',
        help='Run Phase 1 tests in parallel using pytest-xdist. '
             'Use "auto" (default) to match CPU count, or specify worker count.'
    )

    parser.add_argument(
        '--combinator',
        action='store_true',
        help='Run tests using the combinator parser instead of recursive descent'
    )

    parser.add_argument(
        'pytest_args',
        nargs='*',
        help='Additional arguments to pass to pytest'
    )

    args = parser.parse_args()

    # Set up environment for subprocess calls
    env = None
    if args.combinator:
        env = os.environ.copy()
        env['PSH_TEST_PARSER'] = 'combinator'

    # Build base pytest command
    base_cmd = ['python', '-m', 'pytest']

    if args.verbose:
        base_cmd.append('-v')

    # Add any extra pytest args
    if args.pytest_args:
        base_cmd.extend(args.pytest_args)

    parser_label = "combinator" if args.combinator else "recursive_descent"
    exit_codes = []

    if args.all_nocapture:
        # Simple mode: run everything with -s
        print("\n" + "=" * 80)
        print(f"MODE: Running ALL tests with capture disabled (-s flag) [parser: {parser_label}]")
        print("=" * 80)

        cmd = base_cmd + ['tests/', '-s']
        if args.quick:
            cmd.extend(['-m', 'not slow'])

        exit_code = run_command(cmd, "All tests with capture disabled", env=env)
        exit_codes.append(exit_code)

    elif args.subshells_only:
        # Just run subshell tests
        print("\n" + "=" * 80)
        print(f"MODE: Running subshell tests only [parser: {parser_label}]")
        print("=" * 80)

        cmd = base_cmd + ['tests/integration/subshells/', '-s']
        exit_code = run_command(cmd, "Subshell tests (with -s)", env=env)
        exit_codes.append(exit_code)

    else:
        # Smart mode: Run tests in phases
        parallel_label = ""
        if args.parallel:
            parallel_label = f", parallel={args.parallel}"
        print("\n" + "=" * 80)
        print(f"MODE: Smart test runner (recommended) [parser: {parser_label}{parallel_label}]")
        print("  - Phase 1: Regular tests with normal capture")
        if args.parallel:
            print(f"             (parallelized with {args.parallel} workers)")
        print("  - Phase 2: Subshell tests with capture disabled (-s, serial)")
        print("=" * 80)

        # Shared ignores: the subshell / -s tests run in their own phases below.
        non_subshell_ignores = [
            '--ignore=tests/integration/subshells/',
            '--ignore=tests/integration/functions/test_function_advanced.py',
            '--ignore=tests/integration/variables/test_variable_assignment.py',
        ]

        # Phase 1: Regular tests. When parallel, exclude `serial`-marked tests
        # (process/signal/job-control and in-process forked-fd tests that can't
        # run concurrently under xdist); they run in Phase 1b. In serial mode
        # they run here inline.
        cmd = base_cmd + ['tests/'] + non_subshell_ignores
        phase1_markers = []
        if args.parallel:
            phase1_markers.append('not serial')
        if args.quick:
            phase1_markers.append('not slow')
        if phase1_markers:
            cmd.extend(['-m', ' and '.join(phase1_markers)])
        if args.parallel:
            cmd.extend(['-n', args.parallel])

        desc = "Phase 1: Regular tests"
        if args.parallel:
            desc += f" (parallel, {args.parallel} workers, -m 'not serial')"
        else:
            desc += " (with capture)"
        exit_code = run_command(cmd, desc, env=env, parallel=bool(args.parallel))
        exit_codes.append(exit_code)

        # Phase 1b: serial-marked tests (process/signal/forked-fd). Only needed
        # in parallel mode — they were excluded from Phase 1. Run without xdist.
        if args.parallel:
            cmd = base_cmd + ['tests/'] + non_subshell_ignores
            serial_markers = ['serial']
            if args.quick:
                serial_markers.append('not slow')
            cmd.extend(['-m', ' and '.join(serial_markers)])
            exit_code = run_command(
                cmd, "Phase 1b: serial tests (process/signal/forked-fd, no xdist)",
                env=env)
            exit_codes.append(exit_code)

        if not args.no_subshells:
            # Phase 2: Run subshell tests with -s
            cmd = base_cmd + [
                'tests/integration/subshells/',
                '-s'
            ]

            exit_code = run_command(cmd, "Phase 2: Subshell tests (with -s)", env=env)
            exit_codes.append(exit_code)

            # Phase 3: Run the other tests that need -s
            cmd = base_cmd + [
                'tests/integration/functions/test_function_advanced.py::test_function_with_subshell',
                'tests/integration/variables/test_variable_assignment.py::test_assignment_with_subshell',
                '-s'
            ]

            exit_code = run_command(cmd, "Phase 3: Other tests needing -s", env=env)
            exit_codes.append(exit_code)

    # Summary
    print("\n" + "=" * 80)
    print("TEST RUN SUMMARY")
    print("=" * 80)

    if all(code == 0 for code in exit_codes):
        print("✅ All test phases PASSED")
        return 0
    else:
        print("❌ Some test phases FAILED")
        for i, code in enumerate(exit_codes, 1):
            status = "✅ PASSED" if code == 0 else "❌ FAILED"
            print(f"   Phase {i}: {status} (exit code: {code})")
        return 1


if __name__ == '__main__':
    sys.exit(main())
