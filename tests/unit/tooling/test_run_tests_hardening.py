"""Meta-test: the test-runner never translates an abnormal pytest exit into a
"pass".

Reappraisal #18 Tier-3 found that ``run_tests.py`` could mask failures: it
stripped ``INTERNALERROR>`` output and could translate pytest-xdist exit code 3
into success merely because an earlier summary contained "passed". These tests
pin the hardened ``classify_phase_result`` decision (a pure function) so the
masking cannot silently return: a phase reports success ONLY for a clean exit 0
with no internal error, or the narrowly-guarded, provably-all-green xdist
teardown race.
"""

import shutil
import subprocess
import sys
import time

import pytest

import run_tests

GREEN_SUMMARY = "==== 4844 passed, 272 skipped, 1 xfailed in 22.64s ===="
FAIL_SUMMARY = "==== 1 failed, 4843 passed, 272 skipped in 22.64s ===="
ERROR_SUMMARY = "==== 2 errors, 4843 passed in 22.64s ===="
# pytest writes a SINGLE error/failure in the SINGULAR (verified live:
# "==== 1 error in 0.03s ====" / "==== 1 failed in 0.02s ===="). These pin the
# masking hole the T3-2 verifier caught: a lone "1 error" must not slip through.
ONE_ERROR_SUMMARY = "==== 4843 passed, 1 error in 22.64s ===="
ONE_FAILED_SUMMARY = "==== 4843 passed, 1 failed in 22.64s ===="
RACE_LINE = "INTERNALERROR> execnet.gateway_base.RemoteError: cannot send (already closed?)"


def _exit(returncode, output, parallel=False):
    phase_exit, _note = run_tests.classify_phase_result(returncode, output, parallel)
    return phase_exit


# --- Clean success ------------------------------------------------------------

def test_clean_pass_is_success():
    assert _exit(0, GREEN_SUMMARY) == 0


def test_clean_pass_parallel_is_success():
    assert _exit(0, GREEN_SUMMARY, parallel=True) == 0


# --- Ordinary failures ---------------------------------------------------------

def test_exit_1_is_failure():
    assert _exit(1, FAIL_SUMMARY) != 0


def test_exit_2_interrupt_is_failure():
    assert _exit(2, "!!! KeyboardInterrupt !!!") != 0


def test_exit_5_no_tests_collected_is_failure():
    assert _exit(5, "no tests ran in 0.01s") != 0


# --- INTERNALERROR is never masked --------------------------------------------

def test_internalerror_forced_failure_even_on_exit_0():
    # A swallowed internal error alongside a clean rc must NOT pass.
    output = GREEN_SUMMARY + "\n" + "INTERNALERROR> RuntimeError: boom"
    assert _exit(0, output) != 0


def test_internalerror_on_nonzero_is_failure():
    output = "INTERNALERROR> KeyError: 'x'\n" + GREEN_SUMMARY
    assert _exit(3, output) != 0


def test_internalerror_serial_phase_not_translated():
    # rc-3 translation is parallel-only; a serial-phase internal error fails.
    output = RACE_LINE + "\n" + GREEN_SUMMARY
    assert _exit(3, output, parallel=False) != 0


# --- xdist teardown race: benign vs. dangerous --------------------------------

def test_benign_teardown_race_is_pass():
    # exit 3 + "cannot send" + clean all-green summary + no worker loss.
    output = "\n".join([GREEN_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) == 0


def test_teardown_race_with_failures_is_failure():
    output = "\n".join([FAIL_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_errors_is_failure():
    output = "\n".join([ERROR_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_single_error_is_failure():
    # NIT-1: a lone "1 error" (singular) must NOT be masked as all-green.
    output = "\n".join([ONE_ERROR_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_single_failed_is_failure():
    output = "\n".join([ONE_FAILED_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_scary_test_name_is_still_pass():
    # NIT-2: ordinary output containing "crashed"/"node crashed" (a -v test line
    # named for crash recovery, a skip reason) must NOT flip a benign race to
    # red — only anchored xdist crash reports count as worker loss.
    output = "\n".join([
        "tests/x.py::test_recover_from_crashed_worker_node_down PASSED",
        "SKIPPED [1] tests/y.py:3: skip because node crashed earlier",
        GREEN_SUMMARY,
        RACE_LINE,
    ])
    assert _exit(3, output, parallel=True) == 0


def test_teardown_race_with_worker_crash_is_failure():
    # Worker loss → surviving summary may show only passes; must NOT be trusted.
    output = "\n".join([
        "[gw3] node down: Not properly terminated",
        "Replacing crashed worker gw3",
        GREEN_SUMMARY,
        RACE_LINE,
    ])
    assert _exit(3, output, parallel=True) != 0


def test_exit_3_without_race_marker_is_failure():
    # A generic internal error (no teardown-race marker) is never translated.
    output = GREEN_SUMMARY
    assert _exit(3, output, parallel=True) != 0


def test_exit_3_race_without_summary_is_failure():
    # No parseable summary → not provably all-green → failure.
    output = RACE_LINE
    assert _exit(3, output, parallel=True) != 0


# --- _is_provably_all_green edge cases ----------------------------------------

def test_provably_green_accepts_clean_summary():
    assert run_tests._is_provably_all_green(GREEN_SUMMARY) is True


def test_provably_green_rejects_failures():
    assert run_tests._is_provably_all_green(FAIL_SUMMARY) is False


def test_provably_green_rejects_crash_marker():
    assert run_tests._is_provably_all_green("worker gw0 crashed\n" + GREEN_SUMMARY) is False


def test_provably_green_rejects_missing_summary():
    assert run_tests._is_provably_all_green("collecting ...") is False


def test_provably_green_rejects_single_error():
    assert run_tests._is_provably_all_green(ONE_ERROR_SUMMARY) is False


def test_provably_green_rejects_single_failed():
    assert run_tests._is_provably_all_green(ONE_FAILED_SUMMARY) is False


def test_worker_loss_detection_anchored():
    # Real xdist crash reports trip detection...
    assert run_tests._has_worker_loss("[gw3] node down: Not properly terminated")
    assert run_tests._has_worker_loss("Replacing crashed worker gw3")
    assert run_tests._has_worker_loss("worker gw0 crashed while running 'x::y'")
    # ...but mid-line mentions in ordinary output do not.
    assert not run_tests._has_worker_loss(
        "tests/x.py::test_recover_from_crashed_worker PASSED")
    assert not run_tests._has_worker_loss("SKIPPED: node crashed last week")


# --- NIT-3: pin the actual run_command hardening (timeout / killpg / file
# capture). These spawn subprocesses, so they are serial-marked. Without them a
# "remove the timeout/kill" regression would pass silently against the pure
# classifier tests above.

@pytest.mark.serial
def test_run_command_timeout_kills_whole_process_group(monkeypatch):
    """A wedged child (and its grandchild) is killed at the timeout — the
    runner returns TIMEOUT_EXIT promptly and leaves NO orphan."""
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    marker = "PSH_RUNTESTS_KILLPG_PROBE_GRANDCHILD"
    # Direct child forks a grandchild that re-execs with a findable argv marker;
    # both sleep 60s. The grandchild inherits the child's process group (set by
    # run_command's preexec_fn=os.setpgrp), so a group-kill must reap it too.
    inner = (
        "import os,sys,time\n"
        "if os.fork()==0:\n"
        f"    os.execv(sys.executable,[sys.executable,'-c',"
        f"'import time; time.sleep(60)','{marker}'])\n"
        "time.sleep(60)\n"
    )
    t0 = time.time()
    rc, _out = run_tests.run_command([sys.executable, '-c', inner],
                                     'killpg probe', timeout=2)
    elapsed = time.time() - t0
    assert rc == run_tests.TIMEOUT_EXIT
    assert elapsed < 25, f"did not honour the 2s timeout (took {elapsed:.1f}s)"
    if shutil.which('pgrep'):
        time.sleep(0.5)  # let the OS tear the group down
        found = subprocess.run(['pgrep', '-f', marker],
                               capture_output=True, text=True)
        assert found.returncode != 0, (
            f"orphaned grandchild survived the group-kill: {found.stdout!r}")


@pytest.mark.serial
def test_run_command_orphan_holding_output_does_not_wedge(monkeypatch):
    """An orphaned grandchild that keeps the output fd open must NOT wedge the
    reader (the disown-hang class). File-capture makes run_command return as
    soon as the direct child exits; a regression to a PIPE would block until
    the orphan dies (~12s here)."""
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    inner = (
        "import os,sys,time\n"
        "if os.fork()==0:\n"
        "    time.sleep(12)\n"        # orphan keeps fd1 open, outlives parent
        "    os._exit(0)\n"
        "print('child-done', flush=True)\n"
        "os._exit(0)\n"
    )
    t0 = time.time()
    rc, out = run_tests.run_command([sys.executable, '-c', inner],
                                    'orphan probe', timeout=30)
    elapsed = time.time() - t0
    assert 'child-done' in out
    assert elapsed < 6, f"run_command wedged on an orphan-held pipe ({elapsed:.1f}s)"
    assert rc == 0
