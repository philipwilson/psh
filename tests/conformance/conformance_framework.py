"""
Comprehensive conformance testing framework.

Provides infrastructure for comparing PSH behavior with bash and POSIX
standards, tracking differences, and documenting compatibility.

Oracle resolution and case execution are OWNED by the shared harness module
``tests/harness/shell_oracle.py`` (campaign E2): ``resolve_bash()`` is the one
bash-resolution ladder and ``run_shell_case()`` is the one typed runner.  A
non-comparable observation (spawn failure, timeout, output-limit breach, or
decode failure — anything ``is_comparable()`` rejects) is rejected BEFORE any
stdout/status/stderr comparison — two identical failures, including two runaway
commands both truncated at the output cap, must never classify as conformance
(continuation finding G / reappraisal #22 HIGH-1).
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "harness"))
from oracle_policy import oracle_summary  # noqa: E402
from shell_oracle import (  # noqa: E402
    BashOracleUnavailable,
    Completed,
    ShellRunResult,
    hermetic_shell_env,
    is_comparable,
    resolve_bash,
    run_shell_case,
)


class OracleHarnessFailure(AssertionError):
    """A differential run failed in the HARNESS, not in shell behavior.

    Raised by the direct ``run_in_psh``/``run_in_bash``/``run_in_shell``
    helpers so a caller can never mistake a spawn failure, timeout, or decode
    failure for a comparable shell result.  Carries the typed variant.
    """

    def __init__(self, shell: str, result: ShellRunResult):
        self.shell = shell
        self.result = result
        super().__init__(f"harness failure running {shell}: {result!r}")


class ConformanceResult(Enum):
    """Result of conformance test comparison."""
    IDENTICAL = "identical"
    DOCUMENTED_DIFFERENCE = "documented_difference"
    PSH_EXTENSION = "psh_extension"
    PSH_BUG = "psh_bug"
    BASH_SPECIFIC = "bash_specific"
    TEST_ERROR = "test_error"


@dataclass
class CommandResult:
    """Result of running a command in a shell."""
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    shell: str
    command: str


@dataclass
class ComparisonResult:
    """Result of comparing PSH and bash behavior.

    ``psh_result``/``bash_result`` are ``None`` for a side whose run was a
    non-comparable observation (spawn failure, timeout, output-limit breach,
    or decode failure — anything :func:`is_comparable` rejects); ``conformance``
    is then ``TEST_ERROR`` and ``notes`` names the typed failure.  Non-comparable
    observations never reach the behavior comparison.
    """
    command: str
    psh_result: Optional[CommandResult]
    bash_result: Optional[CommandResult]
    conformance: ConformanceResult
    difference_id: Optional[str] = None
    notes: Optional[str] = None


def _oracle_line() -> str:
    """``oracle: <path> <version>`` for failure messages (D1): a differential
    failure must say WHICH bash produced the reference side."""
    try:
        return oracle_summary()
    except BashOracleUnavailable as e:
        return f"oracle: UNAVAILABLE ({e})"


def _fmt_side(result: Optional[CommandResult]) -> str:
    """Human-readable one-line rendering of one side for assertion messages."""
    if result is None:
        return "harness failure (no comparable result)"
    return (f"stdout={result.stdout!r} stderr={result.stderr!r} "
            f"exit={result.exit_code}")


class ConformanceTestFramework:
    """Framework for running conformance tests between PSH and bash."""

    def __init__(self, psh_path: str = None, bash_path: str = None):
        """Initialize conformance test framework.

        Args:
            psh_path: Path to PSH executable (default: python -m psh)
            bash_path: Path to bash executable (default: the resolve_bash()
                oracle — BASH_PATH -> Homebrew -> PATH, never bare ``bash``)
        """
        self.psh_path = psh_path or [sys.executable, "-m", "psh"]
        bash_exec = bash_path or resolve_bash().path
        self.bash_path = bash_exec if isinstance(bash_exec, list) else [bash_exec]
        self.project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.differences_catalog = {}
        self.load_differences_catalog()

    def load_differences_catalog(self):
        """Load catalog of documented PSH vs bash differences."""
        catalog_path = os.path.join(
            os.path.dirname(__file__),
            "differences",
            "psh_bash_differences.json"
        )
        if os.path.exists(catalog_path):
            with open(catalog_path, 'r') as f:
                self.differences_catalog = json.load(f)

    def _run_typed(self, command: str, shell_cmd: List[str],
                   env: Dict[str, str] = None,
                   timeout: float = 10.0) -> ShellRunResult:
        """Run command in the given shell, returning the TYPED runner result.

        The environment is hermetic (all inherited ``LC_*``/``LANG`` and
        ``DISPLAY`` stripped by the shared builder) with the suite's locale
        pin (``LC_ALL=C``/``LANG=C`` — so sort order, error messages, and glob
        ranges don't drift by machine) applied first and the case's own ``env``
        layered on top.  Output decoding is UTF-8 + surrogateescape (lossless,
        so psh-vs-bash byte comparison stays exact even for cases that emit
        UTF-8 while running under the C-locale pin).  Each case runs in its
        own temporary directory inside a fresh session, with bounded output.
        """
        case_env = {'LC_ALL': 'C', 'LANG': 'C'}
        if env:
            case_env.update(env)
        return run_shell_case(
            shell_cmd + ["-c", command],
            env=hermetic_shell_env(case_env),
            timeout=timeout,
        )

    @staticmethod
    def _completed_to_result(run: Completed, shell_cmd: List[str],
                             command: str) -> CommandResult:
        return CommandResult(
            stdout=run.stdout,
            stderr=run.stderr,
            exit_code=run.returncode,
            execution_time=run.duration,
            shell=" ".join(shell_cmd),
            command=command,
        )

    def run_in_shell(self, command: str, shell_cmd: List[str],
                     env: Dict[str, str] = None, timeout: float = 10.0) -> CommandResult:
        """Run command in specified shell and return its completed result.

        A non-comparable observation (spawn failure, timeout, output-limit
        breach, decode failure) raises :class:`OracleHarnessFailure` — it is
        NOT rendered as a fake exit code, so callers can never compare two
        failures as behavior.
        """
        run = self._run_typed(command, shell_cmd, env, timeout)
        if not is_comparable(run):
            raise OracleHarnessFailure(" ".join(shell_cmd), run)
        return self._completed_to_result(run, shell_cmd, command)

    def run_in_psh(self, command: str, env: Dict[str, str] = None,
                   timeout: float = 10.0) -> CommandResult:
        """Run command in PSH."""
        return self.run_in_shell(command, self.psh_path,
                                 self._psh_env(env), timeout)

    def _psh_env(self, env: Dict[str, str] = None) -> Dict[str, str]:
        """psh case env: the caller's env plus PYTHONPATH for this tree."""
        combined_env = dict(env) if env else {}
        existing_path = combined_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
        pythonpath_parts = [self.project_root]
        if existing_path:
            pythonpath_parts.append(existing_path)
        combined_env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        return combined_env

    def run_in_bash(self, command: str, env: Dict[str, str] = None,
                    timeout: float = 10.0) -> CommandResult:
        """Run command in bash."""
        return self.run_in_shell(command, self.bash_path, env, timeout)

    def compare_behavior(self, command: str, env: Dict[str, str] = None,
                        timeout: float = 10.0) -> ComparisonResult:
        """Compare PSH and bash behavior for a command.

        Non-comparable observations are rejected BEFORE the behavior comparison:
        a run that :func:`is_comparable` rejects (spawn failure, timeout,
        output-limit breach, decode failure) makes the outcome ``TEST_ERROR``
        with the typed failure named in ``notes``.  In particular, two IDENTICAL
        harness failures — including two runaway commands both truncated at the
        output cap — never classify as ``IDENTICAL`` (continuation finding G /
        reappraisal #22 HIGH-1).
        """
        psh_run = self._run_typed(command, self.psh_path,
                                  self._psh_env(env), timeout)
        bash_run = self._run_typed(command, self.bash_path, env, timeout)

        harness_notes = []
        if not is_comparable(psh_run):
            harness_notes.append(f"psh harness failure: {psh_run!r}")
        if not is_comparable(bash_run):
            harness_notes.append(f"bash harness failure: {bash_run!r}")
        if harness_notes:
            return ComparisonResult(
                command=command,
                psh_result=(self._completed_to_result(psh_run, self.psh_path, command)
                            if is_comparable(psh_run) else None),
                bash_result=(self._completed_to_result(bash_run, self.bash_path, command)
                             if is_comparable(bash_run) else None),
                conformance=ConformanceResult.TEST_ERROR,
                notes="; ".join(harness_notes),
            )

        psh_result = self._completed_to_result(psh_run, self.psh_path, command)
        bash_result = self._completed_to_result(bash_run, self.bash_path, command)

        # Determine conformance status (both sides COMPLETED — harness
        # failures were rejected above and never reach this comparison).
        conformance = self._analyze_conformance(psh_result, bash_result, command)

        # Look up difference ID if documented
        difference_id = self._get_difference_id(command, conformance)

        return ComparisonResult(
            command=command,
            psh_result=psh_result,
            bash_result=bash_result,
            conformance=conformance,
            difference_id=difference_id
        )

    def _analyze_conformance(self, psh_result: CommandResult,
                           bash_result: CommandResult, command: str) -> ConformanceResult:
        """Analyze conformance between two COMPLETED results.

        Harness failures (spawn/timeout/decode) are typed and rejected in
        :meth:`compare_behavior` before this point; the old exit-code-124
        timeout sentinel is gone with them.
        """
        # Check for identical behavior
        if (psh_result.stdout == bash_result.stdout and
            psh_result.stderr == bash_result.stderr and
            psh_result.exit_code == bash_result.exit_code):
            return ConformanceResult.IDENTICAL

        # Check if this is a documented difference
        if self._is_documented_difference(command, psh_result, bash_result):
            return ConformanceResult.DOCUMENTED_DIFFERENCE

        # Check if this is a PSH extension (check before command not found error)
        if self._is_psh_extension(command, psh_result, bash_result):
            return ConformanceResult.PSH_EXTENSION

        # Check for command not found errors (after checking extensions)
        if psh_result.exit_code == 127 or bash_result.exit_code == 127:
            return ConformanceResult.TEST_ERROR

        # Otherwise, assume PSH bug
        return ConformanceResult.PSH_BUG

    @staticmethod
    def _matches_side(expected: Dict[str, Any], result: CommandResult) -> bool:
        """Does one shell's observed result match its expected shape?

        `exit_code` is exact; `stdout_pattern`/`stderr_pattern` are regex
        SEARCHES, so an entry can pin a whole stream (`^...$`) or just the
        part that identifies the difference. An absent key is not checked.

        A side that checks NOTHING does not match. Without that rule an
        `expected` block carrying only prose (e.g. ``{"note": "..."}``) would
        vacuously satisfy every observation and re-open exactly the blind
        classification F1 closed — a guard present but empty. So a side must
        constrain at least one of exit status, stdout, or stderr. The
        catalog-shape meta-test enforces the same requirement statically;
        this is the RUNTIME half, so a hand-edited catalog cannot bypass it.
        """
        checkable = {"exit_code", "stdout_pattern", "stderr_pattern"}
        if not checkable & set(expected):
            return False
        if "exit_code" in expected and result.exit_code != expected["exit_code"]:
            return False
        for key, observed in (("stdout_pattern", result.stdout),
                              ("stderr_pattern", result.stderr)):
            pattern = expected.get(key)
            if pattern is not None and not re.search(pattern, observed):
                return False
        return True

    def _is_documented_difference(self, command: str, psh_result: CommandResult,
                                bash_result: CommandResult) -> bool:
        """Is the OBSERVED divergence the one this command is documented for?

        Membership in the catalog is necessary but NOT sufficient. Each entry
        carries the expected SHAPE of its difference (per-side exit status and
        output patterns) and the observation must match it.

        This used to be `command in catalog['documented']`, which never looked
        at either result: any future divergence on a catalogued command — a
        genuine regression included — classified as DOCUMENTED_DIFFERENCE, so
        the pins on those commands could not fail for the right reason. An
        observation that no longer matches its entry is NOT documented; either
        the difference changed or a shell regressed, and both deserve a
        failure rather than a silent blessing.

        An entry cannot classify unless BOTH sides actually constrain
        something. A missing `expected` block, a missing `psh`/`bash` side, or
        a side that names no checkable key all return False here rather than
        waving the observation through — see :meth:`_matches_side`. Stating it
        precisely because an earlier version of this docstring implied the
        catalog-shape meta-test was the whole guarantee: that test only
        asserted an `expected` key was PRESENT, so a block containing nothing
        but prose satisfied it while checking nothing at runtime. Both halves
        now enforce the same rule —
        `test_every_documented_entry_carries_an_expected_shape` statically,
        this method at runtime.
        """
        entry = self.differences_catalog.get("documented", {}).get(command)
        if entry is None:
            return False
        expected = entry.get("expected")
        if not expected:
            return False
        # Side lookups are written as `in` + subscript rather than
        # `.get("bash", {})` on purpose: the E2 oracle-resolution ratchet
        # (tests/unit/tooling/test_bash_oracle_resolution.py) flags the string
        # "bash" as a call's first argument or a list's first element, since
        # that is what a bare-bash spawn looks like. These are catalog KEYS,
        # not an oracle invocation — keep them out of those two shapes.
        psh_expected = expected["psh"] if "psh" in expected else {}
        bash_expected = expected["bash"] if "bash" in expected else {}
        return (self._matches_side(psh_expected, psh_result)
                and self._matches_side(bash_expected, bash_result))

    def _is_psh_extension(self, command: str, psh_result: CommandResult,
                         bash_result: CommandResult) -> bool:
        """Check if this is a PSH extension (PSH succeeds, bash fails)."""
        # PSH extension: PSH works, bash doesn't
        return (psh_result.exit_code == 0 and
                bash_result.exit_code != 0 and
                "command not found" in bash_result.stderr)

    def _get_difference_id(self, command: str, conformance: ConformanceResult) -> Optional[str]:
        """Get difference ID from catalog."""
        if conformance == ConformanceResult.DOCUMENTED_DIFFERENCE:
            return self.differences_catalog.get("documented", {}).get(command, {}).get("id")
        return None


class ConformanceTest:
    """Base class for conformance tests."""

    @property
    def framework(self):
        """Get or create conformance test framework."""
        if not hasattr(self, '_framework'):
            self._framework = ConformanceTestFramework()
        return self._framework

    @property
    def results(self):
        """Get or create results list."""
        if not hasattr(self, '_results'):
            self._results: List[ComparisonResult] = []
        return self._results

    def assert_identical_behavior(self, command: str, env: Dict[str, str] = None):
        """Assert PSH and bash produce identical results."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)

        assert result.conformance == ConformanceResult.IDENTICAL, (
            f"PSH and bash behavior differs for: {command}\n"
            f"PSH: {_fmt_side(result.psh_result)}\n"
            f"Bash: {_fmt_side(result.bash_result)}"
            + (f"\nNotes: {result.notes}" if result.notes else "")
            + f"\n{_oracle_line()}"
        )

    def assert_documented_difference(self, command: str, difference_id: str,
                                   env: Dict[str, str] = None):
        """Assert behavior differs in documented way."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)

        assert result.conformance == ConformanceResult.DOCUMENTED_DIFFERENCE, (
            f"Expected documented difference {difference_id} for: {command}\n"
            f"Actual conformance: {result.conformance}\n{_oracle_line()}"
        )

        assert result.difference_id == difference_id, (
            f"Expected difference ID {difference_id}, got {result.difference_id}"
        )

    def assert_psh_extension(self, command: str, env: Dict[str, str] = None):
        """Assert this is a PSH extension (PSH supports, bash doesn't)."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)

        assert result.conformance == ConformanceResult.PSH_EXTENSION, (
            f"Expected PSH extension for: {command}\n"
            f"Actual conformance: {result.conformance}\n{_oracle_line()}"
        )

    def check_behavior(self, command: str, env: Dict[str, str] = None) -> ComparisonResult:
        """Check behavior without a CONFORMANCE assertion (for investigation).

        Harness completedness IS asserted: every caller dereferences
        ``psh_result``/``bash_result``, so a spawn/timeout/decode failure
        surfaces here as a typed diagnostic instead of an ``AttributeError``
        on a ``None`` side downstream.
        """
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)
        assert result.psh_result is not None and result.bash_result is not None, (
            f"harness failure (not shell behavior) for {command!r}: {result.notes}")
        return result
