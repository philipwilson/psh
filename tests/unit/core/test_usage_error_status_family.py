"""The ONE special-builtin usage-error status family (owner unit tests).

`psh/core/internal_errors.py` states the family in one place; every consumer
builtin (`exit`, `shift`, `return`, `cd`, `break`, `continue`) reaches one of
its three named outcomes and spells no status literal of its own.  These tests
drive the owner DIRECTLY with synthetic states -- command_mode on/off, posix
on/off, script vs interactive, inside a substitution -- so a consumer's own
end-to-end pin cannot be the only thing holding the rule up.

bash 5.3.15 statuses (empirical, no CHANGES/NEWS item; probed 2026-09-06 in
-c, script-file and stdin modes).  The behavioral three-mode pins live in
tests/conformance/bash/test_exit_cd_options_conformance.py.
"""

import pytest

from psh.core.exceptions import SpecialBuiltinUsageError, TopLevelAbort
from psh.core.internal_errors import (
    USAGE_ERROR_STATUS,
    special_builtin_usage_discard,
    special_builtin_usage_exit_shell,
    special_builtin_usage_status,
    usage_discard_child_status,
)


def test_family_status_is_two():
    """bash 5.3.15 moved every cell of this family from 1 to 2."""
    assert USAGE_ERROR_STATUS == 2


class TestTooManyArgumentsDiscard:
    """`exit 7 8` / `shift 1 2` / `return 3 4` / `break 1 2`."""

    @pytest.mark.parametrize("posix", [False, True])
    def test_script_mode_discards_line_with_family_status(self, shell, posix):
        """Reproduce: printf 'exit 1 2\\necho after=$?\\n' > s.sh; bash s.sh."""
        shell.state.options['command_mode'] = False
        shell.state.options['posix'] = posix
        with pytest.raises(TopLevelAbort) as exc:
            special_builtin_usage_discard(shell.state)
        assert exc.value.status == USAGE_ERROR_STATUS == 2
        # errexit-immune: the next line runs even under set -e; and the
        # discard is NOT contained by eval/source, it reaches the top-level
        # input loop.
        assert exc.value.errexit_immune is True
        assert exc.value.contain_nested is False

    @pytest.mark.parametrize("posix", [False, True])
    def test_command_mode_abandons_string_with_one(self, shell, posix):
        """The -c leg did NOT move in 5.3: bash -c 'exit 1 2' still exits 1."""
        shell.state.options['command_mode'] = True
        shell.state.options['posix'] = posix
        with pytest.raises(SystemExit) as exc:
            special_builtin_usage_discard(shell.state)
        assert exc.value.code == 1

    def test_abort_is_stamped_for_the_fork_shape_channel(self, shell):
        """The discard's forked-child status depends on the fork SHAPE, so the
        abort must carry the stamp both boundaries key on."""
        shell.state.options['command_mode'] = False
        with pytest.raises(TopLevelAbort) as exc:
            special_builtin_usage_discard(shell.state)
        assert exc.value.usage_discard_channel is True

    def test_command_mode_abandon_publishes_its_status(self, shell):
        """The EXIT trap runs after the abandon and reads $?, so the status
        must be recorded before the raise (bash: `trap 'echo $?' EXIT;
        exit 1 2` under -c prints 1)."""
        shell.state.options['command_mode'] = True
        shell.state.last_exit_code = 0
        with pytest.raises(SystemExit):
            special_builtin_usage_discard(shell.state)
        assert shell.state.last_exit_code == 1


class TestForkShapeStatus:
    """usage_discard_child_status: 1 for a bare-simple fork or anything under
    a substitution, 2 for a forked compound/function. Same severing rule bash
    applies to an ignored `set -e`."""

    def test_main_shell_keeps_the_family_status(self, shell):
        shell.state.forked_simple_command = False
        shell.state.in_substitution = False
        assert usage_discard_child_status(shell.state) == USAGE_ERROR_STATUS

    def test_bare_simple_fork_reports_one(self, shell):
        shell.state.forked_simple_command = True
        shell.state.in_substitution = False
        assert usage_discard_child_status(shell.state) == 1

    def test_pending_shape_reads_as_simple(self, shell):
        """None is the PIPELINE site's pending stamp: a SimpleCommand node was
        forked before anyone knew what it dispatches, and no FUNCTION dispatch
        reclassified it. Every other fork site records True or False at the
        fork -- the background site in particular, because a backgrounded
        builtin never reaches command.py's dispatch chokepoint and a pending
        stamp there would be settled by the builtin's own TEXT instead."""
        shell.state.forked_simple_command = None
        shell.state.in_substitution = False
        assert usage_discard_child_status(shell.state) == 1

    def test_substitution_reports_one_whatever_the_shape(self, shell):
        shell.state.in_substitution = True
        for shape in (False, True, None):
            shell.state.forked_simple_command = shape
            assert usage_discard_child_status(shell.state) == 1

    def test_only_a_function_dispatch_writes_false(self, shell):
        """`f | cat` is 2 because the member names a compound body; the flag
        that says so is the ONLY way to get 2 out of a simple-node fork."""
        shell.state.in_substitution = False
        shell.state.forked_simple_command = False
        assert usage_discard_child_status(shell.state) == USAGE_ERROR_STATUS


class TestNumericArgumentOperandCell:
    """`exit abc` / `shift abc` -- report, then CONTINUE with the status."""

    def test_raises_the_suppressible_typed_outcome(self):
        """The typed outcome is what couples the cell to POSIX mode: the ONE
        posix exit policy (special_builtin_usage_exit, reached from the builtin
        guard) decides exit-vs-fail, and `command`/`builtin` strip it."""
        with pytest.raises(SpecialBuiltinUsageError) as exc:
            special_builtin_usage_status()
        assert exc.value.status == USAGE_ERROR_STATUS == 2
        assert exc.value.suppressible is True

    def test_status_is_overridable_but_defaults_to_the_family(self):
        with pytest.raises(SpecialBuiltinUsageError) as exc:
            special_builtin_usage_status(7)
        assert exc.value.status == 7


class TestBadCountBreakContinueExit:
    """`break abc` / `continue abc` -- EXIT the shell, every input mode."""

    @pytest.mark.parametrize("posix", [False, True])
    @pytest.mark.parametrize("command_mode", [False, True])
    def test_script_mode_exits_with_the_family_status(self, shell, posix,
                                                      command_mode):
        """Unlike the discard cell there is no -c/script split, and no posix
        split: bash exits 2 in all four combinations."""
        shell.state.is_script_mode = True
        shell.state.options['posix'] = posix
        shell.state.options['command_mode'] = command_mode
        with pytest.raises(SystemExit) as exc:
            special_builtin_usage_exit_shell(shell)
        assert exc.value.code == USAGE_ERROR_STATUS == 2
        assert shell.state.last_exit_code == 2


    def test_interactive_discards_the_line(self, shell):
        """bash -i does not exit on `break abc` -- and it does not carry on
        either. Verified over a PTY: it drops the REST OF THE LINE and the
        next prompt shows $? = 2 (no loop body, no same=). So the interactive
        leg is the DISCARD cell, which is why this is NoReturn in both legs.
        The PTY pin is
        tests/system/interactive/test_usage_status_interactive_pty.py.
        """
        shell.state.is_script_mode = False
        shell.state.options['command_mode'] = False
        shell.state.last_exit_code = 0
        with pytest.raises(TopLevelAbort) as exc:
            special_builtin_usage_exit_shell(shell)
        assert exc.value.status == USAGE_ERROR_STATUS == 2
        assert exc.value.usage_discard_channel is True
        assert shell.state.last_exit_code == USAGE_ERROR_STATUS

    def test_the_exit_publishes_its_status_for_the_exit_trap(self, shell):
        shell.state.is_script_mode = True
        shell.state.last_exit_code = 0
        with pytest.raises(SystemExit):
            special_builtin_usage_exit_shell(shell)
        assert shell.state.last_exit_code == USAGE_ERROR_STATUS == 2
