"""Internal expansion failures must propagate, not become literal output.

Regression tests for the v0.300 hardening of ExpansionManager.expand_expansion
and VariableExpander.expand_variable: previously, AttributeError/TypeError/
ValueError raised inside expansion evaluation were swallowed and the literal
text (or str() of the AST node) was silently emitted instead. Internal bugs
must fail loudly; genuine user-facing errors arrive as ExpansionError /
UnboundVariableError with bash-matching messages and exit codes.
"""

import pytest

from psh.ast_nodes import ParameterExpansion, VariableExpansion


class TestInternalErrorsPropagate:
    """Implementation defects must raise, not degrade to literal text."""

    def test_attribute_error_propagates_from_expand_expansion(self, shell, monkeypatch):
        """An AttributeError inside the evaluator is an internal bug: it must
        propagate out of expand_expansion, not be returned as str(node)."""
        ve = shell.expansion_manager.variable_expander

        def boom(*args, **kwargs):
            raise AttributeError("internal bug in VariableExpander")

        monkeypatch.setattr(ve, 'expand_variable', boom)
        node = VariableExpansion(name='HOME')
        with pytest.raises(AttributeError, match="internal bug"):
            shell.expansion_manager.expand_expansion(node)

    def test_type_error_propagates_from_expand_expansion(self, shell, monkeypatch):
        ve = shell.expansion_manager.variable_expander

        def boom(*args, **kwargs):
            raise TypeError("internal bug")

        monkeypatch.setattr(ve, 'expand_parameter_direct', boom)
        node = ParameterExpansion(parameter='x', operator='#', word='y')
        with pytest.raises(TypeError, match="internal bug"):
            shell.expansion_manager.expand_expansion(node)

    def test_unknown_expansion_type_raises(self, shell):
        """A non-expansion object reaching the evaluator is a parser/executor
        bug and must raise (the evaluator's documented ValueError)."""
        with pytest.raises(ValueError, match="Unknown expansion type"):
            shell.expansion_manager.expand_expansion(object())

    def test_operator_bug_does_not_degrade_to_plain_var(self, shell, monkeypatch):
        """A bug in operator application must not silently fall through to
        plain-${var} expansion (the pre-v0.300 behavior of the swallowed
        except in VariableExpander.expand_variable)."""
        ve = shell.expansion_manager.variable_expander
        shell.state.set_variable('x', 'plainvalue')

        def boom(*args, **kwargs):
            raise AttributeError("operator handler bug")

        monkeypatch.setattr(ve, 'expand_parameter_direct', boom)
        with pytest.raises(AttributeError, match="operator handler bug"):
            ve.expand_variable('${x#pat}')


class TestUserFacingErrorsStillWork:
    """Genuine user errors keep bash-matching rc and messages.

    Verified against bash 2026-06-11:
        x=abc; echo "${x:0:-5}"   -> 'bash: -5: substring expression < 0', rc 1
        x=abcdefgh; echo "${x:0:-5}" -> 'abc', rc 0
        echo ${!noexist}          -> 'bash: noexist: invalid indirect expansion', rc 1
    """

    def test_negative_substring_length_errors_like_bash(self, captured_shell):
        rc = captured_shell.run_command('x=abc; echo "${x:0:-5}"')
        assert rc == 1
        assert 'substring expression < 0' in captured_shell.get_stderr()
        # Crucially: NOT the literal text of the expansion
        assert 'ParameterExpansion' not in captured_shell.get_stdout()
        assert '${x:0:-5}' not in captured_shell.get_stdout()

    def test_valid_negative_substring_length_still_works(self, captured_shell):
        rc = captured_shell.run_command('x=abcdefgh; echo "${x:0:-5}"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'abc\n'

    def test_invalid_indirect_expansion_errors_like_bash(self, captured_shell):
        rc = captured_shell.run_command('echo "${!noexist_xyz}"')
        assert rc == 1
        assert 'invalid indirect expansion' in captured_shell.get_stderr()

    def test_var_question_message_still_aborts(self, captured_shell):
        rc = captured_shell.run_command('echo "${unset_xyz:?custom msg}"')
        assert rc != 0
        assert 'custom msg' in captured_shell.get_stderr()

    def test_operator_expansions_unaffected(self, captured_shell):
        rc = captured_shell.run_command(
            'x=abcdef; echo "${x:1:3}" "${x#ab}" "${x/cd/CD}" "${x^^}"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'bcd cdef abCDef ABCDEF\n'
