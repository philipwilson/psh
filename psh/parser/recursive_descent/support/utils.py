"""
Parser utilities for PSH shell.

This module exposes :func:`parse_with_heredocs`, the recursive-descent entry
point for token streams whose here-document bodies were collected separately
by the lexer.
"""

from typing import List, Mapping

from ....ast_nodes import Program
from ....lexer.token_types import Token


def parse_with_heredocs(tokens: List[Token], heredoc_map: Mapping[str, object]) -> Program:
    """Parse *tokens* into an AST with pre-collected here-document bodies.

    The map (lexer-produced) is threaded into the parser so each ``<<``/``<<-``
    ``Redirect`` gets its body attached AS IT IS CONSTRUCTED
    (RedirectionParser._attach_heredoc_body) — there is no second AST traversal.
    """
    from ..parser import Parser
    return Parser(tokens, heredoc_map=heredoc_map).parse()
