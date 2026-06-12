"""Tests for Shell construction lifecycle: for_subshell inheritance and
the absence of implicit attribute forwarding.

Shell used to forward arbitrary attribute reads/writes to ShellState via
__getattr__/__setattr__ magic; that was retired in favor of four explicit
properties (stdout/stderr/stdin/env) and `shell.state.<attr>` everywhere
else. These tests pin the replacement semantics.
"""

import pytest

from psh.core.variables import VarAttributes
from psh.shell import Shell


class TestForSubshell:
    """Pin Shell.for_subshell inheritance semantics (what a subshell copies)."""

    def test_child_inherits_environment_as_copy(self, captured_shell):
        captured_shell.run_command("export PARENT_VAR=hello")
        child = Shell.for_subshell(captured_shell)
        assert child.env["PARENT_VAR"] == "hello"
        # A copy, not a shared dict: child mutations don't leak to the parent.
        child.env["CHILD_ONLY"] = "x"
        assert "CHILD_ONLY" not in captured_shell.env

    def test_child_inherits_variables_with_attributes(self, captured_shell):
        captured_shell.run_command("readonly RO_VAR=fixed")
        captured_shell.run_command("plain=value")
        child = Shell.for_subshell(captured_shell)
        assert child.state.get_variable("plain") == "value"
        var = child.state.scope_manager.get_variable_object("RO_VAR")
        assert var is not None
        assert var.attributes & VarAttributes.READONLY

    def test_child_inherits_functions_and_aliases_as_copies(self, captured_shell):
        captured_shell.run_command("greet() { echo hi; }")
        captured_shell.run_command("alias ll='ls -l'")
        child = Shell.for_subshell(captured_shell)
        assert child.function_manager.get_function("greet") is not None
        assert child.alias_manager.has_alias("ll")
        # Copies: defining in the child must not appear in the parent.
        child.run_command("child_fn() { echo c; }")
        child.run_command("alias ca='cat'")
        assert captured_shell.function_manager.get_function("child_fn") is None
        assert not captured_shell.alias_manager.has_alias("ca")

    def test_child_inherits_options_exit_code_and_positionals(self, captured_shell):
        captured_shell.run_command("set -e -o pipefail")
        captured_shell.run_command("set -- a b c")
        captured_shell.run_command("false || true")
        captured_shell.state.last_exit_code = 7
        child = Shell.for_subshell(captured_shell)
        assert child.state.options["errexit"] is True
        assert child.state.options["pipefail"] is True
        assert child.state.positional_params == ["a", "b", "c"]
        assert child.state.last_exit_code == 7

    def test_child_inherits_pid_identity_and_pipestatus(self, captured_shell):
        captured_shell.state.pipestatus = [0, 1]
        child = Shell.for_subshell(captured_shell)
        # $$ and $PPID keep the original shell's identity (POSIX).
        assert child.state.shell_pid == captured_shell.state.shell_pid
        assert child.state.initial_ppid == captured_shell.state.initial_ppid
        assert child.state.pipestatus == [0, 1]
        assert child.state.pipestatus is not captured_shell.state.pipestatus

    def test_child_does_not_inherit_jobs(self, captured_shell):
        child = Shell.for_subshell(captured_shell)
        assert child.job_manager is not captured_shell.job_manager
        assert not child.job_manager.jobs

    def test_child_skips_rc_loading_by_default(self, captured_shell):
        child = Shell.for_subshell(captured_shell)
        assert child.state.norc is True

    def test_child_keeps_parent_parser_choice(self, captured_shell):
        captured_shell.active_parser = "combinator"
        child = Shell.for_subshell(captured_shell)
        assert child.active_parser == "combinator"


class TestNoImplicitForwarding:
    """The __getattr__/__setattr__ forwarding magic must stay retired."""

    def test_shell_has_no_getattr_hook(self):
        assert "__getattr__" not in Shell.__dict__
        assert "__setattr__" not in Shell.__dict__

    def test_typoed_attribute_raises(self, captured_shell):
        with pytest.raises(AttributeError):
            captured_shell.last_exit_codee  # noqa: B018 — typo must not forward

    def test_state_attrs_are_not_forwarded(self, captured_shell):
        # Names that used to forward to state must now raise.
        with pytest.raises(AttributeError):
            captured_shell.positional_params  # noqa: B018

    def test_big_four_write_through_to_state(self, captured_shell):
        import io
        buf = io.StringIO()
        captured_shell.stdout = buf
        assert captured_shell.state.stdout is buf
        captured_shell.stderr = buf
        assert captured_shell.state.stderr is buf
        captured_shell.stdin = buf
        assert captured_shell.state.stdin is buf
        env = {"A": "1"}
        captured_shell.env = env
        assert captured_shell.state.env is env
