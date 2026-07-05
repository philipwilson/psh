"""Empty case-pattern alternatives are rejected (appraisal finding 5e).

`_parse_case_pattern` could return an empty pattern (`CasePattern(pattern="",
word=Word(parts=[]))`), so psh accepted malformed forms bash rejects as syntax
errors: `case x in x|) ...`, `(|x)`, `()`, `(x|)`. Each alternative must
contribute at least one word part. A QUOTED-empty pattern (`''`) is legal and
DOES produce a (quoted) part, so it stays accepted — verified against bash 5.2.

Both parsers reject the empty forms identically (the combinator already did).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig
from psh.parser.recursive_descent.helpers import ParseError


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
    except Exception:
        return False


EMPTY_ALTERNATIVES = [
    "case x in x|) echo m ;; esac",     # empty after |
    "case x in (|x) echo m ;; esac",    # empty before |
    "case x in () echo m ;; esac",      # fully empty
    "case x in (x|) echo m ;; esac",    # empty trailing
]

LEGAL = [
    "case y in x|y) echo m ;; esac",     # normal alternation
    "case x in (x|y) echo m ;; esac",    # parenthesised alternation
    "case '' in ''|x) echo m ;; esac",   # quoted-empty alternative (legal!)
    "case '' in '') echo e ;; esac",     # quoted-empty pattern (legal!)
    "case x in esac",                    # empty case body (no patterns)
    "case ab in a*|b*) echo m ;; esac",  # glob alternation
]


@pytest.mark.parametrize("src", EMPTY_ALTERNATIVES)
def test_empty_alternative_rejected_rd(src):
    assert _rd_parses(src) is False


@pytest.mark.parametrize("src", LEGAL)
def test_legal_pattern_parses_rd(src):
    assert _rd_parses(src) is True


@pytest.mark.parametrize("src", EMPTY_ALTERNATIVES + LEGAL)
def test_rd_and_combinator_agree(src):
    assert _rd_parses(src) == _comb_parses(src)
