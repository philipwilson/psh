"""Golden behavioral tests for psh.

These tests verify end-to-end behavior across the full pipeline:
  input -> tokenization -> parsing -> expansion -> execution -> output

Each test case is defined in golden_cases.yaml and run via subprocess
against psh. Optionally, results can be compared against bash with
the --compare-bash flag.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# The bash oracle is resolved the SAME way the conformance framework resolves it
# (BASH_PATH -> Homebrew -> PATH), not via a bare ``bash`` off PATH. 26 of the
# comparison golden cases use bash-4+ syntax (declare -A, |&, case-mod); on a
# machine whose PATH bash is macOS's stock /bin/bash 3.2 a bare ``bash`` made the
# --compare-bash phase fail on environment rather than behavior (tests-infra
# addendum #2). find_bash() picks the newest available bash consistently.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conformance"))
from conformance_framework import find_bash  # noqa: E402

CASES_FILE = Path(__file__).parent / "golden_cases.yaml"


def _deterministic_env(env=None):
    """Pin a C locale so glob collation etc. is reproducible across machines.

    psh sorts glob results by ASCII codepoint; bash honours LC_COLLATE, so in a
    UTF-8 locale `echo *` diverges purely on sort order (a dictionary vs. ASCII
    difference, not a real behavioural one). Forcing LC_ALL=C makes both agree
    and keeps the comparison meaningful regardless of the developer's locale.
    """
    base = dict(os.environ if env is None else env)
    base["LC_ALL"] = "C"
    base["LANG"] = "C"
    return base


def _load_cases():
    """Load golden test cases from YAML file."""
    with open(CASES_FILE) as f:
        data = yaml.safe_load(f)
    return data


def _case_ids(cases):
    return [c["name"] for c in cases]


_ALL_CASES = _load_cases()


def _run_psh(command: str, *, env=None, timeout=10):
    """Run a command in psh and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_deterministic_env(env),
    )
    return result.stdout, result.stderr, result.returncode


def _run_bash(command: str, *, env=None, timeout=10):
    """Run a command in bash and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        [find_bash(), "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_deterministic_env(env),
    )
    return result.stdout, result.stderr, result.returncode


@pytest.mark.parametrize("case", _ALL_CASES, ids=_case_ids(_ALL_CASES))
def test_golden(case):
    """Run a single golden behavioral test case."""
    command = case["command"]
    expected_stdout = case.get("stdout", "")
    expected_stderr = case.get("stderr", "")
    expected_exit = case.get("exit_code", 0)

    stdout, stderr, exit_code = _run_psh(command)

    if expected_stdout is not None:
        assert stdout == expected_stdout, (
            f"stdout mismatch for {case['name']!r}\n"
            f"  command: {command!r}\n"
            f"  expected: {expected_stdout!r}\n"
            f"  got:      {stdout!r}"
        )

    if expected_stderr is not None:
        if expected_stderr == "":
            assert stderr == "", (
                f"unexpected stderr for {case['name']!r}\n"
                f"  command: {command!r}\n"
                f"  stderr:  {stderr!r}"
            )
        else:
            assert expected_stderr in stderr, (
                f"stderr mismatch for {case['name']!r}\n"
                f"  command: {command!r}\n"
                f"  expected (substring): {expected_stderr!r}\n"
                f"  got: {stderr!r}"
            )

    assert exit_code == expected_exit, (
        f"exit code mismatch for {case['name']!r}\n"
        f"  command: {command!r}\n"
        f"  expected: {expected_exit}\n"
        f"  got:      {exit_code}"
    )


@pytest.mark.parametrize("case", _ALL_CASES, ids=_case_ids(_ALL_CASES))
def test_golden_bash_comparison(case, request):
    """Compare psh output against bash for conformance verification."""
    if not request.config.getoption("--compare-bash"):
        pytest.skip("--compare-bash not specified")

    # Skip cases explicitly marked as psh-only
    if case.get("psh_only", False):
        pytest.skip("case marked psh_only")

    command = case["command"]

    psh_stdout, psh_stderr, psh_exit = _run_psh(command)
    bash_stdout, bash_stderr, bash_exit = _run_bash(command)

    assert psh_stdout == bash_stdout, (
        f"stdout divergence for {case['name']!r}\n"
        f"  command: {command!r}\n"
        f"  bash: {bash_stdout!r}\n"
        f"  psh:  {psh_stdout!r}"
    )
    assert psh_exit == bash_exit, (
        f"exit code divergence for {case['name']!r}\n"
        f"  command: {command!r}\n"
        f"  bash: {bash_exit}\n"
        f"  psh:  {psh_exit}"
    )
