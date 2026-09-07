"""Unit guards for the two noexec owners (slot 1.10, C040).

Owner 1 — the per-statement gate in
``psh/executor/core.py#ExecutorVisitor._execute_sequence``. It is asked BEFORE
each statement, so a flag flipped by an earlier statement of the SAME list
stops the rest of that list. Repro:
``psh -c 'echo before; set -n; touch marker; echo after'`` prints only
``before``.

Owner 2 — the refusal in
``psh/builtins/environment.py#apply_set_o_option``. bash will not turn noexec
on for a shell in the session the user is typing at, so ``$-`` never grows an
``n``; the command line is exempt because bash parses invocation flags before
it decides the shell is interactive.

Owner 3 — the fact owner 2 reads: ``options['interactive_session']``,
established once by the top-level shell, INHERITED across every fork, and
dropped by ``psh/executor/child_policy.py#leave_interactive_session``. Keying
owner 2 on the per-child ``interactive`` flag instead made a command
substitution of an interactive shell silently yield the empty string (verify
round 1, B2); the scope is pinned at a real terminal in
tests/system/interactive/test_noexec_interactive_pty.py.

The behaviour these guards protect is pinned against bash in
tests/conformance/bash/test_noexec_per_statement_conformance.py; these hold the
two decision sites themselves, with synthetic option state.
"""
import pytest

from psh.builtins.environment import apply_set_o_option
from psh.executor.child_policy import leave_interactive_session
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
        shell.state.options['interactive_session'] = False
        apply_set_o_option(shell, 'noexec', True)
        assert shell.state.options['noexec'] is True

    def test_interactive_shell_refuses_it(self, shell):
        shell.state.options['interactive_session'] = True
        try:
            apply_set_o_option(shell, 'noexec', True)
            assert shell.state.options['noexec'] is False
            # $- must not grow an `n` either — that readout is the observable.
            assert 'n' not in shell.state.options.option_string()
        finally:
            shell.state.options['interactive_session'] = False

    def test_the_per_child_interactive_flag_is_NOT_the_predicate(self, shell):
        """The round-1 defect, pinned: a command-substitution child recomputes
        `interactive` to False while still belonging to the session, so keying
        the refusal on it let `x=$(set -n; echo hi)` lose the value."""
        shell.state.options['interactive'] = False
        shell.state.options['interactive_session'] = True
        try:
            apply_set_o_option(shell, 'noexec', True)
            assert shell.state.options['noexec'] is False
        finally:
            shell.state.options['interactive_session'] = False

    def test_the_command_line_is_exempt(self, shell):
        """`bash -i -n` really does execute nothing: bash parses invocation
        flags before it decides the shell is interactive."""
        shell.state.options['interactive_session'] = True
        try:
            apply_set_o_option(shell, 'noexec', True, from_invocation=True)
            assert shell.state.options['noexec'] is True
        finally:
            shell.state.options['interactive_session'] = False

    def test_turning_it_OFF_is_never_refused(self, shell):
        """The refusal is on the ENABLE direction only — `set +n` in an
        interactive shell that inherited the flag from `-n` must still work."""
        shell.state.options['interactive_session'] = True
        shell.state.options['noexec'] = True
        try:
            apply_set_o_option(shell, 'noexec', False)
            assert shell.state.options['noexec'] is False
        finally:
            shell.state.options['interactive_session'] = False

    def test_short_flag_and_long_option_agree(self, shell):
        """`set -n` routes through the SAME toggle engine as `set -o noexec`,
        so a short flag can never bypass the refusal."""
        shell.state.options['interactive_session'] = True
        try:
            shell.run_command("set -n")
            assert shell.state.options['noexec'] is False
            shell.run_command("set -o noexec")
            assert shell.state.options['noexec'] is False
            shell.run_command("shopt -so noexec")
            assert shell.state.options['noexec'] is False
        finally:
            shell.state.options['interactive_session'] = False

    def test_other_short_flags_still_toggle(self, shell):
        """Discrimination: routing the short cluster through the toggle engine
        must not change any OTHER flag's behaviour."""
        shell.run_command("set -eu")
        assert shell.state.options['errexit'] is True
        assert shell.state.options['nounset'] is True
        shell.run_command("set +eu")
        assert shell.state.options['errexit'] is False
        assert shell.state.options['nounset'] is False


class TestSessionFactOwnership:
    """`interactive_session` is established once and inherited, and there is
    exactly ONE place that drops it."""

    def test_a_child_shell_inherits_it(self):
        parent = Shell(norc=True)
        parent.state.options['interactive_session'] = True
        child = Shell.for_subshell(parent)
        assert child.state.options['interactive_session'] is True
        # …while `interactive` is recomputed per child and may disagree. That
        # divergence is the whole reason the two facts are separate.
        assert 'interactive' in child.state.options

    def test_a_child_of_a_non_session_shell_stays_out(self):
        parent = Shell(norc=True)
        parent.state.options['interactive_session'] = False
        child = Shell.for_subshell(parent)
        assert child.state.options['interactive_session'] is False

    def test_leaving_the_session_drops_it(self):
        shell = Shell(norc=True)
        shell.state.options['interactive_session'] = True
        leave_interactive_session(shell)
        assert shell.state.options['interactive_session'] is False
        # …and the refusal then lets noexec through, which is what an async
        # compound child needs.
        apply_set_o_option(shell, 'noexec', True)
        assert shell.state.options['noexec'] is True

    def test_leaving_is_idempotent_and_safe_off_session(self):
        shell = Shell(norc=True)
        shell.state.options['interactive_session'] = False
        leave_interactive_session(shell)
        leave_interactive_session(shell)
        assert shell.state.options['interactive_session'] is False

    def test_it_has_no_dollar_dash_letter_and_no_set_o_spelling(self):
        """bash exposes no such flag, so neither does psh: it must not leak
        into `$-` or become settable by name."""
        from psh.core.option_registry import OPTION_REGISTRY, OptionCategory
        spec = OPTION_REGISTRY['interactive_session']
        assert spec.dollar_dash is None
        assert spec.short_flag is None
        assert spec.category is OptionCategory.INTERNAL
        shell = Shell(norc=True)
        shell.state.options['interactive'] = False
        shell.state.options['interactive_session'] = False
        before = shell.state.options.option_string()
        shell.state.options['interactive_session'] = True
        assert shell.state.options.option_string() == before, (
            "interactive_session leaked into $-; the `i` letter belongs to "
            "`interactive`, which a child recomputes")
        rc = shell.run_command("set -o interactive_session")
        assert rc != 0, "an INTERNAL option must not be settable by name"
