"""The recursive-descent sub-parsers share one formal contract.

The 8 sub-parsers (statements/commands/control_structures/tests/arithmetic/
functions/redirections/arrays) used to follow an unwritten convention: each
defined an identical ``__init__(self, main_parser)`` storing ``self.parser``.
That convention is now a base class, ``ParserSubcomponent`` (review 2026-06-18
Finding #4 / reassessment 2026-06-20 #4). These tests pin it so a new sub-parser
that re-rolls its own ``__init__`` or forgets the base is caught.
"""

from psh.lexer import tokenize
from psh.parser.recursive_descent.parser import Parser
from psh.parser.recursive_descent.parsers.base import ParserSubcomponent

# The sub-parser attributes the main Parser wires up.
SUBPARSER_ATTRS = [
    "statements", "commands", "control_structures", "tests",
    "arithmetic", "functions", "redirections", "arrays",
]


def _parser():
    return Parser(tokenize("echo hi"))


def test_all_subparsers_extend_the_base():
    p = _parser()
    for attr in SUBPARSER_ATTRS:
        sub = getattr(p, attr)
        assert isinstance(sub, ParserSubcomponent), (
            f"{attr} ({type(sub).__name__}) must extend ParserSubcomponent")


def test_subparsers_do_not_reroll_init():
    """Each sub-parser inherits the base __init__; defining its own would
    reintroduce the duplication the base removed."""
    p = _parser()
    for attr in SUBPARSER_ATTRS:
        cls = type(getattr(p, attr))
        assert "__init__" not in cls.__dict__, (
            f"{cls.__name__} defines its own __init__; inherit ParserSubcomponent's")


def test_base_stores_main_parser():
    p = _parser()
    sub = ParserSubcomponent(p)
    assert sub.parser is p
    # And every wired sub-parser points back at the main Parser.
    for attr in SUBPARSER_ATTRS:
        assert getattr(p, attr).parser is p


def test_base_adds_no_token_delegation():
    """The base is intentionally minimal — token access stays on self.parser,
    not forwarded onto the sub-parser (so the shared Parser is always visible)."""
    for name in ("peek", "advance", "match", "expect", "consume_if"):
        assert not hasattr(ParserSubcomponent, name), (
            f"ParserSubcomponent should not delegate {name}() — keep self.parser explicit")
