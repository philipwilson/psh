"""Version and platform classifiers (Improvement Program 2026-09, D4/D5).

A version-sensitive row carries ``@pytest.mark.oracle_min("5.3")`` (pytest)
or ``min_bash: "5.3"`` (golden); a row that opens ``/dev/stdout`` by path
carries ``requires_dev_fd: true`` (golden). On a host that cannot judge the
row — an older oracle, a sandbox that denies ``/dev/stdout`` — the row SKIPS
with a countable reason, never FAILS and never silently passes. The reasons
come from ``tests/harness/oracle_policy.py`` (``oracle_min_skip_reason``,
``dev_fd_skip_reason``); the marker hook lives in ``tests/conftest.py`` and
the golden keys in ``tests/behavioral/test_golden_behavior.py``.

Every check here uses a FAKE oracle or a monkeypatched probe so it holds on
any host; the marker's positive direction is exercised for real once.
"""
import configparser
import importlib.util
import re
import types
from pathlib import Path

import oracle_policy
import pytest
import yaml
from oracle_policy import dev_fd_skip_reason, oracle_at_least, oracle_min_skip_reason
from shell_oracle import BashOracle, BashOracleUnavailable

TESTS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = TESTS_ROOT.parent
GOLDEN_CASES = TESTS_ROOT / "behavioral" / "golden_cases.yaml"

OLD = BashOracle("/fake/oracle/sh", "5.1.16(1)-release")
NEW = BashOracle("/fake/oracle/sh", "5.3.15(1)-release")


# --- oracle_min_skip_reason ---------------------------------------------------

def test_oracle_min_skip_reason_names_version_and_minimum():
    assert oracle_min_skip_reason("5.3", OLD) == "oracle 5.1.16(1)-release < 5.3"
    assert oracle_min_skip_reason("5.1.17", OLD) == "oracle 5.1.16(1)-release < 5.1.17"


def test_oracle_min_skip_reason_is_none_when_satisfied():
    assert oracle_min_skip_reason("5.3", NEW) is None
    assert oracle_min_skip_reason("5.1.16", OLD) is None


def test_oracle_min_skip_reason_resolves_the_oracle_when_not_given(monkeypatch):
    monkeypatch.setattr(oracle_policy, "resolve_bash", lambda: OLD)
    assert oracle_min_skip_reason("5.3") == "oracle 5.1.16(1)-release < 5.3"


def test_oracle_min_skip_reason_reports_an_unavailable_oracle(monkeypatch):
    def unavailable():
        raise BashOracleUnavailable("no bash oracle found")
    monkeypatch.setattr(oracle_policy, "resolve_bash", unavailable)
    reason = oracle_min_skip_reason("5.3")
    assert reason.startswith("oracle unavailable (no bash oracle found)")
    assert "bash >= 5.3" in reason


# --- dev_fd_skip_reason -------------------------------------------------------

def _probe(monkeypatch, error):
    calls = []

    def fake_probe():
        calls.append(1)
        return error
    monkeypatch.setattr(oracle_policy, "_probe_dev_stdout_writable", fake_probe)
    monkeypatch.setattr(oracle_policy, "_HOST_CACHE", {})
    return calls


def test_dev_fd_skip_reason_when_probe_fails(monkeypatch):
    _probe(monkeypatch, "[Errno 1] Operation not permitted: '/dev/stdout'")
    assert dev_fd_skip_reason() == (
        "/dev/stdout not openable for writing "
        "([Errno 1] Operation not permitted: '/dev/stdout')")


def test_dev_fd_skip_reason_none_when_probe_succeeds(monkeypatch):
    _probe(monkeypatch, None)
    assert dev_fd_skip_reason() is None


def test_dev_fd_probe_runs_once_per_process(monkeypatch):
    calls = _probe(monkeypatch, None)
    dev_fd_skip_reason()
    dev_fd_skip_reason()
    assert len(calls) == 1


def test_real_probe_catches_oserror_only():
    """The live probe either succeeds (unsandboxed gate) or yields an OSError
    text — it never raises out of a row's setup."""
    error = oracle_policy._probe_dev_stdout_writable()
    assert error is None or isinstance(error, str)


# --- the oracle_min marker ----------------------------------------------------

def test_oracle_min_marker_is_registered():
    parser = configparser.ConfigParser()
    parser.read(REPO_ROOT / "pytest.ini")
    markers = parser["pytest"]["markers"].splitlines()
    assert any(m.strip().startswith("oracle_min(version):") for m in markers), markers


def _root_conftest(config):
    matches = [p for p in config.pluginmanager.get_plugins()
               if Path(getattr(p, "__file__", "") or "x").resolve() == TESTS_ROOT / "conftest.py"]
    assert len(matches) == 1
    return matches[0]


def _item(marker_args):
    marker = None if marker_args is None else types.SimpleNamespace(args=marker_args)
    return types.SimpleNamespace(
        get_closest_marker=lambda name: marker if name == "oracle_min" else None,
        fspath="tests/unit/x.py",
        config=types.SimpleNamespace(getoption=lambda *a, **k: False))


def test_marker_hook_skips_with_the_countable_reason(request, monkeypatch):
    monkeypatch.setattr(oracle_policy, "resolve_bash", lambda: OLD)
    hook = _root_conftest(request.config).pytest_runtest_setup
    with pytest.raises(pytest.skip.Exception) as info:
        hook(_item(("5.3",)))
    assert str(info.value) == "oracle 5.1.16(1)-release < 5.3"


def test_marker_hook_lets_a_satisfied_row_run(request, monkeypatch):
    monkeypatch.setattr(oracle_policy, "resolve_bash", lambda: NEW)
    hook = _root_conftest(request.config).pytest_runtest_setup
    assert hook(_item(("5.3",))) is None
    assert hook(_item(None)) is None          # unmarked item untouched


@pytest.mark.parametrize("bad", [(), ("5.3", "5.4"), (5.3,)])
def test_marker_hook_rejects_a_malformed_marker(request, bad):
    hook = _root_conftest(request.config).pytest_runtest_setup
    with pytest.raises(pytest.fail.Exception, match="exactly one version string"):
        hook(_item(bad))


@pytest.mark.oracle_min("1.0")
def test_marker_positive_direction_runs_for_real():
    """A satisfied oracle_min row runs (the negative direction is pinned via
    the hook above so the gate's D5 version-skip census stays at 0)."""
    assert oracle_at_least("1.0")


# --- the golden keys ----------------------------------------------------------

def _golden_runner():
    spec = importlib.util.spec_from_file_location(
        "golden_runner_under_test", TESTS_ROOT / "behavioral" / "test_golden_behavior.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_min_bash_skips_on_an_older_oracle(monkeypatch):
    monkeypatch.setattr(oracle_policy, "resolve_bash", lambda: OLD)
    with pytest.raises(pytest.skip.Exception) as info:
        _golden_runner()._apply_case_classifiers({"name": "row", "min_bash": "5.3"})
    assert str(info.value) == "oracle 5.1.16(1)-release < 5.3"


def test_golden_min_bash_runs_on_a_new_enough_oracle(monkeypatch):
    monkeypatch.setattr(oracle_policy, "resolve_bash", lambda: NEW)
    runner = _golden_runner()
    assert runner._apply_case_classifiers({"name": "row", "min_bash": "5.3"}) is None
    assert runner._apply_case_classifiers({"name": "row"}) is None


def test_golden_requires_dev_fd_skips_when_probe_fails(monkeypatch):
    _probe(monkeypatch, "[Errno 1] Operation not permitted")
    with pytest.raises(pytest.skip.Exception) as info:
        _golden_runner()._apply_case_classifiers({"name": "row", "requires_dev_fd": True})
    assert str(info.value).startswith("/dev/stdout not openable for writing")


def test_golden_requires_dev_fd_runs_when_probe_succeeds(monkeypatch):
    _probe(monkeypatch, None)
    assert _golden_runner()._apply_case_classifiers(
        {"name": "row", "requires_dev_fd": True}) is None


def test_golden_legs_apply_the_classifiers():
    """Both parametrized legs call the classifier before running anything."""
    src = (TESTS_ROOT / "behavioral" / "test_golden_behavior.py").read_text(encoding="utf-8")
    assert src.count("\n    _apply_case_classifiers(case)\n") == 2   # call sites, not the def


# --- the golden corpus: keys are known, classifier values well-formed --------

KNOWN_GOLDEN_KEYS = {"name", "command", "stdout", "stderr", "exit_code",
                     "psh_only", "min_bash", "requires_dev_fd"}
_VERSION = re.compile(r"^\d+\.\d+(\.\d+)?$")


def _cases():
    with open(GOLDEN_CASES, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_golden_case_keys_are_known():
    """There was no key validation before D5: a misspelled classifier key
    (``min_bsh``) would silently do nothing. Now it fails here."""
    unknown = [(c["name"], sorted(set(c) - KNOWN_GOLDEN_KEYS))
               for c in _cases() if set(c) - KNOWN_GOLDEN_KEYS]
    assert not unknown, unknown


def test_golden_classifier_values_are_well_formed():
    for c in _cases():
        if "min_bash" in c:
            assert isinstance(c["min_bash"], str) and _VERSION.match(c["min_bash"]), (
                c["name"], c["min_bash"], 'quote it: min_bash: "5.3"')
        if "requires_dev_fd" in c:
            assert c["requires_dev_fd"] is True, (c["name"], "omit the key instead of false")


def test_history_write_to_dev_stdout_row_is_classified():
    row = next(c for c in _cases() if c["name"] == "r18t2_builtins_history_write_to_stdout")
    assert row["requires_dev_fd"] is True and row["psh_only"] is True
