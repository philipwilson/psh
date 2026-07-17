"""Same-SHA release attestation: writer shape + workflow verifier logic (E4).

Campaign decision (Boundary Integrity, 2026-07-17): ``release-tag.yml`` must
not tag unattested commits. ``run_tests.py --write-attestation`` writes
``gate_attestation.json`` only on a fully green gate; the workflow calls
``tools/verify_gate_attestation.py`` BEFORE tagging and fails loudly unless

* the attestation exists, parses, and has the expected schema/keys;
* its version equals ``psh/version.py`` at HEAD;
* its gated_commit is an ancestor of HEAD with a matching tree hash;
* NOTHING but the attestation file changed between gated_commit and HEAD.

The verifier's checks are exercised here against scratch git repositories, so
the workflow's tagging guard is unit-tested rather than only prose.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import run_tests
from tools import verify_gate_attestation as vga

GIT_ENV_ARGS = ["-c", "user.name=t", "-c", "user.email=t@t",
                "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


def _git(repo, *args):
    proc = subprocess.run(["git", *GIT_ENV_ARGS, *args], cwd=repo,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout.strip()


def _make_repo(tmp_path, version="1.2.3"):
    repo = tmp_path / "repo"
    (repo / "psh").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "psh" / "version.py").write_text(f'__version__ = "{version}"\n')
    (repo / "other.txt").write_text("content\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _attestation_dict(repo, version="1.2.3", **overrides):
    data = run_tests.build_attestation(
        version=version,
        gated_commit=_git(repo, "rev-parse", "HEAD"),
        gated_tree=_git(repo, "rev-parse", "HEAD^{tree}"),
        phases=[{"description": "Phase 1", "exit": 0,
                 "counts": {"passed": 10, "failed": 0, "errored": 0,
                            "skipped": 1, "xfailed": 0, "xpassed": 0,
                            "deselected": 0}}],
        ruff=True,
        mypy_files=258,
        command="run_tests.py --parallel --write-attestation",
        timestamp="2026-07-17T00:00:00+00:00",
        platform_info={"os": "Darwin 25.5.0", "python": "3.12.0",
                       "arch": "arm64"},
    )
    data.update(overrides)
    return data


def _commit_attestation(repo, data):
    (repo / vga.ATTESTATION_FILENAME).write_text(json.dumps(data) + "\n")
    _git(repo, "add", vga.ATTESTATION_FILENAME)
    _git(repo, "commit", "-q", "-m", "attest")


# --- Writer schema ------------------------------------------------------------

def test_build_attestation_schema_matches_verifier_contract(tmp_path):
    """The writer's output shape IS the verifier's required contract: exact
    key-set equality plus the sub-shapes the ceremony relies on."""
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo)
    assert set(data.keys()) == vga.REQUIRED_KEYS
    assert data["schema"] == run_tests.ATTESTATION_SCHEMA == vga.ATTESTATION_SCHEMA
    assert set(data["platform"].keys()) == {"os", "python", "arch"}
    assert isinstance(data["phases"], list) and data["phases"]
    for phase in data["phases"]:
        assert set(phase.keys()) == {"description", "exit", "counts"}
        assert set(phase["counts"].keys()) == set(
            run_tests.MANIFEST_OUTCOME_FIELDS) | {"deselected"}
    assert run_tests.ATTESTATION_FILENAME == vga.ATTESTATION_FILENAME


# --- Verifier: green path -----------------------------------------------------

def test_verify_ok_attestation_commit_after_gate(tmp_path):
    """The intended ceremony: gate at commit C, attestation committed as the
    ONLY change on top; HEAD = attestation commit."""
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo)
    _commit_attestation(repo, data)
    ok, messages = vga.verify_attestation(repo)
    assert ok, messages
    assert "OK" in messages[0]


def test_verify_ok_through_merge_commit(tmp_path):
    """The gated-tip vs merge-commit case the scheme was designed for: main
    merges the branch (merge commit SHA != gated tip) but the snapshot diff
    gated_commit..HEAD is still attestation-only."""
    repo = _make_repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "fix/topic")
    (repo / "other.txt").write_text("changed on branch\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    data = _attestation_dict(repo)          # gate at branch tip
    _commit_attestation(repo, data)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "fix/topic")
    ok, messages = vga.verify_attestation(repo)
    assert ok, messages


# --- Verifier: every check fails loudly ---------------------------------------

def test_absent_attestation_fails_with_bootstrap_message(tmp_path):
    repo = _make_repo(tmp_path)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    text = "\n".join(messages)
    assert "ABSENT" in text
    assert "Boundary Integrity Campaign" in text, (
        "the bootstrap failure must name the campaign decision")


def test_truncated_attestation_fails(tmp_path):
    repo = _make_repo(tmp_path)
    payload = json.dumps(_attestation_dict(repo))
    (repo / vga.ATTESTATION_FILENAME).write_text(payload[:len(payload) // 2])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "attest")
    ok, messages = vga.verify_attestation(repo)
    assert not ok and "JSON" in messages[0]


def test_missing_keys_fail(tmp_path):
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo)
    del data["gated_tree"], data["ruff"]
    _commit_attestation(repo, data)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert "gated_tree" in messages[0] and "ruff" in messages[0]


def test_wrong_schema_fails(tmp_path):
    repo = _make_repo(tmp_path)
    _commit_attestation(repo, _attestation_dict(repo, schema=99))
    ok, messages = vga.verify_attestation(repo)
    assert not ok and "schema" in messages[0]


def test_version_mismatch_fails(tmp_path):
    """Version bumped after the gate ran: the attestation vouches for the
    wrong version — no tag."""
    repo = _make_repo(tmp_path, version="1.2.3")
    data = _attestation_dict(repo, version="1.2.2")
    _commit_attestation(repo, data)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert any("version" in m for m in messages)


def test_unknown_gated_commit_fails(tmp_path):
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo,
                             gated_commit="0" * 40,
                             gated_tree="0" * 40)
    _commit_attestation(repo, data)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert any("not a commit" in m for m in messages)


def test_non_ancestor_gated_commit_fails(tmp_path):
    """A gate run on an abandoned side branch cannot attest main's HEAD."""
    repo = _make_repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "other.txt").write_text("side work\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side")
    side_data = _attestation_dict(repo)     # gated_commit = side tip
    _git(repo, "checkout", "-q", "main")
    _commit_attestation(repo, side_data)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert any("ancestor" in m for m in messages)


def test_gated_tree_mismatch_fails(tmp_path):
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo, gated_tree="f" * 40)
    _commit_attestation(repo, data)
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert any("gated_tree" in m for m in messages)


def test_extra_changes_since_gate_fail(tmp_path):
    """THE central check: anything besides the attestation changing between
    gated_commit and HEAD means the gate did not test what is being tagged."""
    repo = _make_repo(tmp_path)
    data = _attestation_dict(repo)
    (repo / vga.ATTESTATION_FILENAME).write_text(json.dumps(data) + "\n")
    (repo / "other.txt").write_text("sneaked in after the gate\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "attest + sneak")
    ok, messages = vga.verify_attestation(repo)
    assert not ok
    assert any("other.txt" in m for m in messages)


def test_cli_exit_codes(tmp_path):
    """The workflow consumes the process exit status; pin both directions."""
    repo = _make_repo(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(Path(vga.__file__)), "--repo", str(repo)],
        capture_output=True, text=True)
    assert proc.returncode == 1
    assert "Boundary Integrity Campaign" in proc.stdout

    _commit_attestation(repo, _attestation_dict(repo))
    proc = subprocess.run(
        [sys.executable, str(Path(vga.__file__)), "--repo", str(repo)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_write_attestation_rejected_outside_standard_gate():
    """A green quick/benchmark/all-nocapture run must never mint release
    evidence: --write-attestation is standard-gate-only (campaign E4)."""
    for mode_flag in ("--quick", "--benchmarks", "--all-nocapture"):
        proc = subprocess.run(
            [sys.executable, str(Path(run_tests.__file__)), mode_flag,
             "--write-attestation"],
            capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2, (mode_flag, proc.stdout, proc.stderr)
        assert "--write-attestation" in proc.stderr


# --- The workflow actually calls the verifier ---------------------------------

def test_release_workflow_invokes_verifier_before_tagging():
    """release-tag.yml must run tools/verify_gate_attestation.py in a step
    BEFORE the tag-creation step — otherwise the guard is decorative."""
    workflow = (Path(run_tests.__file__).resolve().parent
                / ".github" / "workflows" / "release-tag.yml")
    text = workflow.read_text(encoding="utf-8")
    verify_pos = text.find("tools/verify_gate_attestation.py")
    tag_pos = text.find("git tag -a")
    assert verify_pos != -1, "release-tag.yml no longer calls the verifier"
    assert tag_pos != -1, "release-tag.yml no longer creates the tag?"
    assert verify_pos < tag_pos, (
        "the attestation verification step must precede tag creation")


# --- Writer refuses on a dirty tree -------------------------------------------

def test_write_attestation_refuses_dirty_tracked_tree(tmp_path, monkeypatch):
    """gated_commit must not lie: with tracked modifications (other than the
    attestation itself) present, --write-attestation refuses."""
    monkeypatch.setattr(run_tests, "emit", lambda *a, **k: None)
    repo = _make_repo(tmp_path)
    (repo / "other.txt").write_text("uncommitted modification\n")
    rc = run_tests.write_attestation(repo, phases=[], command="x")
    assert rc == 1
    assert not (repo / run_tests.ATTESTATION_FILENAME).exists()


def test_write_attestation_green_path_writes_valid_file(tmp_path, monkeypatch):
    """On a clean tree with green checks, the writer produces a file the
    verifier accepts once committed (ruff/mypy stubbed — their real gating is
    the ceremony's; this pins the wiring and the file shape)."""
    monkeypatch.setattr(run_tests, "emit", lambda *a, **k: None)
    monkeypatch.setattr(run_tests, "_run_attestation_checks",
                        lambda repo_root: (True, True, 258))
    repo = _make_repo(tmp_path)
    phases = [{"description": "Phase 1", "exit": 0,
               "counts": {"passed": 5, "failed": 0, "errored": 0,
                          "skipped": 0, "xfailed": 0, "xpassed": 0,
                          "deselected": 0}}]
    rc = run_tests.write_attestation(repo, phases=phases,
                                     command="run_tests.py --parallel")
    assert rc == 0
    written = json.loads((repo / run_tests.ATTESTATION_FILENAME).read_text())
    assert set(written.keys()) == vga.REQUIRED_KEYS
    assert written["version"] == "1.2.3"
    assert written["mypy_files"] == 258
    # Commit it (the ceremony's final commit) and the verifier accepts.
    _git(repo, "add", vga.ATTESTATION_FILENAME)
    _git(repo, "commit", "-q", "-m", "attest")
    ok, messages = vga.verify_attestation(repo)
    assert ok, messages


def test_write_attestation_rewrite_over_committed_attestation_allowed(
        tmp_path, monkeypatch):
    """Re-gating at a SHA where an OLD attestation is already tracked: the
    only 'dirty' file is the attestation being rewritten, which is exactly
    the intended update flow — the writer must not refuse."""
    monkeypatch.setattr(run_tests, "emit", lambda *a, **k: None)
    monkeypatch.setattr(run_tests, "_run_attestation_checks",
                        lambda repo_root: (True, True, 258))
    repo = _make_repo(tmp_path)
    _commit_attestation(repo, _attestation_dict(repo, version="1.2.2"))
    rc = run_tests.write_attestation(repo, phases=[], command="x")
    assert rc == 0
    written = json.loads((repo / run_tests.ATTESTATION_FILENAME).read_text())
    assert written["version"] == "1.2.3"


@pytest.mark.slow
def test_run_attestation_checks_real_ruff_and_mypy_missing_tolerated(
        tmp_path, monkeypatch):
    """_run_attestation_checks against an EMPTY scratch dir: ruff passes
    trivially (no files) or is absent; mypy has no config there, so the
    function must fail cleanly rather than crash — the writer then refuses.
    This exercises the real subprocess path without depending on this repo's
    current lint state."""
    monkeypatch.setattr(run_tests, "emit", lambda *a, **k: None)
    scratch = tmp_path / "empty"
    (scratch / "psh").mkdir(parents=True)
    (scratch / "tests").mkdir()
    ok, _ruff, _mypy_files = run_tests._run_attestation_checks(scratch)
    assert ok in (True, False)  # must return, never raise
