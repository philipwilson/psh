"""
Comprehensive conformance testing framework.

Provides infrastructure for comparing PSH behavior with bash and POSIX
standards, tracking differences, and documenting compatibility.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


def find_bash() -> str:
    """Find the best available bash executable.

    Searches for bash in the following order:
    1. BASH_PATH environment variable (if set)
    2. /opt/homebrew/bin/bash (Apple Silicon Mac with Homebrew)
    3. /usr/local/bin/bash (Intel Mac with Homebrew)
    4. bash in PATH (system bash or CI environment)

    This ensures conformance tests use the latest bash on macOS (via Homebrew)
    while still working in CI environments where bash is in the standard PATH.

    For CI/CD or custom environments, set the BASH_PATH environment variable:
        export BASH_PATH=/usr/bin/bash  # or wherever bash is located
        pytest tests/conformance/

    Returns:
        Path to bash executable as string (not list)
    """
    # Check environment variable first
    if "BASH_PATH" in os.environ:
        bash_path = os.environ["BASH_PATH"]
        if os.path.isfile(bash_path) and os.access(bash_path, os.X_OK):
            return bash_path

    # Check common Homebrew locations (newer bash on macOS)
    homebrew_paths = [
        "/opt/homebrew/bin/bash",  # Apple Silicon
        "/usr/local/bin/bash",      # Intel Mac
    ]

    for path in homebrew_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    # Fall back to bash in PATH (works everywhere, including CI)
    bash_in_path = shutil.which("bash")
    if bash_in_path:
        return bash_in_path

    # Last resort: assume bash is available
    return "bash"


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
    """Result of comparing PSH and bash behavior."""
    command: str
    psh_result: CommandResult
    bash_result: CommandResult
    conformance: ConformanceResult
    difference_id: Optional[str] = None
    notes: Optional[str] = None


class ConformanceTestFramework:
    """Framework for running conformance tests between PSH and bash."""

    def __init__(self, psh_path: str = None, bash_path: str = None):
        """Initialize conformance test framework.

        Args:
            psh_path: Path to PSH executable (default: python -m psh)
            bash_path: Path to bash executable (default: auto-detected best bash)
        """
        self.psh_path = psh_path or [sys.executable, "-m", "psh"]
        bash_exec = bash_path or find_bash()
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

    def run_in_shell(self, command: str, shell_cmd: List[str],
                     env: Dict[str, str] = None, timeout: float = 10.0) -> CommandResult:
        """Run command in specified shell and return result."""
        import time

        # Prepare environment
        test_env = os.environ.copy()
        if env:
            test_env.update(env)

        # For safety, run in temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            start_time = time.time()
            try:
                result = subprocess.run(
                    shell_cmd + ["-c", command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                    env=test_env,
                    cwd=temp_dir
                )
                execution_time = time.time() - start_time

                return CommandResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    execution_time=execution_time,
                    shell=" ".join(shell_cmd),
                    command=command
                )
            except subprocess.TimeoutExpired:
                execution_time = time.time() - start_time
                return CommandResult(
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    exit_code=124,  # timeout exit code
                    execution_time=execution_time,
                    shell=" ".join(shell_cmd),
                    command=command
                )
            except Exception as e:
                execution_time = time.time() - start_time
                return CommandResult(
                    stdout="",
                    stderr=f"Execution error: {str(e)}",
                    exit_code=127,
                    execution_time=execution_time,
                    shell=" ".join(shell_cmd),
                    command=command
                )

    def run_in_psh(self, command: str, env: Dict[str, str] = None,
                   timeout: float = 10.0) -> CommandResult:
        """Run command in PSH."""
        combined_env = dict(env) if env else {}
        existing_path = combined_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
        pythonpath_parts = [self.project_root]
        if existing_path:
            pythonpath_parts.append(existing_path)
        combined_env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        return self.run_in_shell(command, self.psh_path, combined_env, timeout)

    def run_in_bash(self, command: str, env: Dict[str, str] = None,
                    timeout: float = 10.0) -> CommandResult:
        """Run command in bash."""
        return self.run_in_shell(command, self.bash_path, env, timeout)

    def compare_behavior(self, command: str, env: Dict[str, str] = None,
                        timeout: float = 10.0) -> ComparisonResult:
        """Compare PSH and bash behavior for a command."""
        psh_result = self.run_in_psh(command, env, timeout)
        bash_result = self.run_in_bash(command, env, timeout)

        # Determine conformance status
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
        """Analyze conformance between PSH and bash results."""
        # Check for test execution errors (timeout)
        if psh_result.exit_code == 124 or bash_result.exit_code == 124:
            return ConformanceResult.TEST_ERROR

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

        # Check if this is bash-specific behavior
        if self._is_bash_specific(command, psh_result, bash_result):
            return ConformanceResult.BASH_SPECIFIC

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

    def _is_bash_specific(self, command: str, psh_result: CommandResult,
                         bash_result: CommandResult) -> bool:
        """Check if this is bash-specific behavior."""
        # Bash-specific: bash works, PSH doesn't, and it's known bash extension
        return (bash_result.exit_code == 0 and
                psh_result.exit_code != 0 and
                any(pattern in command for pattern in ["[[", "((", "declare -", "local "]))

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
            f"PSH: stdout='{result.psh_result.stdout}' stderr='{result.psh_result.stderr}' exit={result.psh_result.exit_code}\n"
            f"Bash: stdout='{result.bash_result.stdout}' stderr='{result.bash_result.stderr}' exit={result.bash_result.exit_code}"
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

    def assert_bash_specific(self, command: str, env: Dict[str, str] = None):
        """Assert this is bash-specific behavior (bash supports, PSH doesn't)."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)

        assert result.conformance == ConformanceResult.BASH_SPECIFIC, (
            f"Expected bash-specific behavior for: {command}\n"
            f"Actual conformance: {result.conformance}"
        )

    def check_behavior(self, command: str, env: Dict[str, str] = None) -> ComparisonResult:
        """Check behavior without assertion (for investigation)."""
        result = self.framework.compare_behavior(command, env)
        self.results.append(result)
        return result

    def get_results_summary(self) -> Dict[str, int]:
        """Get summary of conformance test results."""
        summary = {}
        for result_type in ConformanceResult:
            summary[result_type.value] = sum(
                1 for r in self.results if r.conformance == result_type
            )
        return summary

    def save_results(self, filepath: str):
        """Save results to JSON file for analysis."""
        data = {
            "summary": self.get_results_summary(),
            "results": [
                {
                    "command": r.command,
                    "conformance": r.conformance.value,
                    "difference_id": r.difference_id,
                    "psh": {
                        "stdout": r.psh_result.stdout,
                        "stderr": r.psh_result.stderr,
                        "exit_code": r.psh_result.exit_code,
                        "execution_time": r.psh_result.execution_time
                    },
                    "bash": {
                        "stdout": r.bash_result.stdout,
                        "stderr": r.bash_result.stderr,
                        "exit_code": r.bash_result.exit_code,
                        "execution_time": r.bash_result.execution_time
                    }
                }
                for r in self.results
            ]
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)


# POSIX compliance helper functions
def is_posix_required(feature: str) -> bool:
    """Check if feature is required by POSIX."""
    posix_required = {
        "parameter_expansion", "command_substitution", "arithmetic_expansion",
        "tilde_expansion", "pathname_expansion", "quote_removal",
        "simple_commands", "pipelines", "lists", "compound_commands",
        "if_constructs", "while_loops", "for_loops", "case_constructs",
        "function_definitions", "shell_functions", "shell_parameters",
        "special_parameters", "shell_variables", "shell_expansions"
    }
    return feature in posix_required


def get_posix_test_commands() -> List[str]:
    """Get list of commands for POSIX compliance testing."""
    return [
        # Parameter expansion
        'x=hello; echo ${x}',
        'x=hello; echo ${x:-default}',
        'x=; echo ${x:-default}',
        'unset x; echo ${x:-default}',
        'x=hello; echo ${x:+set}',
        'x=; echo ${x:+set}',

        # Command substitution
        'echo $(echo hello)',
        'echo `echo hello`',
        'echo $(echo $(echo nested))',

        # Arithmetic expansion
        'echo $((2 + 3))',
        'echo $((10 - 4))',
        'echo $((3 * 4))',
        'echo $((15 / 3))',
        'echo $((17 % 5))',

        # Tilde expansion
        'echo ~',
        'echo ~/test',

        # Pathname expansion
        'echo *',
        'echo *.txt',
        'echo [abc]*',

        # Quote removal
        'echo "hello world"',
        "echo 'hello world'",
        'echo hello\\ world',

        # Simple commands
        'echo hello',
        'true',
        'false',

        # Pipelines
        'echo hello | cat',
        'echo -e "line1\\nline2" | wc -l',

        # Lists
        'true && echo success',
        'false || echo failure',
        'true; echo done',

        # Compound commands
        'if true; then echo yes; fi',
        'while false; do echo never; done',
        'for i in 1 2 3; do echo $i; done',
        'case hello in hello) echo match;; esac',

        # Function definitions
        'f() { echo function; }; f',
        'function f { echo function; }; f',
    ]
