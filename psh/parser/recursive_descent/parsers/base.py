"""Shared base for the recursive-descent sub-parsers.

The main `Parser` (`recursive_descent/parser.py`) delegates each construct to a
specialized sub-parser — `StatementParser`, `CommandParser`,
`ControlStructureParser`, `TestParser`, `ArithmeticParser`, `FunctionParser`,
`RedirectionParser`, `ArrayParser`. They share one contract, formalized here as
a base class rather than left as an unwritten convention (review 2026-06-18,
Finding #4 / reassessment 2026-06-20, #4):

  * construct with the main `Parser`, stored as `self.parser`;
  * reach token state through `self.parser` — `peek()` / `advance()` /
    `match()` / `expect()` / `consume_if()` / `current` (the `Parser` inherits
    these from `ContextBaseParser`);
  * raise errors with `self.parser.error(message[, token])`.

Deliberately, this base adds NO token-access delegation (no `self.peek()`
forwarding to `self.parser.peek()`): sub-parsers reference `self.parser`
explicitly so a reader always sees that token state lives on the one shared
`Parser`, not duplicated onto each sub-parser. The base exists to make the
contract discoverable and to remove the eight identical `__init__`s — not to
introduce an abstraction layer over the parser.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..parser import Parser


class ParserSubcomponent:
    """Base for a recursive-descent sub-parser (see the module docstring)."""

    def __init__(self, main_parser: "Parser") -> None:
        self.parser = main_parser
