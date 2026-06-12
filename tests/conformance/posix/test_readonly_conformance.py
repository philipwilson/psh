"""Readonly-variable assignment conformance (pinned to bash 5.2).

Probe battery: tmp/readonly_probes*.sh (2026-06-12).  Key behavior: a
readonly assignment in a command PREFIX (``RO=2 cmd``) reports the error
but still runs the command — the exit status is the command's own (127
for a missing command).  A PURE readonly assignment (``RO=2``) aborts a
non-interactive shell with status 1.  Under ``set -e`` the prefix error
becomes fatal and the command does NOT run.

Diagnostics go to stderr with different shell-name prefixes, so the
error cases compare stdout/exit-code via check_behavior and only assert
that both shells diagnosed on stderr.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestReadonlyPrefixAssignment(ConformanceTest):
    """RO=2 cmd: error reported, command still runs (bash 5.2)."""

    def _assert_same_stdout_and_status(self, command):
        result = self.check_behavior(command)
        assert result.psh_result.stdout == result.bash_result.stdout, command
        assert result.psh_result.exit_code == result.bash_result.exit_code, command
        assert bool(result.psh_result.stderr) == bool(result.bash_result.stderr), command

    def test_prefix_with_builtin_runs_status_0(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2 true; echo rc=$?')

    def test_prefix_with_builtin_output_still_printed(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2 echo ran; echo rc=$?')

    def test_prefix_with_external_runs(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2 /bin/echo ext; echo rc=$?')

    def test_prefix_with_function_runs_and_sees_old_value(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; f() { echo fn $RO; }; RO=2 f; echo rc=$?')

    def test_prefix_with_missing_command_is_127(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2 definitely_not_a_command_xyz; echo rc=$?')

    def test_prefix_command_exit_status_preserved(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2 false; echo rc=$?')

    def test_other_prefix_assignments_remain_temporary(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; OK=5 RO=2 true; echo "rc=$? OK=[$OK]"')

    def test_failed_assignment_not_in_child_environment(self):
        self._assert_same_stdout_and_status(
            'export RO=1; readonly RO; '
            'RO=2 sh -c \'echo "env-RO=[$RO]"\'; echo rc=$?')

    def test_pure_readonly_assignment_aborts_shell(self):
        self._assert_same_stdout_and_status(
            'RO=1; readonly RO; RO=2; echo not-reached')

    def test_errexit_makes_prefix_error_fatal_without_running(self):
        self._assert_same_stdout_and_status(
            'set -e; RO=1; readonly RO; RO=2 echo did-run; echo after')
