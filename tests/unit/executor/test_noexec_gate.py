"""Unit guards for the two noexec owners (slot 1.10, C040).

Owner 1 — the per-statement gate in
``psh/executor/core.py#ExecutorVisitor._execute_sequence``. It is asked BEFORE
each statement, so a flag flipped by an earlier statement of the SAME list
stops the rest of that list. Repro:
``psh -c 'echo before; set -n; touch marker; echo after'`` prints only
``before``.

Owner 2 — the refusal in
``psh/builtins/environment.py#apply_set_o_option``. bash will not turn noexec
on in an interactive shell at all, so ``$-`` never grows an ``n``; the
command line is exempt because bash parses invocation flags before it decides
the shell is interactive.

The behaviour these guards protect is pinned against bash in
tests/conformance/bash/test_noexec_per_statement_conformance.py; these hold the
two decision sites themselves, with synthetic option state.
"""
import pytest

from psh.builtins.environment import apply_set_o_option
from psh.shell import Shell


class TestPerStatementGate:
    """The gate stops the REST of the statement list, not the next unit."""

    def test_flag_set_mid_list_stops_the_rest_of_that_list(self, captured_shell):
        rc = captured_shell.run_command("echo before; set -n; echo after")
        assert captured_shell.get_stdout() == "before\n"
        assert rc == 0

    def test_gate_is_asked_before_every_statement(self, captured_shell):
        """Synthetic state: with noexec already on, a whole list runs nothing
        and reports success — the gate's own answer, no `set` builtin involved."""
        captured_shell.state.options['noexec'] = True
        try:
            rc = captured_shell.run_command("echo a; echo b; false; echo c")
        finally:
            captured_shell.state.options['noexec'] = False
        assert captured_shell.get_stdout() == ""
        assert rc == 0

    def test_gate_applies_inside_a_nested_statement_list(self, captured_shell):
        """visit_StatementList shares the gate: a function body, a loop body
        and a brace group are all sequences, so all stop at the flag."""
        captured_shell.run_command(
            "f() { echo in1; set -n; echo in2; }; f; echo tail")
        assert captured_shell.get_stdout() == "in1\n"

    def test_a_skipped_statement_contributes_success(self, captured_shell):
        """bash returns EXECUTION_SUCCESS for a skipped command, so neither
        `false` nor `exit 7` can change the status once the flag is on."""
        assert captured_shell.run_command("set -n; false") == 0
        assert captured_shell.run_command("set -n; exit 7") == 0

    def test_setting_the_flag_back_off_is_itself_skipped(self, captured_shell):
        rc = captured_shell.run_command("set -n; set +n; echo after")
        assert captured_shell.get_stdout() == ""
        assert rc == 0
        # The option is still on in this shell — `set +n` never ran.
        assert captured_shell.state.options['noexec'] is True
        captured_shell.state.options['noexec'] = False


class TestInteractiveRefusal:
    """An interactive shell refuses to turn noexec on (bash 5.3.15, probed at
    a pty). The refusal is silent and leaves the option OFF."""

    @pytest.fixture
    def shell(self):
        created = Shell(norc=True)
        yield created
        created.state.options['noexec'] = False

    def test_non_interactive_shell_accepts_it(self, shell):
        shell.state.options['interactive'] = False
        apply_set_o_option(shell, 'noexec', True)
        assert shell.state.options['noexec'] is True

    def test_interactive_shell_refuses_it(self, shell):
        shell.state.options['interactive'] = True
        try:
            apply_set_o_option(shell, 'noexec', True)
            assert shell.state.options['noexec'] is False
            # $- must not grow an `n` either — that readout is the observable.
            assert 'n' not in shell.state.options.option_string()
        finally:
            shell.state.options['interactive'] = False

    def test_the_command_line_is_exempt(self, shell):
        """`bash -i -n` really does execute nothing: bash parses invocation
        flags before it decides the shell is interactive."""
        shell.state.options['interactive'] = True
        try:
            apply_set_o_option(shell, 'noexec', True, from_invocation=True)
            assert shell.state.options['noexec'] is True
        finally:
            shell.state.options['interactive'] = False

    def test_turning_it_OFF_is_never_refused(self, shell):
        """The refusal is on the ENABLE direction only — `set +n` in an
        interactive shell that inherited the flag from `-n` must still work."""
        shell.state.options['interactive'] = True
        shell.state.options['noexec'] = True
        try:
            apply_set_o_option(shell, 'noexec', False)
            assert shell.state.options['noexec'] is False
        finally:
            shell.state.options['interactive'] = False

    def test_short_flag_and_long_option_agree(self, shell):
        """`set -n` routes through the SAME toggle engine as `set -o noexec`,
        so a short flag can never bypass the refusal."""
        shell.state.options['interactive'] = True
        try:
            shell.run_command("set -n")
            assert shell.state.options['noexec'] is False
            shell.run_command("set -o noexec")
            assert shell.state.options['noexec'] is False
            shell.run_command("shopt -so noexec")
            assert shell.state.options['noexec'] is False
        finally:
            shell.state.options['interactive'] = False

    def test_other_short_flags_still_toggle(self, shell):
        """Discrimination: routing the short cluster through the toggle engine
        must not change any OTHER flag's behaviour."""
        shell.run_command("set -eu")
        assert shell.state.options['errexit'] is True
        assert shell.state.options['nounset'] is True
        shell.run_command("set +eu")
        assert shell.state.options['errexit'] is False
        assert shell.state.options['nounset'] is False
