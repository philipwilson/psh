"""Golden behavioral tests for psh.

These tests verify end-to-end behavior across the full pipeline:
  input -> tokenization -> parsing -> expansion -> execution -> output

Each test case is defined in golden_cases.yaml and run via subprocess
against psh. Optionally, results can be compared against bash with
the --compare-bash flag.
"""

import sys
import warnings
from pathlib import Path

import pytest
import yaml

# The bash oracle is resolved by the shared harness's resolve_bash() ladder
# (BASH_PATH -> Homebrew -> PATH), not via a bare ``bash`` off PATH. 26 of the
# comparison golden cases use bash-4+ syntax (declare -A, |&, case-mod); on a
# machine whose PATH bash is macOS's stock /bin/bash 3.2 a bare ``bash`` made the
# --compare-bash phase fail on environment rather than behavior (tests-infra
# addendum #2). Execution goes through the typed run_shell_case runner: a
# harness failure (spawn/timeout/decode) raises instead of masquerading as
# case output, each case runs hermetically (all inherited LC_*/LANG stripped,
# fresh temp cwd, own session, bounded file-backed capture).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from shell_oracle import (  # noqa: E402
    Completed,
    hermetic_shell_env,
    resolve_bash,
    run_shell_case,
)

CASES_FILE = Path(__file__).parent / "golden_cases.yaml"


def _deterministic_env(env=None):
    """Hermetic env with a C-locale pin so results are machine-independent.

    psh sorts glob results by ASCII codepoint; bash honours LC_COLLATE, so in a
    UTF-8 locale `echo *` diverges purely on sort order (a dictionary vs. ASCII
    difference, not a real behavioural one). Forcing LC_ALL=C makes both agree
    and keeps the comparison meaningful regardless of the developer's locale.
    The shared hermetic builder additionally STRIPS every inherited LC_* /
    LANG / DISPLAY first, so the developer's terminal locale (e.g. an
    inherited LC_CTYPE) cannot leak into either shell.
    """
    case_env = {"LC_ALL": "C", "LANG": "C"}
    if env:
        case_env.update(env)
    return hermetic_shell_env(case_env)


def _load_cases():
    """Load golden test cases from YAML file."""
    with open(CASES_FILE) as f:
        data = yaml.safe_load(f)
    return data


def _case_ids(cases):
    return [c["name"] for c in cases]


_ALL_CASES = _load_cases()


def _run_case(argv, *, env=None, timeout=10):
    """Run one golden case via the typed runner; harness failures raise."""
    run = run_shell_case(argv, env=_deterministic_env(env), timeout=timeout)
    if not isinstance(run, Completed):
        raise AssertionError(f"harness failure running {argv[0]}: {run!r}")
    return run.stdout, run.stderr, run.returncode


def _run_psh(command: str, *, env=None, timeout=10):
    """Run a command in psh and return (stdout, stderr, returncode)."""
    return _run_case([sys.executable, "-m", "psh", "-c", command],
                     env=env, timeout=timeout)


def _run_bash(command: str, *, env=None, timeout=10):
    """Run a command in bash and return (stdout, stderr, returncode)."""
    return _run_case([resolve_bash().path, "-c", command],
                     env=env, timeout=timeout)


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
    """Compare psh output against bash for conformance verification.

    DELIBERATE LOSS (campaign E2, amended doc): this comparison gates on
    stdout + exit status ONLY.  stderr equality is deliberately not gated —
    shell diagnostic wording legitimately differs (``psh:`` vs ``bash:``
    prefixes, message phrasing), and the psh-only golden path (test_golden)
    plus the conformance framework's IDENTICAL classification both DO assert
    stderr.  The terminal consumer of the dropped fact is this comparison's
    pass/fail verdict; no later semantic consumer sees the stderr text.  A
    stderr-PRESENCE disagreement (one shell diagnosed, the other stayed
    silent) is surfaced as a non-gating warning below.
    """
    if not request.config.getoption("--compare-bash"):
        pytest.skip("--compare-bash not specified")

    # Skip cases explicitly marked as psh-only
    if case.get("psh_only", False):
        pytest.skip("case marked psh_only")

    command = case["command"]

    psh_stdout, psh_stderr, psh_exit = _run_psh(command)
    bash_stdout, bash_stderr, bash_exit = _run_bash(command)

    if bool(psh_stderr) != bool(bash_stderr):
        warnings.warn(
            f"stderr-presence disagreement for {case['name']!r}: "
            f"psh={psh_stderr!r} bash={bash_stderr!r} (non-gating; "
            f"golden comparison gates stdout+status only)",
            stacklevel=1)

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
