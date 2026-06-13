"""Characterization + regression pins for [[ ]] test-operand semantics.

Created for the Tier C-D2 refactor that brought BinaryTestExpression
operands into the Word model (review Ugly 11); extended by T3.1 (2026-06-14),
which made the operands genuinely MULTI-PART Words carrying per-part quote
context and deleted the ``right_quote_type`` sentinel. The evaluator now
decides pattern-vs-literal per part, so mixed-quote operands (``a"b"*``,
``ab"?"``) are bash-correct rather than collapsed-to-unquoted. These tests
freeze:

1. EVALUATION RESULTS (true/false + BASH_REMATCH) for a corpus exercising
   every operator and quoting shape, including per-part mixed quoting.
2. The whole-operand ``is_quoted`` flag: True only when every part is
   quoted with the same char; a mixed-quote operand is NOT wholly quoted
   (its per-part quoting is what drives matching, not this flag).
"""

import pytest

from psh.ast_nodes import (
    BinaryTestExpression,
    EnhancedTestStatement,
    TestExpression,
)
from psh.lexer import tokenize
from psh.parser import parse


def _find_test_expr(node) -> TestExpression:
    """Walk the parsed AST to the EnhancedTestStatement's expression."""
    cur = node
    # Descend through TopLevel/StatementList/AndOrList/Pipeline wrappers.
    seen = 0
    while cur is not None and not isinstance(cur, EnhancedTestStatement):
        seen += 1
        if seen > 50:
            break
        nxt = None
        for f in getattr(cur, '__dataclass_fields__', {}):
            v = getattr(cur, f)
            if isinstance(v, list) and v and hasattr(v[0], '__dataclass_fields__'):
                nxt = v[0]
                break
            if hasattr(v, '__dataclass_fields__'):
                nxt = v
                break
        cur = nxt
    assert isinstance(cur, EnhancedTestStatement), f"no test statement in {node}"
    return cur.expression


def parse_test_expr(src: str) -> TestExpression:
    return _find_test_expr(parse(tokenize(src)))


# ---------------------------------------------------------------------------
# Evaluation-result corpus
# ---------------------------------------------------------------------------
# (setup_commands, test_command, expected_exit_code)  exit 0 == true
EVAL_CASES = [
    # glob pattern (unquoted RHS)
    ("x=abc", "[[ $x == a* ]]", 0),
    ("x=xyz", "[[ $x == a* ]]", 1),
    # literal RHS (double-quoted) — '*' is literal
    ("x=abc", '[[ $x == "a*" ]]', 1),
    ("x='a*'", '[[ $x == "a*" ]]', 0),
    # literal RHS (single-quoted)
    ("x=abc", "[[ $x == 'a*' ]]", 1),
    ("x='a*'", "[[ $x == 'a*' ]]", 0),
    # != glob
    ("x=abc", "[[ $x != b* ]]", 0),
    ("x=bcd", "[[ $x != b* ]]", 1),
    # regex (unquoted)
    ("x=aXYZ", "[[ $x =~ ^a.*$ ]]", 0),
    ("x=zzz", "[[ $x =~ ^a.*$ ]]", 1),
    # literal regex (double-quoted RHS matched literally; '.' is literal dot)
    ("x=aXb", '[[ $x =~ "a.b" ]]', 1),
    ("x=a.b", '[[ $x =~ "a.b" ]]', 0),
    # mixed-quote RHS pattern: a"b"* -> a (glob) + b (literal) + * (glob)
    ("", '[[ abc == a"b"* ]]', 0),
    ("", '[[ axc == a"b"* ]]', 1),
    # per-part quoting: the QUOTED '?' is a literal '?', not a glob (bash)
    ("", '[[ abc == ab"?" ]]', 1),     # ab? literal, abc != ab? -> false
    ("", '[[ "ab?" == ab"?" ]]', 0),   # ab? literal matches ab? -> true
    ("", '[[ abc == ab? ]]', 0),       # unquoted ? is a glob -> true
    # per-part quoting in =~: the quoted '.' is a literal dot
    ("", '[[ "a.c" =~ a"."c ]]', 0),
    ("", '[[ "axc" =~ a"."c ]]', 1),
    ("", '[[ "axc" =~ a.c ]]', 0),     # unquoted . is regex-any -> true
    # double-quoted backslash stays literal (\. is two chars in dquotes)
    ("", r'[[ "a\.c" == "a\.c" ]]', 0),
    ("", r'[[ "a.c" =~ a\.c ]]', 0),   # \. = literal dot in regex
    ("", r'[[ "axc" =~ a\.c ]]', 1),
    # quoted variable RHS is literal; unquoted is live pattern
    ("p='a*'", '[[ aXX == "$p" ]]', 1),
    ("p='a*'", "[[ aXX == $p ]]", 0),
    # unary file test
    ("f=/", "[[ -f $f ]]", 1),
    # unary string test (quoted operand)
    ("x=hello", '[[ -z "$x" ]]', 1),
    ("x=", '[[ -z "$x" ]]', 0),
    # numeric comparison
    ("a=5", "[[ $a -eq 5 ]]", 0),
    ("a=6", "[[ $a -eq 5 ]]", 1),
    # lexicographic comparison
    ("x=abc; y=abd", "[[ $x < $y ]]", 0),
    ("x=abd; y=abc", "[[ $x < $y ]]", 1),
    # tilde operands
    ("", "[[ ~ == ~ ]]", 0),
    # empty operands
    ("", '[[ "" == "" ]]', 0),
    ("", '[[ "" != "" ]]', 1),
]


@pytest.mark.parametrize("setup,cmd,expected", EVAL_CASES)
def test_eval_results(isolated_shell_with_temp_dir, setup, cmd, expected):
    shell = isolated_shell_with_temp_dir
    if setup:
        assert shell.run_command(setup) == 0
    assert shell.run_command(cmd) == expected


def test_bash_rematch_capture(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    assert shell.run_command("x=2024-06-13") == 0
    assert shell.run_command(r'[[ $x =~ ^([0-9]+)-([0-9]+)-([0-9]+)$ ]]') == 0
    assert shell.run_command('echo "${BASH_REMATCH[0]}|${BASH_REMATCH[1]}|'
                             '${BASH_REMATCH[2]}|${BASH_REMATCH[3]}"') == 0


def test_bash_rematch_no_match_clears(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    shell.run_command("x=nope")
    assert shell.run_command(r'[[ $x =~ ^([0-9]+)$ ]]') == 1


# ---------------------------------------------------------------------------
# whole-operand is_quoted corpus
# ---------------------------------------------------------------------------
# (test_src, expected_is_quoted_for_right_operand)
# is_quoted is True only for a WHOLLY (uniformly) quoted operand; a
# mixed-quote operand is False (its per-part quoting drives matching).
IS_QUOTED_CASES = [
    ("[[ $x == a* ]]", False),       # unquoted glob
    ('[[ $x == "a*" ]]', True),      # wholly double-quoted
    ("[[ $x == 'a*' ]]", True),      # wholly single-quoted
    ("[[ $x != b* ]]", False),       # unquoted
    ("[[ $x =~ ^a.*$ ]]", False),    # unquoted regex
    ('[[ $x =~ "a.b" ]]', True),     # wholly-quoted regex
    ('[[ x == a"b"* ]]', False),     # MIXED-quote RHS -> not wholly quoted
    ('[[ "" == "" ]]', True),        # empty quoted
    ("[[ $a -eq 5 ]]", False),       # numeric unquoted
    ("[[ $x < $y ]]", False),        # unquoted var
]


@pytest.mark.parametrize("src,expected_quoted", IS_QUOTED_CASES)
def test_right_operand_is_quoted(src, expected_quoted):
    expr = parse_test_expr(src)
    assert isinstance(expr, BinaryTestExpression)
    assert expr.right_word.is_quoted == expected_quoted


def test_mixed_quote_operand_is_multipart():
    """A mixed-quote operand is now a genuine multi-part Word: ``a"b"*`` is
    three parts (unquoted ``a``, double-quoted ``b``, unquoted ``*``).

    ``display_text()`` still flattens to ``ab*`` (the pre-expansion text),
    but the per-part quote context is preserved — which is what lets the
    evaluator treat the ``b`` as a literal and ``a``/``*`` as glob-active
    (T3.1; replaces the former lossy collapse-to-unquoted)."""
    expr = parse_test_expr('[[ a"b"* == c ]]')
    assert isinstance(expr, BinaryTestExpression)
    assert expr.left_word.display_text() == "ab*"
    assert expr.left_word.is_quoted is False
    quoted_flags = [getattr(p, 'quoted', False) for p in expr.left_word.parts]
    assert quoted_flags == [False, True, False]
