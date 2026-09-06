"""One oracle identity on every reporting surface (Improvement Program 2026-09, D1).

``tests/harness/oracle_policy.py#oracle_summary`` renders the resolved bash as
``oracle: <path> <version>``. That SAME line must appear on every surface a
reader uses to learn which bash produced a reference side:

* the ``run_tests.py`` preflight (pinned in ``test_gate_attestation.py``);
* the pytest session header (``tests/conftest.py#pytest_report_header``);
* every conformance failure message
  (``conformance_framework.py#_oracle_line``, appended by the three
  ``assert_*`` helpers).

A host with no oracle at all says ``oracle: UNAVAILABLE (...)`` on those
surfaces rather than crashing collection or hiding the failure's provenance.
"""
import sys
import types
from pathlib import Path

import oracle_policy
import pytest
from oracle_policy import oracle_summary
from shell_oracle import BashOracleUnavailable

TESTS_ROOT = Path(__file__).resolve().parents[2]
# tests/conformance is not a package and not on sys.path (only tests/harness
# is, via tests/conftest.py) — same arrangement as test_shell_oracle_harness.py.
sys.path.insert(0, str(TESTS_ROOT / "conformance"))
import conformance_framework  # noqa: E402
from conformance_framework import ConformanceResult, ConformanceTest  # noqa: E402


def _root_conftest(config):
    """The tests/conftest.py plugin object, found through pytest's own
    registry (never a second import of the module)."""
    matches = [p for p in config.pluginmanager.get_plugins()
               if Path(getattr(p, "__file__", "") or "x").resolve() == TESTS_ROOT / "conftest.py"]
    assert len(matches) == 1, matches
    return matches[0]


def test_session_header_is_the_oracle_summary(request):
    line = _root_conftest(request.config).pytest_report_header(request.config)
    assert line == oracle_summary()
    assert line.startswith("oracle: /")


def test_session_header_survives_an_unavailable_oracle(request, monkeypatch):
    def unavailable():
        raise BashOracleUnavailable("no bash oracle found")
    monkeypatch.setattr(oracle_policy, "oracle_summary", unavailable)
    line = _root_conftest(request.config).pytest_report_header(request.config)
    assert line == "oracle: UNAVAILABLE (no bash oracle found)"


class _Probe(ConformanceTest):
    """A ConformanceTest whose framework is a stub returning a canned result,
    so the assertion text is exercised without spawning either shell."""

    def __init__(self, conformance):
        self._framework = types.SimpleNamespace(
            compare_behavior=lambda command, env=None: types.SimpleNamespace(
                conformance=conformance, psh_result=None, bash_result=None,
                notes="probe", difference_id="X"))


def _not_identical():
    return next(m for m in ConformanceResult if m is not ConformanceResult.IDENTICAL)


def test_identical_behavior_failure_ends_with_the_oracle_line():
    with pytest.raises(AssertionError) as info:
        _Probe(_not_identical()).assert_identical_behavior("echo probe")
    text = str(info.value)
    assert "PSH and bash behavior differs for: echo probe" in text   # existing text kept
    assert "Notes: probe" in text
    assert text.rstrip().endswith(oracle_summary())


def test_documented_difference_and_extension_failures_name_the_oracle():
    with pytest.raises(AssertionError) as info:
        _Probe(ConformanceResult.IDENTICAL).assert_documented_difference("echo probe", "D-1")
    assert oracle_summary() in str(info.value)
    with pytest.raises(AssertionError) as info:
        _Probe(ConformanceResult.IDENTICAL).assert_psh_extension("echo probe")
    assert oracle_summary() in str(info.value)


def test_failure_line_survives_an_unavailable_oracle(monkeypatch):
    def unavailable():
        raise BashOracleUnavailable("none")
    monkeypatch.setattr(conformance_framework, "oracle_summary", unavailable)
    assert conformance_framework._oracle_line() == "oracle: UNAVAILABLE (none)"
