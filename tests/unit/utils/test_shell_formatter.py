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


class TestCStyleForAndLoopControl:
    """Regression (reappraisal #10 R12.B): ShellFormatter referenced AST
    attributes that don't exist — CStyleForLoop.init/.condition/.update (real:
    init_expr/condition_expr/update_expr) and Break/Continue.levels (real:
    .level) — so formatting these (e.g. via `declare -f`) raised AttributeError.
    check_untyped_defs surfaced it.
    """

    def test_c_style_for_formats_without_error(self):
        out = _fmt("for ((i=0; i<3; i++)); do echo $i; done")
        assert "for ((i=0; i<3; i++))" in out
        assert "# Unknown node type" not in out

    def test_c_style_for_empty_sections(self):
        out = _fmt("for ((;;)); do echo x; done")
        assert "for ((; ; ))" in out

    def test_break_with_level(self):
        out = _fmt("while true; do break 2; done")
        assert "break 2" in out

    def test_continue_with_level(self):
        out = _fmt("while true; do continue 3; done")
        assert "continue 3" in out

    def test_break_without_level(self):
        assert "break" in _fmt("while true; do break; done")


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
