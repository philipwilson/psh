"""
Comprehensive conformance testing framework.

Provides infrastructure for comparing PSH behavior with bash and POSIX
standards, tracking differences, and documenting compatibility.

Oracle resolution and case execution are OWNED by the shared harness module
``tests/harness/shell_oracle.py`` (campaign E2): ``resolve_bash()`` is the one
bash-resolution ladder and ``run_shell_case()`` is the one typed runner.  A
harness failure (spawn failure, timeout, decode failure) is rejected BEFORE
any stdout/status/stderr comparison — two identical failures must never
classify as conformance (continuation finding G).
"""

import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "harness"))
from shell_oracle import (  # noqa: E402
    Completed,
    ShellRunResult,
    hermetic_shell_env,
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
    HARNESS failure (spawn/timeout/decode); ``conformance`` is then
    ``TEST_ERROR`` and ``notes`` names the typed failure.  Harness failures
    never reach the behavior comparison.
    """
    command: str
    psh_result: Optional[CommandResult]
    bash_result: Optional[CommandResult]
    conformance: ConformanceResult
    difference_id: Optional[str] = None
    notes: Optional[str] = None


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

        A harness failure (spawn failure, timeout, decode failure) raises
        :class:`OracleHarnessFailure` — it is NOT rendered as a fake exit
        code, so callers can never compare two failures as behavior.
        """
        run = self._run_typed(command, shell_cmd, env, timeout)
        if not isinstance(run, Completed):
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

        Harness failures are rejected BEFORE the behavior comparison: a run
        that did not complete makes the outcome ``TEST_ERROR`` with the typed
        failure named in ``notes``.  In particular, two IDENTICAL harness
        failures never classify as ``IDENTICAL`` (continuation finding G).
        """
        psh_run = self._run_typed(command, self.psh_path,
                                  self._psh_env(env), timeout)
        bash_run = self._run_typed(command, self.bash_path, env, timeout)

        harness_notes = []
        if not isinstance(psh_run, Completed):
            harness_notes.append(f"psh harness failure: {psh_run!r}")
        if not isinstance(bash_run, Completed):
            harness_notes.append(f"bash harness failure: {bash_run!r}")
        if harness_notes:
            return ComparisonResult(
                command=command,
                psh_result=(self._completed_to_result(psh_run, self.psh_path, command)
                            if isinstance(psh_run, Completed) else None),
                bash_result=(self._completed_to_result(bash_run, self.bash_path, command)
                             if isinstance(bash_run, Completed) else None),
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

    def _is_documented_difference(self, command: str, psh_result: CommandResult,
                                bash_result: CommandResult) -> bool:
        """Check if difference is documented in catalog."""
        # Simple command matching - could be enhanced with pattern matching
        return command in self.differences_catalog.get("documented", {})

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
        )

    def assert_documented_difference(self, command: str, difference_id: str,
                                   env: Dict[str, str] = None):
        """Assert behavior differs in documented way."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)

        assert result.conformance == ConformanceResult.DOCUMENTED_DIFFERENCE, (
            f"Expected documented difference {difference_id} for: {command}\n"
            f"Actual conformance: {result.conformance}"
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
            f"Actual conformance: {result.conformance}"
        )

    def check_behavior(self, command: str, env: Dict[str, str] = None) -> ComparisonResult:
        """Check behavior without assertion (for investigation)."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)
        return result
