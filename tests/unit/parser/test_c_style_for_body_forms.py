"""C-style for body forms match bash (appraisal finding 5a).

Bash accepts a C-style for body as EITHER `do LIST done` OR a brace group
`{ LIST }` (a documented synonym), and REQUIRES one of them — a bare command
with no `do`/`{` is a syntax error. psh previously made `do` optional, so
`for ((...)) echo x; done` was wrongly accepted and `for ((...)) { ...; }` was
wrongly rejected.

Both the recursive-descent and combinator parsers are checked so they
accept/reject these forms identically (RD == combinator parity).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig
from psh.parser.recursive_descent.helpers import ParseError

# (source, should_parse) — verified against bash 5.2 (rc 0 vs rc 2).
CASES = [
    ("for ((i=0;i<2;i++)); do echo x; done", True),
    ("for ((i=0;i<2;i++))\ndo echo x; done", True),
    ("for ((i=0;i<2;i++)) do echo x; done", True),      # do, no separator
    ("for ((i=0;i<2;i++)) { echo x; }", True),          # brace body, no sep
    ("for ((i=0;i<2;i++)); { echo x; }", True),         # brace body, ; sep
    ("for ((i=0;i<2;i++))\n{ echo x; }", True),         # brace body, newline
    ("for ((i=0;i<1;i++)) { echo a; echo b; }", True),  # multi-command brace
    ("for ((i=0;i<1;i++)) { for ((j=0;j<1;j++)) { echo n; }; }", True),  # nested
    ("for ((i=0;i<2;i++)) echo x; done", False),        # bare command, no do/brace
    ("for ((i=0;i<2;i++)); echo x; done", False),       # ; then bare command
    ("for ((i=0;i<2;i++)) done", False),                # done with no do
    ("for ((i=0;i<1;i++)) { }", False),                 # empty brace body
]


def _rd_parses(src):
    try:
        Parser(tokenize(src)).parse()
        return True
    except ParseError:
        return False


def _comb_parses(src):
    try:
        ParserCombinatorShellParser(ParserConfig()).parse(tokenize(src))
        return True
    except Exception:  # combinator raises ParseError / ParseFailure-derived
        return False


@pytest.mark.parametrize("src,should_parse", CASES)
def test_rd_c_style_for_body(src, should_parse):
    assert _rd_parses(src) is should_parse


@pytest.mark.parametrize("src,should_parse", CASES)
def test_combinator_c_style_for_body(src, should_parse):
    assert _comb_parses(src) is should_parse


@pytest.mark.parametrize("src,_should_parse", CASES)
def test_rd_and_combinator_agree(src, _should_parse):
    assert _rd_parses(src) == _comb_parses(src)
