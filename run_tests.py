#!/usr/bin/env python3
"""
PSH Test Runner

This script runs the full PSH test suite in phases, with per-phase process-group
timeouts and failure-safety guarantees (see below), plus an opt-in bash-comparison
phase for the golden behavioral cases.

Usage:
    python run_tests.py                    # Run all tests with smart handling
    python run_tests.py --parallel         # Parallel execution (pytest-xdist)
    python run_tests.py --parallel 8       # Parallel with 8 workers
    python run_tests.py --all-nocapture    # Run ALL tests with -s flag
    python run_tests.py --quick            # Curated fast smoke subset (parallel)
    python run_tests.py --help             # Show help

Failure-safety guarantees (reappraisal #18 Tier-3 hardening):
    * Every phase runs under a per-phase timeout in its own process group; a
      wedged run is killed (group-wide) and reported as a FAILURE rather than
      hanging the gate forever.
    * Child output is captured to a real file, not an inherited pipe, so an
      orphaned background process (e.g. a leaked ``sleep``) that keeps the
      output fd open can never wedge the reader.
    * ``INTERNALERROR>`` output is NEVER stripped — a pytest internal error is
      surfaced verbatim and forced to a FAILURE.
    * A phase reports success ONLY when pytest exits 0 with no internal error.
      The sole exception is the benign pytest-xdist teardown race (exit 3 +
      "cannot send (already closed?)"), and only when the run is provably
      all-green (clean passed summary, no failures/errors, no worker loss).
    * The complete run output is streamed to a results file so failures are
      inspectable without re-running the suite.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Failure-safety constants -------------------------------------------------

# Per-phase wall-clock backstop. A healthy phase completes in well under a
# minute (~23s for the whole parallel Phase 1); this generous default only
# fires when a phase is genuinely wedged. Override with --timeout.
DEFAULT_PHASE_TIMEOUT = 1800  # seconds

# Conventional "command timed out" exit status (matches coreutils `timeout`).
TIMEOUT_EXIT = 124

# --- Quick smoke tier ---------------------------------------------------------
#
# `--quick` runs a curated, genuinely small smoke subset (finding C3 of the
# 2026-07-06 tests/docs appraisal): the whole unit tree plus the fast,
# in-process integration areas — no serial/subprocess-heavy dirs (redirection,
# subshells, job_control, interactive, scripting), no performance suite. It
# runs in parallel by default so it finishes in well under a minute (~8,300
# tests in ~20s on a laptop) and is meant for tight local iteration, NOT as the
# release gate. The gate remains `python run_tests.py --parallel` (all phases).
QUICK_PATHS = [
    'tests/unit/',
    'tests/integration/control_flow/',
    'tests/integration/parameter_expansion/',
    'tests/integration/arrays/',
    'tests/integration/functions/',
    'tests/integration/variables/',
    'tests/integration/pipeline/',
]

# Markers we key failure/masking decisions on.
INTERNALERROR_TOKEN = 'INTERNALERROR>'
XDIST_TEARDOWN_RACE = 'cannot send (already closed?)'
# Patterns that indicate a lost/crashed xdist worker (an incomplete run whose
# surviving summary must NOT be trusted as all-green). Anchored to xdist's real
# line formats — matched at line start (optionally behind a "[gwN]" prefix) —
# so ordinary output cannot trip them: a test NAMED "..._crashed_worker" or a
# skip reason containing "node crashed" appears mid-line, never as one of these
# whole-line crash reports. Conservative by design: we would rather treat a
# real crash as a failure than false-fail an otherwise-green run.
_WORKER_LOSS_PATTERNS = (
    # "[gw3] node down: Not properly terminated" / "node down: ..."
    re.compile(r'^\s*(?:\[gw\d+\]\s*)?node down\b', re.MULTILINE | re.IGNORECASE),
    # "Replacing crashed worker gw3"
    re.compile(r'^\s*replacing crashed worker\b', re.MULTILINE | re.IGNORECASE),
    # "worker gw0 crashed while running '<nodeid>'"
    re.compile(r'^\s*worker gw\d+ crashed\b', re.MULTILINE | re.IGNORECASE),
)


def _has_worker_loss(output):
    """True if *output* shows an xdist worker crash/node-down (see patterns)."""
    return any(pat.search(output) for pat in _WORKER_LOSS_PATTERNS)

# The persisted results file (relative to this script) unless --results-file
# overrides it. Complete run output is mirrored here so failures are
# inspectable without re-running.
DEFAULT_RESULTS_FILE = Path(__file__).parent / 'tmp' / 'last-test-run.txt'


# --- Output plumbing ----------------------------------------------------------

# Open results file handle; every emit() mirrors here so the persisted file is
# a complete transcript of the run.
_RESULTS_FH = None


def emit(text=""):
    """Print *text* to stdout AND mirror it into the persisted results file.

    Using a single sink for all runner output means the results file is a
    faithful, complete transcript — nothing the user sees on the terminal is
    absent from the file, and vice versa.
    """
    print(text)
    if _RESULTS_FH is not None:
        _RESULTS_FH.write(text)
        _RESULTS_FH.write("\n")
        _RESULTS_FH.flush()


# --- Subprocess execution + exit-code classification --------------------------


def _kill_process_group(proc):
    """SIGKILL *proc*'s whole process group, then reap the direct child.

    The child was started with ``preexec_fn=os.setpgrp`` so it leads its own
    process group (pgid == pid) while keeping the controlling terminal. Killing
    the group — rather than just the direct child — also reaps grandchildren
    (xdist workers, spawned ``python -m psh`` instances, a leaked background
    ``sleep``) that would otherwise linger after a timeout.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Group gone or unkillable — fall back to the direct child.
        try:
            proc.kill()
        except OSError:
            pass
    # Reap so we do not leave a zombie. The child is dead (SIGKILL), so this is
    # bounded; guard it with a timeout anyway for defence in depth.
    try:
        proc.wait(timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        try:
            proc.kill()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass


def _is_provably_all_green(output):
    """True only if *output* proves the run finished fully and all-green.

    Requires a pytest summary that reports passes with zero failures/errors AND
    no sign of a lost/crashed xdist worker. This is deliberately conservative:
    a worker that crashes mid-run leaves a surviving summary that may show only
    passes, so we must reject any crash marker regardless of the summary.
    """
    if _has_worker_loss(output):
        return False
    counts = parse_summary_counts(output)
    if not counts or 'passed' not in counts:
        return False
    if counts.get('failed', 0) or counts.get('errors', 0):
        return False
    return True


def classify_phase_result(returncode, output, parallel):
    """Map a pytest phase result to ``(phase_exit, note)``.

    ``phase_exit`` is 0 only for a genuinely successful phase; any other value
    is a FAILURE. ``note`` is a human-readable explanation (or '').

    Guiding rule: a phase passes ONLY when pytest exits 0 with no internal
    error in its output. The single exception is the benign pytest-xdist
    teardown race (exit 3 + "cannot send (already closed?)"), and even that is
    honoured only when the run is provably all-green (clean passed summary, no
    failures/errors, no worker loss, no other internal error). Every other
    abnormal exit — including a bare internal error — is a FAILURE.

    This is a PURE function (no I/O) so it can be unit-tested directly; see
    tests/unit/tooling/test_run_tests_hardening.py.
    """
    has_internalerror = INTERNALERROR_TOKEN in output

    if returncode == 0:
        # A clean exit must not carry an internal error. pytest normally exits
        # 3 for INTERNALERROR, but never trust a swallowed one.
        if has_internalerror:
            return 1, ("❌ pytest exited 0 but its output contains "
                       "INTERNALERROR — treating as FAILURE.")
        return 0, ""

    # Benign pytest-xdist teardown race: exit 3 with the known channel-close
    # message, and only when the run is provably complete and all-green.
    if parallel and returncode == 3 and XDIST_TEARDOWN_RACE in output:
        if _is_provably_all_green(output):
            return 0, ("⚠️  pytest-xdist teardown race (exit 3, "
                       "'cannot send (already closed?)') with a clean all-green "
                       "summary and no worker loss — treated as PASS.")
        return returncode, ("❌ exit 3 with 'cannot send (already closed?)' "
                            "but the run is NOT provably all-green "
                            "(failures/errors/worker-loss) — treating as "
                            "FAILURE.")

    # Any other nonzero exit is a failure. Call out internal errors loudly.
    if has_internalerror:
        return returncode, (f"❌ pytest INTERNAL ERROR (exit {returncode}) "
                            f"— see INTERNALERROR output above. FAILURE.")
    return returncode, ""


def run_command(cmd, description, env=None, parallel=False,
                timeout=DEFAULT_PHASE_TIMEOUT):
    """Run a pytest phase and return ``(phase_exit, output)``.

    Output is captured to a real temporary file (never an inherited pipe): an
    orphaned grandchild that keeps the output fd open therefore cannot wedge
    the reader, because ``proc.wait()`` only waits for the direct child and a
    file fd never blocks. The captured output is echoed verbatim (INTERNALERROR
    lines included) and mirrored to the persisted results file.

    The phase runs in its own process group under *timeout*; on timeout the
    whole group is killed and the phase is reported as a FAILURE.
    """
    emit(f"\n{'=' * 80}")
    emit(f"Running: {description}")
    emit(f"Command: {' '.join(cmd)}")
    emit(f"(timeout: {timeout}s, own process group)")
    emit('=' * 80)

    timed_out = False
    with tempfile.TemporaryFile() as tmp:
        proc = subprocess.Popen(
            cmd, cwd=Path(__file__).parent, env=env,
            stdout=tmp, stderr=subprocess.STDOUT,
            # New process group (same session → controlling terminal preserved)
            # so a timeout can group-kill without killing this runner.
            preexec_fn=os.setpgrp,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc)
        except BaseException:
            # KeyboardInterrupt (Ctrl-C), SystemExit, or any early exit while a
            # phase is running: kill the whole process group before propagating
            # so the child pytest and its xdist workers / spawned `python -m psh`
            # instances are not orphaned. The timeout path above already does
            # this; this closes the interrupt gap (appraisal finding C4).
            _kill_process_group(proc)
            raise
        tmp.seek(0)
        output = tmp.read().decode('utf-8', errors='replace')

    # Echo the phase output verbatim — NEVER strip INTERNALERROR.
    emit(output.rstrip('\n'))

    if timed_out:
        emit(f"\n❌ TIMEOUT: '{description}' exceeded {timeout}s. "
             f"Killed the process group and reporting FAILURE "
             f"(exit {TIMEOUT_EXIT}).")
        return TIMEOUT_EXIT, output

    phase_exit, note = classify_phase_result(proc.returncode, output, parallel)
    if note:
        emit(note)
    return phase_exit, output


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
                # pytest pluralizes ONLY "error" — a single erroring test is
                # written "1 error" (verified live), so match the singular too;
                # missing it would let a lone error slip through the all-green
                # guard. ("failed" is invariant; "1 failed" already matches.)
                token = 'errors?' if field == 'errors' else field
                # \b keeps "failed" from matching inside "xfailed"
                m = re.search(rf'(\d+) {token}\b', line)
                if m:
                    counts[field] = int(m.group(1))
            if counts:
                return counts
    return counts


def golden_case_counts():
    """(total, psh_only, comparisons) read from golden_cases.yaml at runtime.

    The compare-bash phase runs one psh-vs-bash comparison per non-``psh_only``
    golden case. Reporting a hardcoded total drifted every time a case was added
    (the banner froze at 1,119 and was 188 cases stale before this was
    computed). ``comparisons`` is ``total - psh_only``. Returns ``(0, 0, 0)`` if
    pyyaml or the file is unavailable so the banner degrades gracefully rather
    than crashing the run.
    """
    try:
        import yaml
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'tests', 'behavioral', 'golden_cases.yaml')
        with open(path) as f:
            cases = yaml.safe_load(f)
        total = len(cases)
        psh_only = sum(1 for c in cases if c.get('psh_only', False))
        return total, psh_only, total - psh_only
    except Exception:
        return 0, 0, 0


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

    emit("\n" + "=" * 80)
    emit("SKIP/XFAIL CENSUS")
    emit("=" * 80)
    total_skips = sum(skip_reasons.values())
    emit(f"\nSkipped: {total_skips} (by reason, descending):")
    for reason, count in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
        emit(f"  {count:4d}  {reason}")
    emit(f"\nXfailed: {sum(xfail_reasons.values())} (by reason, descending):")
    for reason, count in sorted(xfail_reasons.items(), key=lambda kv: -kv[1]):
        emit(f"  {count:4d}  {reason}")
    if xpasses:
        emit(f"\nXPASSED (unexpectedly passing — investigate): {len(xpasses)}")
        for test in xpasses:
            emit(f"        {test}")


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
  python run_tests.py --quick            # Curated fast smoke subset (parallel)
  python run_tests.py --verbose          # Verbose output
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
        help='Run a curated fast smoke subset (unit tree + fast integration '
             'areas), in parallel, for local iteration. Not the release gate.'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (show each test)'
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
        '--timeout',
        type=int,
        default=DEFAULT_PHASE_TIMEOUT,
        metavar='SECONDS',
        help=f'Per-phase wall-clock timeout (default: {DEFAULT_PHASE_TIMEOUT}s). '
             'On timeout the phase process group is killed and the phase FAILS.'
    )

    parser.add_argument(
        '--results-file',
        default=str(DEFAULT_RESULTS_FILE),
        metavar='PATH',
        help='Persist the complete run transcript here so failures are '
             f'inspectable without re-running (default: {DEFAULT_RESULTS_FILE}).'
    )

    parser.add_argument(
        'pytest_args',
        nargs='*',
        help='Additional arguments to pass to pytest'
    )

    args = parser.parse_args()

    # Open the persisted results file up front so the ENTIRE transcript
    # (banners, phase output, summary) is mirrored to disk.
    global _RESULTS_FH
    results_path = Path(args.results_file)
    try:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        _RESULTS_FH = open(results_path, 'w', encoding='utf-8')
    except OSError as e:
        # Persistence is best-effort; never let it block the run.
        print(f"WARNING: could not open results file {results_path}: {e}")
        _RESULTS_FH = None

    try:
        return _run(args, results_path)
    finally:
        if _RESULTS_FH is not None:
            _RESULTS_FH.close()


def _run(args, results_path):
    """Execute the selected mode; separated from main() so main() can own the
    results-file lifecycle."""
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
    timeout = args.timeout
    exit_codes = []
    phase_outputs = []

    if _RESULTS_FH is not None:
        emit(f"Persisting full run transcript to: {results_path}")

    if args.quick:
        # Genuine smoke tier: a curated fast subset, run in parallel. Deliberately
        # short-circuits the other modes — see QUICK_PATHS for the rationale.
        workers = args.parallel if args.parallel else 'auto'
        emit("\n" + "=" * 80)
        emit(f"MODE: Quick smoke tier [parser: {parser_label}, parallel={workers}]")
        emit("  Curated subset (unit + fast integration); NOT the release gate.")
        emit("  Full gate: python run_tests.py --parallel")
        emit("=" * 80)

        cmd = base_cmd + QUICK_PATHS + ['-m', 'not serial and not slow',
                                        '-n', workers]
        exit_code, output = run_command(cmd, "Quick smoke tier", env=env,
                                        parallel=True, timeout=timeout)
        exit_codes.append(exit_code)
        phase_outputs.append(output)

    elif args.all_nocapture:
        # Simple mode: run everything with -s
        emit("\n" + "=" * 80)
        emit(f"MODE: Running ALL tests with capture disabled (-s flag) [parser: {parser_label}]")
        emit("=" * 80)

        cmd = base_cmd + ['tests/', '-s']

        exit_code, output = run_command(cmd, "All tests with capture disabled",
                                        env=env, timeout=timeout)
        exit_codes.append(exit_code)
        phase_outputs.append(output)

    else:
        # Smart mode: Run tests in phases
        parallel_label = ""
        if args.parallel:
            parallel_label = f", parallel={args.parallel}"
        emit("\n" + "=" * 80)
        emit(f"MODE: Smart test runner (recommended) [parser: {parser_label}{parallel_label}]")
        emit("  - Phase 1: Regular tests with normal capture")
        if args.parallel:
            emit(f"             (parallelized with {args.parallel} workers)")
        emit("=" * 80)

        # Phase 1: Regular tests. When parallel, exclude `serial`-marked tests
        # (process/signal/job-control and in-process forked-fd tests that can't
        # run concurrently under xdist); they run in Phase 1b. In serial mode
        # they run here inline. Subshell tests (tests/integration/subshells/) are
        # ordinary Phase-1 tests: they pass under normal pytest capture — the -s
        # flag has been unnecessary since v0.195.0, as forked children do
        # fd-level I/O (see tests/integration/subshells/README.md).
        cmd = base_cmd + ['tests/']
        phase1_markers = []
        if args.parallel:
            phase1_markers.append('not serial')
        if phase1_markers:
            cmd.extend(['-m', ' and '.join(phase1_markers)])
        if args.parallel:
            cmd.extend(['-n', args.parallel])

        desc = "Phase 1: Regular tests"
        if args.parallel:
            desc += f" (parallel, {args.parallel} workers, -m 'not serial')"
        else:
            desc += " (with capture)"
        exit_code, output = run_command(cmd, desc, env=env,
                                        parallel=bool(args.parallel),
                                        timeout=timeout)
        exit_codes.append(exit_code)
        phase_outputs.append(output)

        # Phase 1b: serial-marked tests (process/signal/forked-fd). Only needed
        # in parallel mode — they were excluded from Phase 1. Run without xdist.
        if args.parallel:
            cmd = base_cmd + ['tests/']
            cmd.extend(['-m', 'serial'])
            exit_code, output = run_command(
                cmd, "Phase 1b: serial tests (process/signal/forked-fd, no xdist)",
                env=env, timeout=timeout)
            exit_codes.append(exit_code)
            phase_outputs.append(output)

        # Phase 2 (opt-in): golden behavioral cases compared against bash.
        # Gated behind --compare-bash because it requires bash on PATH; the
        # comparison itself is locale-pinned (LC_ALL=C) so it is deterministic.
        #
        # Two runtime optimizations (campaign #21, test_performance appraisal
        # 2026-07-07, items a+b):
        #   (b) DE-DUPLICATE: run ONLY the psh-vs-bash comparison variant
        #       (`test_golden_bash_comparison`). The psh-side assertion
        #       (`test_golden`) ALREADY ran in Phase 1 (test collection includes
        #       tests/behavioral/), so re-running it here was pure duplication.
        #       This CHANGES the phase's canonical count — see the loud banner.
        #       We match by function name (`-k test_golden_bash_comparison`), NOT
        #       `-k comparison`: two case NAMES contain "comparison"
        #       (arith_comparison_*), which `-k comparison` would wrongly also
        #       select as their psh-only test_golden variant.
        #   (a) PARALLELIZE: each comparison case is an isolated psh+bash
        #       subprocess pair with no shared fd/signal/cwd state, so the phase
        #       is xdist-safe. Run it under the same worker count as Phase 1.
        #       Safety proof: the identical psh commands already run concurrently
        #       across all workers as `test_golden` in the green Phase 1.
        if args.compare_bash:
            total, psh_only, comparisons = golden_case_counts()
            emit("\n" + "-" * 80)
            emit("COMPARE-BASH phase (comparison-only; campaign #21, item b):")
            emit("  Runs ONLY the psh-vs-bash comparison variant")
            emit("  (test_golden_bash_comparison), NOT the psh-only test_golden")
            emit("  that already ran in Phase 1. Counts are computed from")
            emit("  tests/behavioral/golden_cases.yaml at runtime (a frozen number")
            emit("  here went 188 cases stale before this became live):")
            emit(f"      {comparisons:,} comparison pairs / {psh_only} skipped "
                 "(psh_only cases)")
            emit(f"      out of {total:,} golden cases total.")
            emit("-" * 80)
            cmd = base_cmd + [
                'tests/behavioral/test_golden_behavior.py',
                '-k', 'test_golden_bash_comparison',
                '--compare-bash',
            ]
            desc = "Phase 2: Golden behavioral comparison vs bash (comparison-only"
            if args.parallel:
                cmd.extend(['-n', args.parallel])
                desc += f", parallel={args.parallel})"
            else:
                desc += ", serial)"
            exit_code, output = run_command(
                cmd, desc, env=env, parallel=bool(args.parallel),
                timeout=timeout)
            exit_codes.append(exit_code)
            phase_outputs.append(output)

    # Optional skip/xfail census
    if args.census:
        print_census(phase_outputs)

    # Summary
    emit("\n" + "=" * 80)
    emit("TEST RUN SUMMARY")
    emit("=" * 80)

    # Combined outcome totals across all phases
    totals = {}
    for output in phase_outputs:
        for field, count in parse_summary_counts(output).items():
            totals[field] = totals.get(field, 0) + count
    if totals:
        combined = ', '.join(
            f"{totals[f]} {f}" for f in _SUMMARY_FIELDS if f in totals)
        emit(f"Combined across {len(phase_outputs)} phase(s): {combined}")

    if _RESULTS_FH is not None:
        emit(f"Full transcript saved to: {results_path}")

    if all(code == 0 for code in exit_codes):
        emit("✅ All test phases PASSED")
        return 0
    else:
        emit("❌ Some test phases FAILED")
        for i, code in enumerate(exit_codes, 1):
            if code == 0:
                status = "✅ PASSED"
            elif code == TIMEOUT_EXIT:
                status = "❌ FAILED (TIMEOUT)"
            else:
                status = "❌ FAILED"
            emit(f"   Phase {i}: {status} (exit code: {code})")
        return 1


if __name__ == '__main__':
    sys.exit(main())
