"""Tests for FormatterVisitor (the AST formatter behind `psh --format`).

Regression for the bug where subshell and brace-group nodes fell through to
generic_visit and emitted ``# Unknown node: ...`` instead of valid shell.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import FormatterVisitor


def _fmt(src):
    return FormatterVisitor().visit(parse(tokenize(src)))


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ ls; echo done; }",
    "[[ -n $x ]]",
    "( cd /tmp && ls ) > out",
    "{ echo y; } &",
    "if [[ -f f ]]; then ( echo y ); fi",
    "echo a; ( echo b )",
])
def test_no_unknown_node(src):
    """No real node type should produce the '# Unknown node' fallback."""
    assert "# Unknown node" not in _fmt(src)


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ ls; echo done; }",
    "( cd /tmp && ls ) > out",
    "{ echo y; } &",
])
def test_group_round_trip_stable(src):
    """Formatting a group is idempotent and re-parseable."""
    once = _fmt(src)
    twice = FormatterVisitor().visit(parse(tokenize(once)))
    assert once == twice
    assert "# Unknown node" not in once


def test_subshell_uses_parens():
    out = _fmt("( echo hi )")
    assert out.startswith("(")
    assert out.rstrip().endswith(")")
    assert "echo hi" in out


def test_brace_group_uses_braces():
    out = _fmt("{ echo hi; }")
    assert out.startswith("{")
    assert out.rstrip().endswith("}")
    assert "echo hi" in out
