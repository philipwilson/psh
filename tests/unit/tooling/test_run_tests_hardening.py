"""Meta-test: the test-runner never translates an abnormal pytest exit into a
"pass".

Reappraisal #18 Tier-3 found that ``run_tests.py`` could mask failures: it
stripped ``INTERNALERROR>`` output and could translate pytest-xdist exit code 3
into success merely because an earlier summary contained "passed".

Boundary campaign E1 (2026-07-17) removed the LAST translation: the carve-out
that mapped the "benign" xdist teardown race (exit 3 + "cannot send (already
closed?)" + a provably-all-green summary) to success. A Codex-review
counterexample proved that carve-out could bless a run that ALSO carried an
unrelated second ``INTERNALERROR`` (probe archived red-on-base at d1b8ef35:
tmp/boundary-ledgers/E1-probes/01-codex-counterexample-red-on-base.txt).

These tests pin the hardened decision functions (both PURE):

* ``classify_phase_result`` — NO nonzero pytest exit ever classifies success;
  ``INTERNALERROR`` and xdist worker loss fail even at exit 0.
* ``classify_manifest`` — a missing, truncated, malformed, or internally
  inconsistent structured phase manifest (tools/pytest_phase_manifest.py) is a
  failure independent of transcript text and exit status.
"""

import itertools
import json
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

import run_tests
from tools import pytest_phase_manifest as manifest_plugin

GREEN_SUMMARY = "==== 4844 passed, 272 skipped, 1 xfailed in 22.64s ===="
FAIL_SUMMARY = "==== 1 failed, 4843 passed, 272 skipped in 22.64s ===="
ERROR_SUMMARY = "==== 2 errors, 4843 passed in 22.64s ===="
ONE_ERROR_SUMMARY = "==== 4843 passed, 1 error in 22.64s ===="
ONE_FAILED_SUMMARY = "==== 4843 passed, 1 failed in 22.64s ===="
RACE_LINE = "INTERNALERROR> execnet.gateway_base.RemoteError: cannot send (already closed?)"
UNRELATED_INTERNALERROR = "INTERNALERROR> RuntimeError: unrelated collection failure"
WORKER_CRASH_LINES = "\n".join([
    "[gw3] node down: Not properly terminated",
    "Replacing crashed worker gw3",
])


def _exit(returncode, output, parallel=False):
    phase_exit, _note = run_tests.classify_phase_result(returncode, output, parallel)
    return phase_exit


def _manifest(collected=None, passed=None, failed=0, errored=0, skipped=0,
              xfailed=0, xpassed=0, deselected=0, schema=None):
    """A structurally valid manifest dict (as JSON text) for classify_manifest."""
    if collected is None:
        collected = [f"tests/x.py::test_{i}" for i in range(3)]
    if passed is None:
        passed = len(collected) - failed - errored - skipped - xfailed - xpassed
    return json.dumps({
        "schema": run_tests.MANIFEST_SCHEMA if schema is None else schema,
        "shuffle_seed": None,
        "exitstatus": 0,
        "collected": collected,
        "counts": {
            "passed": passed, "failed": failed, "errored": errored,
            "skipped": skipped, "xfailed": xfailed, "xpassed": xpassed,
            "deselected": deselected,
        },
        "failed_ids": [],
        "errored_ids": [],
    })


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


# --- INTERNALERROR / worker loss are never masked ------------------------------

def test_internalerror_forced_failure_even_on_exit_0():
    # A swallowed internal error alongside a clean rc must NOT pass.
    output = GREEN_SUMMARY + "\n" + "INTERNALERROR> RuntimeError: boom"
    assert _exit(0, output) != 0


def test_worker_loss_forced_failure_even_on_exit_0():
    # Campaign E1: a lost worker leaves a green-looking surviving summary; the
    # run is incomplete regardless of the exit status.
    output = WORKER_CRASH_LINES + "\n" + GREEN_SUMMARY
    assert _exit(0, output, parallel=True) != 0
    assert _exit(0, output, parallel=False) != 0


def test_internalerror_on_nonzero_is_failure():
    output = "INTERNALERROR> KeyError: 'x'\n" + GREEN_SUMMARY
    assert _exit(3, output) != 0


def test_internalerror_serial_phase_not_translated():
    output = RACE_LINE + "\n" + GREEN_SUMMARY
    assert _exit(3, output, parallel=False) != 0


# --- The xdist teardown race is a FAILURE (carve-out removed, campaign E1) ----
#
# INVERTED PINS: until d1b8ef35 the first two cases below were pinned as PASS
# (test_benign_teardown_race_is_pass / ..._scary_test_name_is_still_pass).
# The carve-out translated pytest exit 3 to success when the transcript looked
# all-green. That translation is deleted; the same transcripts now pin FAILURE.

def test_benign_teardown_race_is_failure():
    # exit 3 + "cannot send" + clean all-green summary + no worker loss:
    # previously the sole translated-to-success case. Now: red, rerun the gate.
    output = "\n".join([GREEN_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_scary_test_name_is_failure():
    # Ordinary output plus the race at exit 3: also a failure now (the
    # anchored worker-loss patterns are pinned separately below).
    output = "\n".join([
        "tests/x.py::test_recover_from_crashed_worker_node_down PASSED",
        "SKIPPED [1] tests/y.py:3: skip because node crashed earlier",
        GREEN_SUMMARY,
        RACE_LINE,
    ])
    assert _exit(3, output, parallel=True) != 0


def test_codex_counterexample_mixed_internalerror_is_failure():
    """THE campaign counterexample (continuation finding F, Codex review).

    A clean summary + the benign race line + an UNRELATED second
    INTERNALERROR at rc 3 under parallel classified SUCCESS on the base
    classifier (demonstrated red-on-base at d1b8ef35, transcript archived in
    tmp/boundary-ledgers/E1-probes/). It must classify FAILURE forever.
    """
    output = "\n".join([
        "==== 10 passed in 0.1s ====",
        RACE_LINE,
        UNRELATED_INTERNALERROR,
    ])
    phase_exit, note = run_tests.classify_phase_result(3, output, parallel=True)
    assert phase_exit != 0
    assert note, "a masked internal error must be called out loudly"


def test_teardown_race_with_failures_is_failure():
    output = "\n".join([FAIL_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_errors_is_failure():
    output = "\n".join([ERROR_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_teardown_race_with_worker_crash_is_failure():
    output = "\n".join([WORKER_CRASH_LINES, GREEN_SUMMARY, RACE_LINE])
    assert _exit(3, output, parallel=True) != 0


def test_exit_3_without_race_marker_is_failure():
    assert _exit(3, GREEN_SUMMARY, parallel=True) != 0


def test_exit_3_race_without_summary_is_failure():
    assert _exit(3, RACE_LINE, parallel=True) != 0


# --- Property sweep: NO (rc != 0, transcript) pair ever classifies success ----

_SWEEP_RCS = (1, 2, 3, 4, 5, run_tests.TIMEOUT_EXIT)
_SWEEP_TRANSCRIPTS = (
    "",
    GREEN_SUMMARY,
    FAIL_SUMMARY,
    ERROR_SUMMARY,
    ONE_ERROR_SUMMARY,
    ONE_FAILED_SUMMARY,
    RACE_LINE,
    GREEN_SUMMARY + "\n" + RACE_LINE,
    GREEN_SUMMARY + "\n" + RACE_LINE + "\n" + UNRELATED_INTERNALERROR,
    WORKER_CRASH_LINES + "\n" + GREEN_SUMMARY,
    WORKER_CRASH_LINES + "\n" + GREEN_SUMMARY + "\n" + RACE_LINE,
    "collecting ...",
    "no tests ran in 0.01s",
    "!!! KeyboardInterrupt !!!",
)


def test_no_nonzero_exit_ever_classifies_success():
    """Exhaustive corpus sweep over rc x transcript x parallel: rc != 0 can
    NEVER map to phase success. This is the campaign's core no-translation
    invariant stated as a property, so no future carve-out can sneak in via a
    transcript shape the example-based pins above happen not to cover."""
    offenders = []
    for rc, transcript, parallel in itertools.product(
            _SWEEP_RCS, _SWEEP_TRANSCRIPTS, (False, True)):
        phase_exit, _note = run_tests.classify_phase_result(
            rc, transcript, parallel)
        if phase_exit == 0:
            offenders.append((rc, parallel, transcript[:60]))
    assert not offenders, (
        "classify_phase_result translated a nonzero pytest exit to success "
        f"for: {offenders}")


def test_worker_loss_detection_anchored():
    # Real xdist crash reports trip detection...
    assert run_tests._has_worker_loss("[gw3] node down: Not properly terminated")
    assert run_tests._has_worker_loss("Replacing crashed worker gw3")
    assert run_tests._has_worker_loss("worker gw0 crashed while running 'x::y'")
    # ...but mid-line mentions in ordinary output do not.
    assert not run_tests._has_worker_loss(
        "tests/x.py::test_recover_from_crashed_worker PASSED")
    assert not run_tests._has_worker_loss("SKIPPED: node crashed last week")


# --- classify_manifest: structural phase evidence -----------------------------

def test_valid_manifest_classifies_ok():
    ok, note, counts = run_tests.classify_manifest(_manifest())
    assert ok and note == ""
    assert counts["passed"] == 3


def test_missing_manifest_is_failure():
    ok, note, _counts = run_tests.classify_manifest(None)
    assert not ok and "MISSING" in note


def test_truncated_manifest_is_failure():
    # Synthetic truncation: valid JSON cut mid-document.
    text = _manifest()
    ok, note, _counts = run_tests.classify_manifest(text[:len(text) // 2])
    assert not ok and "unparseable" in note


def test_empty_manifest_text_is_failure():
    ok, _note, _counts = run_tests.classify_manifest("")
    assert not ok


def test_wrong_schema_manifest_is_failure():
    ok, note, _counts = run_tests.classify_manifest(_manifest(schema=99))
    assert not ok and "schema" in note


def test_malformed_manifest_is_failure():
    ok, _note, _counts = run_tests.classify_manifest(
        json.dumps({"schema": run_tests.MANIFEST_SCHEMA}))
    assert not ok


def test_manifest_missing_count_field_is_failure():
    data = json.loads(_manifest())
    del data["counts"]["errored"]
    ok, note, _counts = run_tests.classify_manifest(json.dumps(data))
    assert not ok and "errored" in note


def test_empty_collection_manifest_is_failure():
    """Integrator ruling (E1 bounce): a structurally valid manifest whose
    collection is EMPTY (all-zero counts) is a failure even at rc 0 — a phase
    that ran nothing proves nothing."""
    ok, note, _counts = run_tests.classify_manifest(_manifest(collected=[]))
    assert not ok and "EMPTY" in note


def test_collection_count_mismatch_is_failure():
    # 3 collected ids but only 2 reported outcomes: a lost worker's silence.
    data = json.loads(_manifest())
    data["counts"]["passed"] = 2
    ok, note, _counts = run_tests.classify_manifest(json.dumps(data))
    assert not ok and "collected" in note


def test_manifest_failed_count_is_failure():
    ok, _note, counts = run_tests.classify_manifest(_manifest(failed=1))
    assert not ok
    assert counts.get("failed") == 1


def test_manifest_errored_count_is_failure():
    ok, _note, _counts = run_tests.classify_manifest(_manifest(errored=1))
    assert not ok


def test_manifest_skips_and_xfails_are_not_failures():
    ok, _note, _counts = run_tests.classify_manifest(
        _manifest(skipped=1, xfailed=1))
    assert ok


# --- run_tests <-> plugin contract cannot drift -------------------------------

def test_manifest_contract_matches_plugin():
    """run_tests deliberately does not import the (pytest-importing) plugin;
    the duplicated schema/field constants are pinned identical here."""
    assert run_tests.MANIFEST_SCHEMA == manifest_plugin.MANIFEST_SCHEMA
    assert run_tests.MANIFEST_OUTCOME_FIELDS == manifest_plugin.OUTCOME_FIELDS


def test_pytest_base_cmd_uses_this_interpreter():
    """Continuation medium 16: the runner must launch pytest with its OWN
    interpreter (sys.executable), never a PATH-resolved 'python', and must
    load the phase-manifest plugin in every phase."""
    base = run_tests.pytest_base_cmd()
    assert base[0] == sys.executable
    assert base[1:3] == ['-m', 'pytest']
    assert 'tools.pytest_phase_manifest' in base


# --- run_command + manifest integration (subprocess-driven) -------------------

def test_run_command_missing_manifest_fails_despite_clean_rc(monkeypatch, tmp_path):
    """A phase whose child exits 0 with green-looking output but never writes
    its manifest is a FAILURE — evidence of what ran is mandatory."""
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    manifest = tmp_path / "phase.json"
    rc, out, counts = run_tests.run_command(
        [sys.executable, '-c', 'print("==== 10 passed in 0.1s ====")'],
        'missing-manifest probe', timeout=30, manifest_path=manifest)
    assert rc != 0
    assert counts == {}
    assert '10 passed' in out  # the transcript looked green; structure decides


def test_run_command_truncated_manifest_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    manifest = tmp_path / "phase.json"
    script = (
        "import sys\n"
        f"open({str(manifest)!r}, 'w').write('{{\"schema\": 1, \"coll')\n"
        "print('==== 10 passed in 0.1s ====')\n"
    )
    rc, _out, counts = run_tests.run_command(
        [sys.executable, '-c', script],
        'truncated-manifest probe', timeout=30, manifest_path=manifest)
    assert rc != 0
    assert counts == {}


def test_run_command_stale_manifest_never_vouches(monkeypatch, tmp_path):
    """A manifest left by an EARLIER run must be deleted before the child
    starts; a child that writes nothing then fails on the missing manifest."""
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    manifest = tmp_path / "phase.json"
    manifest.write_text(_manifest())
    rc, _out, counts = run_tests.run_command(
        [sys.executable, '-c', 'pass'],
        'stale-manifest probe', timeout=30, manifest_path=manifest)
    assert rc != 0
    assert counts == {}


def test_run_command_valid_manifest_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    manifest = tmp_path / "phase.json"
    payload = _manifest()
    script = (
        f"open({str(manifest)!r}, 'w').write({payload!r})\n"
    )
    rc, _out, counts = run_tests.run_command(
        [sys.executable, '-c', script],
        'valid-manifest probe', timeout=30, manifest_path=manifest)
    assert rc == 0
    assert counts["passed"] == 3


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
    rc, _out, _counts = run_tests.run_command(
        [sys.executable, '-c', inner], 'killpg probe', timeout=2)
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
    rc, out, _counts = run_tests.run_command(
        [sys.executable, '-c', inner], 'orphan probe', timeout=30)
    elapsed = time.time() - t0
    assert 'child-done' in out
    assert elapsed < 6, f"run_command wedged on an orphan-held pipe ({elapsed:.1f}s)"
    assert rc == 0


def test_run_command_kills_group_on_interrupt(monkeypatch):
    """Ctrl-C (or any early exit) while a phase runs must group-kill the child
    before propagating — otherwise the child pytest and its xdist workers are
    orphaned (appraisal finding C4). The timeout path already did this; this
    pins the interrupt path.
    """
    monkeypatch.setattr(run_tests, 'emit', lambda *a, **k: None)
    killed = []

    class _FakeProc:
        pid = 424242
        returncode = None

        def wait(self, timeout=None):
            raise KeyboardInterrupt

    monkeypatch.setattr(run_tests.subprocess, 'Popen',
                        lambda *a, **k: _FakeProc())
    monkeypatch.setattr(run_tests, '_kill_process_group',
                        lambda proc: killed.append(proc.pid))

    with pytest.raises(KeyboardInterrupt):
        run_tests.run_command([sys.executable, '-c', 'pass'], 'interrupt probe')
    assert killed == [424242], "interrupted phase did not group-kill its child"


# --- Compare-bash banner counts are LIVE (never re-frozen) --------------------

def test_golden_case_counts_match_yaml():
    """golden_case_counts() must equal an independent parse of the YAML.

    The compare-bash banner once printed a hardcoded "1,119 pairs" that went
    188 cases stale on the gate's own transcript. This pins the counts to the
    live corpus so a frozen number can never creep back: the function and a
    fresh yaml.safe_load must agree, and the corpus is non-trivial (some
    psh_only cases exist, so `comparisons < total`)."""
    import yaml

    path = (pathlib.Path(run_tests.__file__).resolve().parent
            / "tests" / "behavioral" / "golden_cases.yaml")
    cases = yaml.safe_load(path.read_text())
    total = len(cases)
    psh_only = sum(1 for c in cases if c.get("psh_only", False))

    assert run_tests.golden_case_counts() == (total, psh_only, total - psh_only)
    assert total > 100 and psh_only > 0, "golden corpus looks wrong-sized"
    assert total - psh_only < total, "comparisons must exclude psh_only cases"
