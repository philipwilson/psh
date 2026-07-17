"""End-to-end tests for the structured phase-manifest plugin (campaign E1).

``tools/pytest_phase_manifest.py`` is the producer of the gate's structural
evidence: per-phase collected node ids and per-outcome counts, plus the
deterministic ``--shuffle-seed`` ordering used by the campaign's Phase-E
three-seed exit. These tests drive REAL pytest subprocesses over a synthetic
mini-suite and assert the manifest tells the truth in both serial and xdist
modes, and that ``run_tests.classify_manifest`` accepts/rejects the real files
the plugin writes.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import run_tests

ROOT = Path(__file__).resolve().parents[3]

MINI_SUITE = '''
import pytest

def test_pass():
    pass

def test_fail():
    assert False

def test_skip():
    pytest.skip("because")

@pytest.mark.xfail(reason="known")
def test_xfail():
    assert False

@pytest.mark.xfail(reason="known", strict=False)
def test_xpass():
    pass

@pytest.fixture
def broken():
    raise RuntimeError("setup boom")

def test_error(broken):
    pass

def test_teardown_error(request):
    request.addfinalizer(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

def test_deselect_me():
    pass
'''

GREEN_SUITE = '\n'.join(f"def test_g{i}():\n    pass\n" for i in range(10))


def _run_mini(tmp_path, suite, *pytest_args, manifest_name="manifest.json"):
    """Run pytest on *suite* text in tmp_path with the plugin; return
    (completed_process, manifest_path)."""
    (tmp_path / "test_mini.py").write_text(suite)
    manifest = tmp_path / manifest_name
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "pytest", "test_mini.py",
           "-p", "tools.pytest_phase_manifest",
           "-p", "no:cacheprovider",
           "--phase-manifest", str(manifest), "-q", *pytest_args]
    proc = subprocess.run(cmd, cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=120)
    return proc, manifest


def _load(manifest):
    assert manifest.exists(), "plugin did not write the manifest"
    return json.loads(manifest.read_text())


EXPECTED_MIXED_COUNTS = {
    "passed": 1,      # test_pass
    "failed": 1,      # test_fail
    "errored": 2,     # test_error (setup), test_teardown_error (teardown)
    "skipped": 1,     # test_skip
    "xfailed": 1,     # test_xfail
    "xpassed": 1,     # test_xpass (non-strict; rootdir has no pytest.ini)
    "deselected": 1,  # test_deselect_me via -k
}


def test_manifest_truth_serial(tmp_path):
    proc, manifest = _run_mini(tmp_path, MINI_SUITE, "-k", "not deselect_me")
    data = _load(manifest)
    assert data["schema"] == run_tests.MANIFEST_SCHEMA
    assert data["counts"] == EXPECTED_MIXED_COUNTS
    assert len(data["collected"]) == 7
    assert "test_mini.py::test_deselect_me" not in data["collected"]
    assert data["failed_ids"] == ["test_mini.py::test_fail"]
    assert sorted(data["errored_ids"]) == [
        "test_mini.py::test_error", "test_mini.py::test_teardown_error"]
    assert data["exitstatus"] == proc.returncode == 1
    # The real failing manifest must be REJECTED by the runner's classifier.
    ok, _note, counts = run_tests.classify_manifest(manifest.read_text())
    assert not ok
    assert counts == EXPECTED_MIXED_COUNTS


@pytest.mark.slow
def test_manifest_truth_xdist(tmp_path):
    """Under -n 2 the controller must still record collection (via the xdist
    node-collection hook), outcomes (forwarded reports), and deselection
    (shipped through workeroutput)."""
    proc, manifest = _run_mini(tmp_path, MINI_SUITE,
                               "-k", "not deselect_me", "-n", "2")
    data = _load(manifest)
    assert data["counts"] == EXPECTED_MIXED_COUNTS
    assert len(data["collected"]) == 7
    assert proc.returncode == 1


def test_green_manifest_accepted_by_classifier(tmp_path):
    proc, manifest = _run_mini(tmp_path, GREEN_SUITE)
    assert proc.returncode == 0
    ok, note, counts = run_tests.classify_manifest(manifest.read_text())
    assert ok, note
    assert counts["passed"] == 10
    data = _load(manifest)
    assert sum(counts[f] for f in run_tests.MANIFEST_OUTCOME_FIELDS) == len(
        data["collected"])


def test_shuffle_seed_deterministic_and_seed_sensitive(tmp_path):
    _, m1 = _run_mini(tmp_path, GREEN_SUITE, "--shuffle-seed", "3",
                      manifest_name="m1.json")
    _, m2 = _run_mini(tmp_path, GREEN_SUITE, "--shuffle-seed", "3",
                      manifest_name="m2.json")
    _, m3 = _run_mini(tmp_path, GREEN_SUITE, "--shuffle-seed", "4",
                      manifest_name="m3.json")
    _, m0 = _run_mini(tmp_path, GREEN_SUITE, manifest_name="m0.json")
    order1 = _load(m1)["collected"]
    order2 = _load(m2)["collected"]
    order3 = _load(m3)["collected"]
    order0 = _load(m0)["collected"]
    assert order1 == order2, "same seed must reproduce the same order"
    assert sorted(order1) == sorted(order3) == sorted(order0)
    assert order1 != order3, "different seeds must differ (10! orderings)"
    assert order1 != order0, "seeded order must differ from collection order"
    assert _load(m1)["shuffle_seed"] == 3
    assert _load(m0)["shuffle_seed"] is None


def test_categorize_report_unit():
    """The per-report categorization used to build the counts (pure)."""
    from tools.pytest_phase_manifest import categorize_report

    class R:
        def __init__(self, when, outcome, wasxfail=False):
            self.when = when
            self.outcome = outcome
            if wasxfail:
                self.wasxfail = "reason"

    assert categorize_report(R("call", "passed")) == "passed"
    assert categorize_report(R("call", "failed")) == "failed"
    assert categorize_report(R("call", "skipped")) == "skipped"
    assert categorize_report(R("call", "skipped", wasxfail=True)) == "xfailed"
    assert categorize_report(R("call", "passed", wasxfail=True)) == "xpassed"
    assert categorize_report(R("setup", "failed")) == "errored"
    assert categorize_report(R("teardown", "failed")) == "errored"
    assert categorize_report(R("setup", "skipped")) == "skipped"
    assert categorize_report(R("setup", "skipped", wasxfail=True)) == "xfailed"
    assert categorize_report(R("setup", "passed")) is None
    assert categorize_report(R("teardown", "passed")) is None
