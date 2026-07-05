"""Function-name rules (reappraisal #15 cluster D2).

bash's name policy is permissive: any single word that is not a reserved
word can name a function — including builtin names (functions shadow
builtins in lookup order), dashes, dots, digits, and punctuation. Reserved
words are rejected by the PARSER (syntax error, rc 2), while the runtime
FunctionManager only rejects empty/whitespace names and readonly
redefinitions — and those route as expected shell errors, not through the
"unexpected error" defect guard.
"""

import pytest

from psh.ast_nodes import StatementList
from psh.core.exceptions import FunctionDefinitionError
from psh.core.functions import FunctionManager


class TestFunctionManagerNamePolicy:
    @pytest.mark.parametrize("name", [
        'true', 'false', 'exit', 'return', 'break', 'continue',
        'my-func', '.dot', 'f.g', '1fn', 'a@b', 'a:b', 'a/b', ':', '[', ']',
    ])
    def test_bash_valid_names_accepted(self, name):
        mgr = FunctionManager()
        mgr.define_function(name, StatementList())
        assert mgr.get_function(name) is not None

    @pytest.mark.parametrize("name", ['', 'a b', 'a\tb'])
    def test_empty_or_whitespace_names_rejected(self, name):
        mgr = FunctionManager()
        with pytest.raises(FunctionDefinitionError):
            mgr.define_function(name, StatementList())

    def test_readonly_redefinition_rejected_with_bash_message(self):
        mgr = FunctionManager()
        mgr.define_function('f', StatementList())
        mgr.set_function_readonly('f')
        with pytest.raises(FunctionDefinitionError, match=r'f: readonly function'):
            mgr.define_function('f', StatementList())


class TestDefinitionErrorRouting:
    """Definition-time errors are expected shell errors, not defects."""

    def test_readonly_redefine_reports_and_continues(self, captured_shell):
        rc = captured_shell.run_command(
            'f(){ :; }; readonly -f f; f(){ echo x; }; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=1\n'
        stderr = captured_shell.get_stderr()
        assert 'readonly function' in stderr
        assert 'unexpected error' not in stderr


class TestParserNameRules:
    """Reserved words fail at parse time (rc 2), like bash."""

    @pytest.mark.parametrize("src", ['if(){ :; }', 'while(){ :; }',
                                     'do(){ :; }', 'in(){ :; }'])
    def test_reserved_word_name_is_syntax_error(self, captured_shell, src):
        rc = captured_shell.run_command(src)
        assert rc == 2
        # The exact wording varies by which parse rule trips first
        # ("syntax error near unexpected token" vs "Expected command").
        assert 'error' in captured_shell.get_stderr()

    def test_function_keyword_form_accepts_reserved_word(self, captured_shell):
        # bash: `function if { ...; }` defines a function named "if"
        # (callable only via quoting, but the definition succeeds, rc 0).
        rc = captured_shell.run_command('function if { :; }')
        assert rc == 0

    def test_bracket_function_name(self, captured_shell):
        rc = captured_shell.run_command('[(){ echo lb; }; [')
        assert rc == 0
        assert captured_shell.get_stdout() == 'lb\n'
