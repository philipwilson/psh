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
    python run_tests.py --benchmarks       # Benchmark tier only (serial)
    python run_tests.py --shuffle-seed 7   # Deterministic collection shuffle
    python run_tests.py --parallel --write-attestation  # Gate + attestation
    python run_tests.py --help             # Show help

Failure-safety guarantees (reappraisal #18 Tier-3 hardening; boundary campaign
E1 structured gate results):
    * Every phase runs under a per-phase timeout in its own process group; a
      wedged run is killed (group-wide) and reported as a FAILURE rather than
      hanging the gate forever.
    * Child output is captured to a real file, not an inherited pipe, so an
      orphaned background process (e.g. a leaked ``sleep``) that keeps the
      output fd open can never wedge the reader.
    * ``INTERNALERROR>`` output is NEVER stripped — a pytest internal error is
      surfaced verbatim and forced to a FAILURE.
    * A phase reports success ONLY when pytest exits 0 with no internal error,
      no xdist worker loss, and a valid structured phase manifest (written by
      the ``tools/pytest_phase_manifest`` plugin) whose outcome counts are
      complete and clean. NO nonzero pytest exit is EVER translated to
      success — the historical carve-out for the "benign" xdist teardown race
      is gone (campaign E1); if that race fires, the gate is red and is rerun.
    * A missing, truncated, or internally inconsistent phase manifest is a
      FAILURE independent of the transcript text or the exit status.
    * The complete run output is streamed to a results file so failures are
      inspectable without re-running the suite.
"""

import argparse
import itertools
import json
import os
import platform as platform_mod
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
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

# Structured phase-manifest contract (tools/pytest_phase_manifest.py). The
# values are duplicated here so importing run_tests never imports pytest; a
# tooling test pins the two modules to identical values so they cannot drift
# (tests/unit/tooling/test_run_tests_hardening.py).
MANIFEST_SCHEMA = 1
MANIFEST_OUTCOME_FIELDS = ('passed', 'failed', 'errored', 'skipped',
                           'xfailed', 'xpassed')

# The same-SHA release attestation written by --write-attestation (campaign
# E4) and verified by tools/verify_gate_attestation.py before release tagging.
ATTESTATION_FILENAME = 'gate_attestation.json'
ATTESTATION_SCHEMA = 1
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


def classify_phase_result(returncode, output, parallel):
    """Map a pytest phase result to ``(phase_exit, note)``.

    ``phase_exit`` is 0 only for a genuinely successful phase; any other value
    is a FAILURE. ``note`` is a human-readable explanation (or '').

    Guiding rule (boundary campaign E1): NO nonzero pytest exit is EVER
    translated to success, and an ``INTERNALERROR`` or xdist worker loss is a
    failure regardless of the exit status or how clean the summary text looks.
    The historical carve-out for the "benign" xdist teardown race (exit 3 +
    "cannot send (already closed?)" + a provably all-green summary) is GONE:
    transcript recognition is not evidence of completion — a Codex-review
    counterexample showed the carve-out blessed a run that ALSO carried an
    unrelated second INTERNALERROR. If the race ever fires again, the gate is
    simply red and gets rerun; that is accepted policy, not a
    reclassification.

    This is a PURE function (no I/O) so it can be unit-tested directly; see
    tests/unit/tooling/test_run_tests_hardening.py. The *parallel* flag only
    affects note wording, never the verdict.
    """
    has_internalerror = INTERNALERROR_TOKEN in output

    if returncode == 0:
        # A clean exit must not carry an internal error or a lost worker.
        # pytest normally exits 3 for INTERNALERROR, but never trust a
        # swallowed one; a crashed worker's surviving summary can look green.
        if has_internalerror:
            return 1, ("❌ pytest exited 0 but its output contains "
                       "INTERNALERROR — treating as FAILURE.")
        if _has_worker_loss(output):
            return 1, ("❌ pytest exited 0 but its output reports a "
                       "lost/crashed xdist worker — the run is incomplete. "
                       "FAILURE.")
        return 0, ""

    # Any nonzero exit is a failure — no exceptions. Call out the known
    # teardown race and internal errors loudly so reruns are informed.
    if returncode == 3 and XDIST_TEARDOWN_RACE in output and parallel:
        return returncode, ("❌ pytest INTERNAL ERROR (exit 3) including the "
                            "xdist teardown race ('cannot send (already "
                            "closed?)'). The old all-green carve-out was "
                            "removed (campaign E1): this phase FAILS — rerun "
                            "the gate.")
    if has_internalerror:
        return returncode, (f"❌ pytest INTERNAL ERROR (exit {returncode}) "
                            f"— see INTERNALERROR output above. FAILURE.")
    return returncode, ""


def classify_manifest(manifest_text):
    """Validate a structured phase manifest; return ``(ok, note, counts)``.

    *manifest_text* is the JSON text written by tools/pytest_phase_manifest
    (or ``None`` when the file is missing). The manifest is judged on
    STRUCTURE, never on transcript text:

    * missing manifest            -> FAILURE (the phase cannot prove what ran)
    * unparseable/truncated JSON  -> FAILURE
    * wrong schema / malformed    -> FAILURE
    * EMPTY collection            -> FAILURE (integrator ruling, E1 bounce:
      a phase that ran nothing proves nothing, even at rc 0 — every real
      phase collects tests; pytest itself exits 5 on empty collection)
    * outcome counts that do not sum to the collected-test count -> FAILURE
      (collection loss: a crashed worker leaves collected ids unreported)
    * any failed/errored count    -> FAILURE (defence in depth alongside rc)

    xpassed counts do NOT fail here (integrator ruling, same bounce): a
    non-strict xpass is not a failure in pytest's own semantics, and strict
    xpasses already surface as ``failed``.

    ``counts`` is returned (possibly partial) even on failure so the combined
    summary can still display what is known. PURE function (no I/O).
    """
    if manifest_text is None:
        return False, ("❌ phase manifest MISSING — the phase cannot prove "
                       "what it ran. FAILURE."), {}
    try:
        data = json.loads(manifest_text)
    except (ValueError, TypeError) as e:
        return False, (f"❌ phase manifest unparseable/truncated ({e}). "
                       "FAILURE."), {}
    if not isinstance(data, dict) or data.get('schema') != MANIFEST_SCHEMA:
        return False, ("❌ phase manifest has wrong/missing schema "
                       f"(expected {MANIFEST_SCHEMA}). FAILURE."), {}
    counts = data.get('counts')
    collected = data.get('collected')
    if not isinstance(counts, dict) or not isinstance(collected, list):
        return False, "❌ phase manifest malformed. FAILURE.", {}
    bad_fields = [f for f in MANIFEST_OUTCOME_FIELDS + ('deselected',)
                  if not isinstance(counts.get(f), int)]
    if bad_fields:
        return False, ("❌ phase manifest counts missing/non-integer fields: "
                       f"{', '.join(bad_fields)}. FAILURE."), {}
    if not collected:
        return False, ("❌ phase manifest records an EMPTY collection — the "
                       "phase ran nothing, which proves nothing. "
                       "FAILURE."), counts
    executed = sum(counts[f] for f in MANIFEST_OUTCOME_FIELDS)
    if executed != len(collected):
        return False, (f"❌ phase manifest outcome total ({executed}) != "
                       f"collected count ({len(collected)}) — lost reports / "
                       "collection loss. FAILURE."), counts
    if counts['failed'] or counts['errored']:
        return False, (f"❌ phase manifest records {counts['failed']} failed, "
                       f"{counts['errored']} errored. FAILURE."), counts
    return True, "", counts


def run_command(cmd, description, env=None, parallel=False,
                timeout=DEFAULT_PHASE_TIMEOUT, manifest_path=None):
    """Run a pytest phase and return ``(phase_exit, output, counts)``.

    Output is captured to a real temporary file (never an inherited pipe): an
    orphaned grandchild that keeps the output fd open therefore cannot wedge
    the reader, because ``proc.wait()`` only waits for the direct child and a
    file fd never blocks. The captured output is echoed verbatim (INTERNALERROR
    lines included) and mirrored to the persisted results file.

    When *manifest_path* is given, ``--phase-manifest`` is appended to *cmd*
    and the written manifest is validated with ``classify_manifest``; a
    missing/truncated/inconsistent manifest forces the phase to FAILURE even
    when pytest exited 0 with clean-looking output. ``counts`` is the
    manifest's outcome-count dict ({} when unavailable).

    The phase runs in its own process group under *timeout*; on timeout the
    whole group is killed and the phase is reported as a FAILURE.
    """
    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        cmd = list(cmd) + ['--phase-manifest', str(manifest_path)]
        # A stale manifest from an earlier run must never vouch for this one.
        try:
            manifest_path.unlink()
        except FileNotFoundError:
            pass

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
        return TIMEOUT_EXIT, output, {}

    phase_exit, note = classify_phase_result(proc.returncode, output, parallel)
    if note:
        emit(note)

    counts = {}
    if manifest_path is not None:
        try:
            manifest_text = manifest_path.read_text(encoding='utf-8')
        except OSError:
            manifest_text = None
        manifest_ok, manifest_note, counts = classify_manifest(manifest_text)
        if not manifest_ok:
            emit(manifest_note)
            if phase_exit == 0:
                phase_exit = 1
    return phase_exit, output, counts


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


def pytest_base_cmd():
    """The pytest launcher for every phase.

    ALWAYS this interpreter (``sys.executable``), never a PATH-resolved
    ``python`` (continuation appraisal medium 16 — the runner must gate the
    environment it itself runs in), plus the structured phase-manifest plugin
    (campaign E1) so every phase can write a manifest and honour
    ``--shuffle-seed``.
    """
    return [sys.executable, '-m', 'pytest', '-p', 'tools.pytest_phase_manifest']


# --- Same-SHA release attestation (campaign E4) -------------------------------


def build_attestation(version, gated_commit, gated_tree, phases, ruff,
                      mypy_files, command, timestamp, platform_info):
    """Assemble the attestation document (PURE — all inputs injected).

    The shape is verified by tools/verify_gate_attestation.py before release
    tagging and pinned by tests/unit/tooling/test_gate_attestation.py.
    """
    return {
        'schema': ATTESTATION_SCHEMA,
        'version': version,
        'gated_commit': gated_commit,
        'gated_tree': gated_tree,
        'platform': platform_info,
        'phases': phases,
        'ruff': ruff,
        'mypy_files': mypy_files,
        'timestamp': timestamp,
        'command': command,
    }


def _git_output(repo_root, *args):
    return subprocess.run(['git', *args], cwd=repo_root, capture_output=True,
                          text=True, check=True).stdout.strip()


def _dirty_tracked_paths(repo_root):
    """Paths of tracked files with uncommitted changes, parsed losslessly.

    Uses ``git status --porcelain -z``: NUL-delimited records with no quoting,
    immune to the leading-space hazard of line parsing (a porcelain record for
    an unstaged modification STARTS with a space — a whole-stdout ``strip()``
    ate it and then ``[3:]`` truncated the first path's first character,
    which broke the attestation self-exemption and printed mangled paths;
    E1-bounce Blocker 1, pinned in test_gate_attestation.py). Each record is
    ``XY <path>``; a rename/copy record (``R``/``C``) is followed by one
    extra NUL-terminated field, the ORIGIN path — both sides count as dirty.
    """
    out = subprocess.run(
        ['git', 'status', '--porcelain', '-z', '--untracked-files=no'],
        cwd=repo_root, capture_output=True, text=True, check=True).stdout
    paths = []
    entries = iter(out.split('\0'))
    for entry in entries:
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if status[:1] in ('R', 'C'):
            origin = next(entries, '')
            if origin:
                paths.append(origin)
    return paths


def _read_tree_version(repo_root):
    text = (Path(repo_root) / 'psh' / 'version.py').read_text(encoding='utf-8')
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise ValueError('could not parse __version__ from psh/version.py')
    return m.group(1)


def _run_attestation_checks(repo_root):
    """Run ruff + mypy for the attestation; return (ok, ruff, mypy_files).

    Documented choice (campaign E4): ``--write-attestation`` runs the linter
    and type checker ITSELF rather than trusting the ceremony to fill the
    fields, so a written attestation always testifies to a ruff+mypy-green
    tree. On failure nothing is written and the runner exits nonzero.
    """
    ruff_exe = shutil.which('ruff')
    ruff_cmd = ([ruff_exe] if ruff_exe else [sys.executable, '-m', 'ruff'])
    # Canonical lint scope includes tools/ (E1-bounce ruling R1).
    ruff_cmd += ['check', 'psh', 'tests', 'tools']
    emit(f"Attestation check: {' '.join(ruff_cmd)}")
    ruff_proc = subprocess.run(ruff_cmd, cwd=repo_root, capture_output=True,
                               text=True)
    if ruff_proc.returncode != 0:
        emit("❌ ruff check failed — no attestation written:")
        emit((ruff_proc.stdout + ruff_proc.stderr).strip())
        return False, False, 0

    mypy_cmd = [sys.executable, '-m', 'mypy']
    emit(f"Attestation check: {' '.join(mypy_cmd)}")
    mypy_proc = subprocess.run(mypy_cmd, cwd=repo_root, capture_output=True,
                               text=True)
    mypy_out = (mypy_proc.stdout + mypy_proc.stderr).strip()
    m = re.search(r'no issues found in (\d+) source files', mypy_out)
    if mypy_proc.returncode != 0 or not m:
        emit("❌ mypy failed (or produced no clean summary) — no attestation "
             "written:")
        emit(mypy_out[-2000:])
        return False, True, 0
    return True, True, int(m.group(1))


def write_attestation(repo_root, phases, command):
    """Write ATTESTATION_FILENAME for a fully green gate; return 0/1.

    Refuses when tracked files (other than the attestation itself) are
    modified: ``gated_commit`` must truthfully name the tree that was gated.
    """
    repo_root = Path(repo_root)
    try:
        dirty_paths = _dirty_tracked_paths(repo_root)
    except (subprocess.CalledProcessError, OSError) as e:
        emit(f"❌ cannot determine git state ({e}) — no attestation written.")
        return 1
    dirty_paths = [p for p in dirty_paths if p != ATTESTATION_FILENAME]
    if dirty_paths:
        emit("❌ tracked files are modified — the gate did not run at a "
             "committed tree, so gated_commit would be a lie. No attestation "
             "written:")
        for p in dirty_paths:
            emit(f"    {p}")
        return 1

    checks_ok, ruff_ok, mypy_files = _run_attestation_checks(repo_root)
    if not checks_ok:
        return 1

    attestation = build_attestation(
        version=_read_tree_version(repo_root),
        gated_commit=_git_output(repo_root, 'rev-parse', 'HEAD'),
        gated_tree=_git_output(repo_root, 'rev-parse', 'HEAD^{tree}'),
        phases=phases,
        ruff=ruff_ok,
        mypy_files=mypy_files,
        command=command,
        timestamp=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        platform_info={
            'os': f"{platform_mod.system()} {platform_mod.release()}",
            'python': platform_mod.python_version(),
            'arch': platform_mod.machine(),
        },
    )
    out_path = repo_root / ATTESTATION_FILENAME
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(attestation, f, indent=2, sort_keys=False)
        f.write('\n')
    emit(f"\n✅ Attestation written: {out_path} "
         f"(gated_commit {attestation['gated_commit'][:12]}, "
         f"version {attestation['version']}). Commit it as the FINAL commit "
         "before pushing — release-tag.yml refuses to tag without it.")
    return 0


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
        '--benchmarks',
        action='store_true',
        help='Run ONLY the benchmark tier: `benchmark`-marked CPU/wall-time '
             'microbenchmarks (tests/performance), serially (no xdist). These '
             'are excluded from every standard-gate phase so millisecond '
             'thresholds never flake the gate; intended for nightly/explicit '
             'runs.'
    )

    parser.add_argument(
        '--shuffle-seed',
        type=int,
        default=None,
        metavar='N',
        help='Deterministically shuffle collected tests in EVERY phase '
             '(including the serial phase) via the phase-manifest plugin '
             '(random.Random(N)). Used for the campaign Phase-E exit: three '
             'standard runs under three seeds must produce identical '
             'collection/outcome censuses.'
    )

    parser.add_argument(
        '--write-attestation',
        action='store_true',
        help='On a fully green run, also run ruff+mypy and write '
             f'{ATTESTATION_FILENAME} at the repo root (campaign E4). '
             'release-tag.yml refuses to tag a version bump without a '
             'matching attestation.'
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

    # The attestation testifies to the STANDARD gate (campaign E4): a green
    # quick/benchmark/all-nocapture run must never mint release evidence.
    if args.write_attestation and (args.quick or args.all_nocapture
                                   or args.benchmarks):
        parser.error('--write-attestation is only valid for the standard '
                     'gate (use: python run_tests.py --parallel '
                     '--write-attestation)')

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

    # Build base pytest command. sys.executable + manifest plugin — see
    # pytest_base_cmd().
    base_cmd = pytest_base_cmd()

    if args.shuffle_seed is not None:
        base_cmd.extend(['--shuffle-seed', str(args.shuffle_seed)])

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
    phase_records = []  # [{'description':…, 'exit':…, 'counts':…}] per phase

    # Structured phase manifests (campaign E1): one JSON file per phase under
    # tmp/phase-manifests/. Load-bearing — creation failures propagate loudly.
    manifest_dir = Path(__file__).parent / 'tmp' / 'phase-manifests'
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_seq = itertools.count(1)

    def run_phase(cmd, description, parallel=False):
        manifest_path = manifest_dir / f'phase-{next(manifest_seq)}.json'
        exit_code, output, counts = run_command(
            cmd, description, env=env, parallel=parallel, timeout=timeout,
            manifest_path=manifest_path)
        exit_codes.append(exit_code)
        phase_outputs.append(output)
        phase_records.append({'description': description, 'exit': exit_code,
                              'counts': counts})

    if _RESULTS_FH is not None:
        emit(f"Persisting full run transcript to: {results_path}")

    if args.benchmarks:
        # Benchmark tier: timing-threshold microbenchmarks, serial by design
        # (they are also `serial`-marked so a bare `pytest -n auto` never runs
        # them concurrently). Deliberately NOT part of the standard gate.
        emit("\n" + "=" * 80)
        emit(f"MODE: Benchmark tier (serial) [parser: {parser_label}]")
        emit("  CPU/wall-time microbenchmarks (-m benchmark); excluded from")
        emit("  the standard gate. See docs/testing_source_of_truth.md.")
        emit("=" * 80)

        cmd = base_cmd + ['tests/', '-m', 'benchmark']
        run_phase(cmd, "Benchmark tier (serial)")

    elif args.quick:
        # Genuine smoke tier: a curated fast subset, run in parallel. Deliberately
        # short-circuits the other modes — see QUICK_PATHS for the rationale.
        workers = args.parallel if args.parallel else 'auto'
        emit("\n" + "=" * 80)
        emit(f"MODE: Quick smoke tier [parser: {parser_label}, parallel={workers}]")
        emit("  Curated subset (unit + fast integration); NOT the release gate.")
        emit("  Full gate: python run_tests.py --parallel")
        emit("=" * 80)

        cmd = base_cmd + QUICK_PATHS + ['-m',
                                        'not serial and not slow and not benchmark',
                                        '-n', workers]
        run_phase(cmd, "Quick smoke tier", parallel=True)

    elif args.all_nocapture:
        # Simple mode: run everything with -s (including the benchmark tier —
        # this diagnostic mode really does mean ALL tests, serially).
        emit("\n" + "=" * 80)
        emit(f"MODE: Running ALL tests with capture disabled (-s flag) [parser: {parser_label}]")
        emit("=" * 80)

        cmd = base_cmd + ['tests/', '-s']

        run_phase(cmd, "All tests with capture disabled")

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
        # they run here inline. `benchmark`-marked timing tests are excluded
        # from EVERY gate phase (they run in the --benchmarks tier), so
        # removing the old pytest.ini performance ignore did not import
        # millisecond thresholds into the gate. Subshell tests
        # (tests/integration/subshells/) are ordinary Phase-1 tests: they pass
        # under normal pytest capture — the -s flag has been unnecessary since
        # v0.195.0, as forked children do fd-level I/O (see
        # tests/integration/subshells/README.md).
        cmd = base_cmd + ['tests/']
        if args.parallel:
            phase1_marker = 'not serial and not benchmark'
        else:
            phase1_marker = 'not benchmark'
        cmd.extend(['-m', phase1_marker])
        if args.parallel:
            cmd.extend(['-n', args.parallel])

        desc = "Phase 1: Regular tests"
        if args.parallel:
            desc += f" (parallel, {args.parallel} workers, -m '{phase1_marker}')"
        else:
            desc += " (with capture)"
        run_phase(cmd, desc, parallel=bool(args.parallel))

        # Phase 1b: serial-marked tests (process/signal/forked-fd). Only needed
        # in parallel mode — they were excluded from Phase 1. Run without xdist.
        if args.parallel:
            cmd = base_cmd + ['tests/']
            cmd.extend(['-m', 'serial and not benchmark'])
            run_phase(
                cmd,
                "Phase 1b: serial tests (process/signal/forked-fd, no xdist)")

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
            run_phase(cmd, desc, parallel=bool(args.parallel))

    # Optional skip/xfail census
    if args.census:
        print_census(phase_outputs)

    # Summary
    emit("\n" + "=" * 80)
    emit("TEST RUN SUMMARY")
    emit("=" * 80)

    # Combined outcome totals across all phases, from the structured phase
    # manifests (never re-parsed from transcript text). `deselected` is
    # deliberately EXCLUDED from the combined tally — the compare-bash -k
    # filter and --quick's -m selection produce large deselection counts that
    # only inflate the banner (TESTINF-6); per-phase deselection is still
    # recorded in each manifest.
    totals = {}
    unmanifested = []
    for i, record in enumerate(phase_records, 1):
        if record['counts']:
            for field in MANIFEST_OUTCOME_FIELDS:
                totals[field] = totals.get(field, 0) + record['counts'][field]
        else:
            unmanifested.append(i)
    if totals:
        combined = ', '.join(
            f"{totals[f]} {f}" for f in MANIFEST_OUTCOME_FIELDS if totals[f])
        emit(f"Combined across {len(phase_records)} phase(s) "
             f"(from phase manifests): {combined}")
    if unmanifested:
        emit(f"⚠️  No usable manifest for phase(s) "
             f"{', '.join(map(str, unmanifested))} — totals are partial.")

    if _RESULTS_FH is not None:
        emit(f"Full transcript saved to: {results_path}")

    if all(code == 0 for code in exit_codes):
        emit("✅ All test phases PASSED")
        if args.write_attestation:
            return write_attestation(Path(__file__).parent, phase_records,
                                     ' '.join([Path(sys.argv[0]).name]
                                              + sys.argv[1:]))
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
        if args.write_attestation:
            emit("❌ --write-attestation: refusing — the gate is not green.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
