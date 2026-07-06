"""Conditional-regex `=~` operand policy matches bash (appraisal finding 5d).

The `=~` operand parser used to consume nearly any token until `]]`/`&&`/`||`,
so shell separators and redirection operators (`;`, `&`, `<`, `>`) leaked into
the regex and unbalanced parens surfaced later as a runtime regex warning. It
now enforces an explicit operand policy (verified against bash 5.2):

- reject unquoted shell separators / redirection operators as a conditional
  SYNTAX error (`;`, `&`, `<`, `>`, and those inside a bracket expression like
  `[;]`, `[<>]`);
- require balanced grouping — an unmatched `(` or a stray `)` is a parse error;
- allow the legal ERE alternation `|` and quoted/escaped metacharacters.

These pin the recursive-descent (production) parser. The combinator parser's
`=~` handling is intentionally limited to single-token operands (documented in
docs/guides/combinator_parser_remaining_failures.md) and is not exercised here.
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.recursive_descent.helpers import ParseError


def _parses(src):
    try:
        Parser(tokenize(src)).parse()
        return True
    except ParseError:
        return False


# --- Illegal operand content -> parse error (bash: conditional syntax error) ---
@pytest.mark.parametrize("src", [
    "[[ x =~ ; ]]",
    "[[ x =~ & ]]",
    "[[ x =~ < ]]",
    "[[ x =~ > ]]",
    "[[ x =~ ( ]]",       # unbalanced open
    "[[ x =~ ) ]]",       # stray close
    "[[ a =~ a) ]]",      # trailing stray close
    "[[ x =~ [;] ]]",     # separator inside a bracket expression
    "[[ x =~ [<>] ]]",    # redirection operator inside a bracket expression
    "[[ x =~ ]]",         # empty operand
])
def test_illegal_regex_operand_is_parse_error(src):
    assert _parses(src) is False


# --- Legal regexes -> parse (and don't raise) ---
@pytest.mark.parametrize("src", [
    "[[ ab =~ a|b ]]",            # ERE alternation
    "[[ ab =~ (a|b)+ ]]",         # grouped alternation with quantifier
    "[[ ab =~ (a)(b) ]]",         # multiple groups
    "[[ a =~ ((a)) ]]",           # nested groups
    "[[ a =~ [[:alpha:]] ]]",     # POSIX class
    "[[ abc =~ ([[:alpha:]]+) ]]",
    "[[ aa =~ a{1,2} ]]",         # brace quantifier
    "[[ 'x;y' =~ 'x;y' ]]",       # quoted separator (literal)
    '[[ "a b" =~ "a b" ]]',       # quoted whitespace
    r"[[ 'a;b' =~ a\;b ]]",       # escaped separator
    "[[ aaa =~ ^a+$ ]]",          # anchors
    "[[ abc =~ a.c ]]",           # any-char
])
def test_legal_regex_operand_parses(src):
    assert _parses(src) is True


def test_balanced_group_with_trailing_test_terminator():
    # `(a)` closes cleanly, then `]]` ends the test (group-depth-0 `]]`).
    assert _parses("[[ ab =~ (a)(b) ]]") is True
