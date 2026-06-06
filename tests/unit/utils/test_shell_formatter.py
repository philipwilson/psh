"""Tests for ShellFormatter AST -> shell-syntax reconstruction.

Regression for the bug where real compound node types (subshells, brace groups,
[[ ]] tests) fell through to the ``# Unknown node type: ...`` fallback, producing
output that is a comment rather than valid shell.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.utils.shell_formatter import ShellFormatter


def _fmt(src):
    return ShellFormatter.format(parse(tokenize(src)))


@pytest.mark.parametrize("src, expected", [
    ("( echo a; echo b )", "( echo a; echo b )"),
    ("{ echo a; echo b; }", "{ echo a; echo b; }"),
    ("[[ -n $x ]]", "[[ -n $x ]]"),
    ("[[ $a == b && $c != d ]]", "[[ $a == b && $c != d ]]"),
    ("[[ ! -f /tmp/x ]]", "[[ ! -f /tmp/x ]]"),
    ("{ echo y; } &", "{ echo y; } &"),
])
def test_formats_compound_nodes(src, expected):
    assert _fmt(src) == expected


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ echo a; echo b; }",
    "[[ -n $x ]]",
    "[[ $a == b && $c != d ]]",
    "[[ ! -f /tmp/x ]]",
    "echo a; ( cd /tmp && ls )",
    "if [[ -f f ]]; then echo y; fi",
    "while [[ $i -lt 3 ]]; do echo $i; done",
    "( echo x ) > out",
])
def test_no_unknown_node_type(src):
    """No real node type should reach the broken '# Unknown node type' fallback."""
    assert "# Unknown node type" not in _fmt(src)


@pytest.mark.parametrize("src", [
    "( echo a; echo b )",
    "{ echo a; echo b; }",
    "[[ -n $x ]]",
    "if [[ -f f ]]; then echo y; fi",
    "while [[ $i -lt 3 ]]; do echo $i; done",
])
def test_round_trip_is_stable(src):
    """Formatting is idempotent: format -> parse -> format yields the same text."""
    once = _fmt(src)
    twice = ShellFormatter.format(parse(tokenize(once)))
    assert once == twice
