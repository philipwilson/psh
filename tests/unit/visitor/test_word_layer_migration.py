"""Pins the R9.B3 visitor Word-layer migration.

The metrics and linter visitors now read variable/command-substitution
structure from the Word parts instead of regexing the rendered argument
string. These tests pin the resulting (more accurate) behavior.
"""

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.linter_visitor import LinterVisitor
from psh.visitor.metrics_visitor import MetricsVisitor


def _lint_quote_msgs(src):
    v = LinterVisitor()
    v.visit(parse(tokenize(src)))
    return [i.message for i in v.issues if "Unquoted variable" in i.message]


def _cmdsubs(src):
    v = MetricsVisitor()
    v.visit(parse(tokenize(src)))
    return v.metrics.command_substitutions


# --- linter: structured unquoted-variable detection ---------------------

def test_rm_unquoted_variable_warns():
    assert any("rm command" in m for m in _lint_quote_msgs("rm $f"))


def test_rm_quoted_variable_no_warn():
    assert _lint_quote_msgs('rm "$f"') == []


def test_rm_embedded_variable_now_warns():
    """Improvement: a var embedded in a word (pre$f) is caught structurally;
    the old leading-'$' scan missed it."""
    assert any("rm command" in m for m in _lint_quote_msgs("rm pre$f"))


def test_test_command_unquoted_after_operator_warns():
    assert any("test command" in m for m in _lint_quote_msgs("[ x = $y ]"))


def test_test_command_quoted_after_operator_no_warn():
    assert not any("test command" in m for m in _lint_quote_msgs('[ x = "$y" ]'))


# --- metrics: accurate command-substitution counting --------------------

def test_dollar_paren_command_sub_counts_once():
    assert _cmdsubs("echo $(date)") == 1


def test_backtick_command_sub_counts_once():
    """Old regex counted each backtick (2 per pair); structurally it is 1."""
    assert _cmdsubs("echo `date`") == 1


def test_arithmetic_not_counted_as_command_sub():
    """`$((expr))` is arithmetic, not a command substitution."""
    assert _cmdsubs("echo $((1 + 2))") == 0
