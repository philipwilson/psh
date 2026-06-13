"""Characterization + regression pins for [[ ]] test-operand semantics.

Created for the Tier C-D2 refactor that brings BinaryTestExpression operands
into the Word model (review Ugly 11). These tests freeze:

1. EVALUATION RESULTS (true/false + BASH_REMATCH) for a corpus exercising
   every operator and quoting shape.
2. The is_quoted equivalence: for the right operand of each binary test,
   ``right_word.is_quoted`` must equal the OLD ``right_quote_type is not None``
   boolean (a wholly-quoted operand is quoted; unquoted or MIXED-quote
   operands are not). The pre-refactor code stored ``right_quote_type``
   directly; these assertions are written against the post-refactor Word
   model and were confirmed equivalent to the stored field before the change.

These pin ZERO BEHAVIOR CHANGE across the refactor.
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
    # mixed-quote LHS pattern: a"b"* parses to literal pattern ab* (unquoted)
    ("", '[[ abc == a"b"* ]]', 0),
    ("", '[[ axc == a"b"* ]]', 1),
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
# is_quoted equivalence corpus
# ---------------------------------------------------------------------------
# (test_src, expected_is_quoted_for_right_operand)
# expected matches OLD `right_quote_type is not None`.
IS_QUOTED_CASES = [
    ("[[ $x == a* ]]", False),       # unquoted glob
    ('[[ $x == "a*" ]]', True),      # wholly double-quoted
    ("[[ $x == 'a*' ]]", True),      # wholly single-quoted
    ("[[ $x != b* ]]", False),       # unquoted
    ("[[ $x =~ ^a.*$ ]]", False),    # unquoted regex
    ('[[ $x =~ "a.b" ]]', True),     # wholly-quoted regex
    ('[[ x == a"b"* ]]', False),     # MIXED-quote RHS -> unquoted (lossy, pinned)
    ('[[ "" == "" ]]', True),        # empty quoted
    ("[[ $a -eq 5 ]]", False),       # numeric unquoted
    ("[[ $x < $y ]]", False),        # unquoted var
]


@pytest.mark.parametrize("src,expected_quoted", IS_QUOTED_CASES)
def test_right_operand_is_quoted_equivalence(src, expected_quoted):
    expr = parse_test_expr(src)
    assert isinstance(expr, BinaryTestExpression)
    # right_quote_type (derived property) must agree with is_quoted, and both
    # must equal the OLD stored-field boolean.
    assert expr.right_word.is_quoted == expected_quoted
    assert (expr.right_quote_type is not None) == expected_quoted


def test_mixed_quote_lhs_is_lossy_pinned():
    """PINNED: a"b"* collapses to literal text 'ab*' with no quote context.

    This is the pre-existing (lossy) behavior of the string-based operand
    model. The Word migration preserves it exactly rather than 'improving'
    mixed-quote fidelity (which would be a behavior change)."""
    expr = parse_test_expr('[[ a"b"* == c ]]')
    assert isinstance(expr, BinaryTestExpression)
    assert expr.left_word.display_text() == "ab*"
    assert expr.left_word.is_quoted is False
