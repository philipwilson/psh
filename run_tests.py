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
    """Run a command and return ``(exit_code, output)``.

    Output is always captured (and echoed) so the final summary can report
    combined pass totals across phases and the ``--census`` mode can parse
    skip/xfail reasons. When *parallel* is True we additionally detect the
    pytest-xdist teardown race (``INTERNALERROR ... cannot send``) that
    produces exit-code 3 even though all tests passed, and report success
    based on the pytest summary line instead.
    """
    print(f"\n{'=' * 80}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('=' * 80)

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
        return 0, result.stdout

    # Exit code 3 with "cannot send (already closed?)" is a known
    # pytest-xdist teardown race — harmless if no tests actually failed.
    if parallel and result.returncode == 3 \
            and 'cannot send (already closed?)' in result.stdout:
        # Check whether the summary line reports any real failures.
        # The pytest summary looks like "=== 1739 passed, 264 skipped ... ==="
        # Note: must distinguish "N failed" from "N xfailed" — only the
        # former indicates real test failures.
        for line in reversed(result.stdout.splitlines()):
            if 'passed' in line and re.search(r'(?<!\w)failed(?!\w)', line):
                # Real failures present — print the full output so the
                # user can see what went wrong, then honour the exit code.
                print(result.stdout)
                return result.returncode, result.stdout
            if 'passed' in line:
                # All tests passed (possibly with xfails); teardown noise.
                return 0, result.stdout

    return result.returncode, result.stdout


# Pytest summary tokens we aggregate across phases, e.g.
# "=== 4844 passed, 272 skipped, 1 xfailed in 22.64s ===".
_SUMMARY_FIELDS = ('passed', 'failed', 'errors', 'skipped',
                   'xfailed', 'xpassed', 'deselected')


def parse_summary_counts(output):
    """Extract test-outcome counts from the LAST pytest summary line."""
    counts = {}
    for line in reversed(output.splitlines()):
        if 'passed' in line or 'failed' in line or 'error' in line:
            for field in _SUMMARY_FIELDS:
                # \b keeps "failed" from matching inside "xfailed"
                m = re.search(rf'(\d+) {field}\b', line)
                if m:
                    counts[field] = int(m.group(1))
            if counts:
                return counts
    return counts


def print_census(phase_outputs):
    """Print a skip/xfail breakdown with reasons, aggregated across phases.

    Parses the ``-rsxX`` short-summary lines:
        SKIPPED [3] tests/foo.py:10: reason text
        XFAIL tests/bar.py::test_x - reason text
        XPASS tests/baz.py::test_y
    """
    skip_reasons = {}
    xfail_reasons = {}
    xpasses = []
    for output in phase_outputs:
        for line in output.splitlines():
            m = re.match(r'SKIPPED \[(\d+)\] [^:]+(?::\d+)?: (.*)', line)
            if m:
                count, reason = int(m.group(1)), m.group(2).strip()
                skip_reasons[reason] = skip_reasons.get(reason, 0) + count
                continue
            m = re.match(r'XFAIL (\S+)(?: - (.*))?', line)
            if m:
                reason = (m.group(2) or '(no reason given)').strip()
                xfail_reasons[reason] = xfail_reasons.get(reason, 0) + 1
                continue
            m = re.match(r'XPASS (\S+)', line)
            if m:
                xpasses.append(m.group(1))

    print("\n" + "=" * 80)
    print("SKIP/XFAIL CENSUS")
    print("=" * 80)
    total_skips = sum(skip_reasons.values())
    print(f"\nSkipped: {total_skips} (by reason, descending):")
    for reason, count in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {reason}")
    print(f"\nXfailed: {sum(xfail_reasons.values())} (by reason, descending):")
    for reason, count in sorted(xfail_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {reason}")
    if xpasses:
        print(f"\nXPASSED (unexpectedly passing — investigate): {len(xpasses)}")
        for test in xpasses:
            print(f"        {test}")


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
        '--compare-bash',
        action='store_true',
        help='Additionally run the golden behavioral cases against bash and '
             'compare output (requires bash on PATH). Adds a comparison phase.'
    )

    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Collect coverage for the psh package across all phases '
             '(pytest-cov; accumulated with --cov-append). Writes coverage.xml '
             'and prints a terminal report. Non-gating.'
    )

    parser.add_argument(
        '--census',
        action='store_true',
        help='Print a skip/xfail breakdown with reasons (aggregated across '
             'phases) after the run.'
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

    if args.census:
        # Short summaries for skips/xfails/xpasses so the census can parse
        # per-test reasons from each phase's output.
        base_cmd.append('-rsxX')

    if args.coverage:
        # Accumulate one coverage database across all phases; the xml/term
        # reports are rewritten per phase, so the LAST phase's reports cover
        # the whole run. Non-gating (no --cov-fail-under).
        coverage_db = Path(__file__).parent / '.coverage'
        if coverage_db.exists():
            coverage_db.unlink()
        base_cmd.extend([
            '--cov=psh', '--cov-append',
            '--cov-report=xml:coverage.xml', '--cov-report=term',
        ])

    # Add any extra pytest args
    if args.pytest_args:
        base_cmd.extend(args.pytest_args)

    parser_label = "combinator" if args.combinator else "recursive_descent"
    exit_codes = []
    phase_outputs = []

    if args.all_nocapture:
        # Simple mode: run everything with -s
        print("\n" + "=" * 80)
        print(f"MODE: Running ALL tests with capture disabled (-s flag) [parser: {parser_label}]")
        print("=" * 80)

        cmd = base_cmd + ['tests/', '-s']
        if args.quick:
            cmd.extend(['-m', 'not slow'])

        exit_code, output = run_command(cmd, "All tests with capture disabled", env=env)
        exit_codes.append(exit_code)
        phase_outputs.append(output)

    elif args.subshells_only:
        # Just run subshell tests
        print("\n" + "=" * 80)
        print(f"MODE: Running subshell tests only [parser: {parser_label}]")
        print("=" * 80)

        cmd = base_cmd + ['tests/integration/subshells/', '-s']
        exit_code, output = run_command(cmd, "Subshell tests (with -s)", env=env)
        exit_codes.append(exit_code)
        phase_outputs.append(output)

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

        # Shared ignore: the subshell tests run in their own -s phase below.
        non_subshell_ignores = [
            '--ignore=tests/integration/subshells/',
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
        exit_code, output = run_command(cmd, desc, env=env, parallel=bool(args.parallel))
        exit_codes.append(exit_code)
        phase_outputs.append(output)

        # Phase 1b: serial-marked tests (process/signal/forked-fd). Only needed
        # in parallel mode — they were excluded from Phase 1. Run without xdist.
        if args.parallel:
            cmd = base_cmd + ['tests/'] + non_subshell_ignores
            serial_markers = ['serial']
            if args.quick:
                serial_markers.append('not slow')
            cmd.extend(['-m', ' and '.join(serial_markers)])
            exit_code, output = run_command(
                cmd, "Phase 1b: serial tests (process/signal/forked-fd, no xdist)",
                env=env)
            exit_codes.append(exit_code)
            phase_outputs.append(output)

        if not args.no_subshells:
            # Phase 2: Run subshell tests with -s
            cmd = base_cmd + [
                'tests/integration/subshells/',
                '-s'
            ]

            exit_code, output = run_command(cmd, "Phase 2: Subshell tests (with -s)", env=env)
            exit_codes.append(exit_code)
            phase_outputs.append(output)

        # Phase 3 (opt-in): golden behavioral cases compared against bash.
        # Gated behind --compare-bash because it requires bash on PATH; the
        # comparison itself is locale-pinned (LC_ALL=C) so it is deterministic.
        if args.compare_bash:
            cmd = base_cmd + [
                'tests/behavioral/test_golden_behavior.py',
                '--compare-bash',
            ]
            exit_code, output = run_command(
                cmd, "Phase 3: Golden behavioral comparison vs bash", env=env)
            exit_codes.append(exit_code)
            phase_outputs.append(output)

    # Optional skip/xfail census
    if args.census:
        print_census(phase_outputs)

    # Summary
    print("\n" + "=" * 80)
    print("TEST RUN SUMMARY")
    print("=" * 80)

    # Combined outcome totals across all phases
    totals = {}
    for output in phase_outputs:
        for field, count in parse_summary_counts(output).items():
            totals[field] = totals.get(field, 0) + count
    if totals:
        combined = ', '.join(
            f"{totals[f]} {f}" for f in _SUMMARY_FIELDS if f in totals)
        print(f"Combined across {len(phase_outputs)} phase(s): {combined}")

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
