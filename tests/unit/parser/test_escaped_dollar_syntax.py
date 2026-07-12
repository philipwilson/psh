"""Test parser handling of escaped dollar followed by parenthesis."""

import subprocess
import sys

import pytest

from psh.ast_nodes import FunctionDef, SubshellGroup
from psh.lexer import tokenize
from psh.parser import ParseError, Parser


class TestEscapedDollarSyntax:
    r"""Test that PSH correctly rejects \$( as a syntax error like bash does."""

    def test_escaped_dollar_paren_is_syntax_error(self):
        r"""Test that \$( produces a syntax error matching bash behavior."""
        # This is a syntax error in bash: echo \$(echo test)
        tokens = tokenize(r'echo \$(echo test)')
        parser = Parser(tokens)

        with pytest.raises(ParseError) as exc_info:
            parser.parse()

        assert "syntax error near unexpected token '('" in str(exc_info.value)

    def test_escaped_dollar_alone_is_valid(self):
        r"""Test that \$ alone is valid."""
        tokens = tokenize(r'echo \$')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_normal_command_substitution_is_valid(self):
        """Test that normal command substitution works."""
        tokens = tokenize(r'echo $(echo test)')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_escaped_dollar_and_parens_is_valid(self):
        r"""Test that \$\(...\) is valid (all escaped)."""
        tokens = tokenize(r'echo \$\(echo test\)')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_escaped_dollar_in_quotes_is_valid(self):
        r"""Test that "\$(echo test)" is valid."""
        tokens = tokenize(r'echo "\$(echo test)"')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_multiple_escaped_dollars(self):
        """Test various multiple escape scenarios."""
        # \\$(echo test) should work - double backslash then command sub
        tokens = tokenize(r'echo \\$(echo test)')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

        # \\\$(echo test) should fail - escaped dollar then paren
        tokens = tokenize(r'echo \\\$(echo test)')
        parser = Parser(tokens)

        with pytest.raises(ParseError) as exc_info:
            parser.parse()

        assert "syntax error near unexpected token '('" in str(exc_info.value)

    def test_escaped_dollar_at_end(self):
        """Test that escaped dollar at end of command works."""
        tokens = tokenize(r'\$')
        parser = Parser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_escaped_dollar_with_just_paren(self):
        r"""Test \$( with nothing after is also an error."""
        tokens = tokenize(r'\$(')
        parser = Parser(tokens)

        with pytest.raises(ParseError) as exc_info:
            parser.parse()

        assert "syntax error near unexpected token '('" in str(exc_info.value)


def _parse(text):
    return Parser(tokenize(text), source_text=text).parse()


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=60)


class TestEscapedDollarFunctionNames:
    r"""A function NAME ending in an escaped dollar is not the `\$(` error.

    `function f\$ (echo hi)` is a keyword-form definition whose name token
    ends in odd-backslash+`$`, followed by a subshell BODY. That is legal at
    PARSE time (bash 5.2 parses it too; bash then rejects the name at RUN
    time as "not a valid identifier", while psh defines the function — the
    caller's `f\$` expands to `f$` and finds nothing, so both shells
    observably yield command-not-found rc 127).

    `_reject_escaped_dollar_paren` reads the PREVIOUS token looking for the
    `echo \$(...)` argument shape; once function bodies routed through
    `_parse_compound_component` (H12) it misfired on the function-name token
    (r19-B3 bounce blocker). The chokepoint suppresses the check for
    function bodies (`in_function_body=True`); these pins hold the line for
    the name shapes and prove the argument-position check still fires
    (TestEscapedDollarSyntax above keeps the original error pinned).
    """

    def _assert_funcdef_with_subshell_body(self, ast, name):
        func = ast.statements[0]
        assert isinstance(func, FunctionDef)
        assert func.name == name
        assert isinstance(func.body.statements[0], SubshellGroup)

    def test_keyword_form_escaped_dollar_name_subshell_body_parses(self):
        r"""`function f\$ (echo hi)` — the bounce blocker — must parse."""
        ast = _parse(r'function f\$ (echo hi)')
        self._assert_funcdef_with_subshell_body(ast, r'f\$')

    def test_keyword_form_escaped_dollar_name_runs_to_127(self):
        r"""Defining and calling `f\$` is command-not-found (rc 127), the
        same observable outcome as bash 5.2."""
        r = _psh_c(r'function f\$ (echo hi); f\$')
        assert r.returncode == 127, (r.returncode, r.stderr)
        assert 'Parse error' not in r.stderr
        assert 'command not found' in r.stderr

    def test_posix_form_escaped_dollar_name_subshell_body(self):
        r"""`f\$() (echo hi)` — the `()` marker sits between name and body,
        so the check never saw the name here; keep it that way."""
        ast = _parse(r'f\$() (echo hi)')
        self._assert_funcdef_with_subshell_body(ast, r'f\$')
        r = _psh_c(r'f\$() (echo hi); f\$')
        assert r.returncode == 127, (r.returncode, r.stderr)
        assert 'Parse error' not in r.stderr

    def test_keyword_form_escaped_dollar_name_brace_body(self):
        r"""`function f\$ { echo hi; }` — brace body, no LPAREN branch."""
        ast = _parse(r'function f\$ { echo hi; }')
        func = ast.statements[0]
        assert isinstance(func, FunctionDef)
        assert func.name == r'f\$'
        r = _psh_c(r'function f\$ { echo hi; }; f\$')
        assert r.returncode == 127, (r.returncode, r.stderr)

    def test_even_backslash_name_subshell_body_parses(self):
        r"""`function f\\$ (echo hi)` — even backslash count: the dollar is
        not escaped, and the check never fired for this shape anyway."""
        ast = _parse(r'function f\\$ (echo hi)')
        func = ast.statements[0]
        assert isinstance(func, FunctionDef)
        assert isinstance(func.body.statements[0], SubshellGroup)

    def test_argument_position_check_still_fires_after_suppression(self):
        r"""The suppression is scoped to function bodies: the original
        `echo \$(...)` argument-position error must survive intact."""
        with pytest.raises(ParseError) as exc_info:
            _parse(r'echo \$(date)')
        assert "syntax error near unexpected token '('" in str(exc_info.value)
