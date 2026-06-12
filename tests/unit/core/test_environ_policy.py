"""os.environ read-once policy (v0.312).

os.environ is read once at ShellState startup; state.env is the live
environment and is passed explicitly to every child.  Nothing in psh
writes os.environ after startup — these tests pin that: each mutation
path (export, allexport, `VAR=x exec`, export -n) must update state.env
and leave the hosting process's os.environ untouched.

The pre-fix counterexample was the exec leak: `FOO=bar exec` wrote
os.environ and never restored it (invisible to children, who already
receive state.env explicitly — but it leaked into the host process).
"""

import os


class TestEnvironReadOncePolicy:
    def test_export_does_not_write_os_environ(self, captured_shell):
        name = 'PSH_ENVPOLICY_EXPORT'
        assert name not in os.environ
        captured_shell.run_command(f'export {name}=val')
        assert captured_shell.state.env.get(name) == 'val'
        assert name not in os.environ

    def test_allexport_does_not_write_os_environ(self, captured_shell):
        name = 'PSH_ENVPOLICY_ALLEXPORT'
        assert name not in os.environ
        captured_shell.run_command(f'set -a; {name}=val; set +a')
        assert captured_shell.state.env.get(name) == 'val'
        assert name not in os.environ

    def test_exec_assignment_does_not_leak_into_os_environ(self, captured_shell):
        """The v0.312 exec-leak fix: `FOO=bar exec` must not write
        os.environ.  (bash 5.2, probe-verified: the assignment does not
        persist in the shell either — `FOO=bar exec; echo $FOO` prints
        nothing — and psh matches.)"""
        name = 'PSH_ENVPOLICY_EXEC'
        assert name not in os.environ
        captured_shell.run_command(f'{name}=bar exec')
        assert name not in os.environ
        assert name not in captured_shell.state.env  # matches bash

    def test_export_n_does_not_touch_os_environ(self, captured_shell, monkeypatch):
        """export -n removes from state.env; the runner's os.environ entry
        (if any) is not psh's to remove."""
        name = 'PSH_ENVPOLICY_EXPORT_N'
        monkeypatch.setenv(name, 'host-value')
        captured_shell.run_command(f'export {name}=v2; export -n {name}')
        assert name not in captured_shell.state.env
        assert os.environ[name] == 'host-value'

    def test_child_sees_export_via_explicit_env(self, captured_shell):
        """Children receive state.env explicitly — exports are visible to
        them without any os.environ write."""
        name = 'PSH_ENVPOLICY_CHILD'
        captured_shell.run_command(
            f'export {name}=seen; {name}_OUT=$(/usr/bin/printenv {name})')
        assert captured_shell.state.get_variable(f'{name}_OUT') == 'seen'
        assert name not in os.environ
