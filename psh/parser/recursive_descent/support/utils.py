"""
Parser utilities for PSH shell.

This module exposes :func:`parse_with_heredocs`, the recursive-descent entry
point for token streams whose here-document bodies were collected separately
by the lexer.
"""

from typing import List, Mapping, Optional

from ....ast_nodes import Program
from ....lexer.token_types import Token


def parse_with_heredocs(tokens: List[Token], heredoc_map: Mapping[str, object],
                        lexer_options: Optional[Mapping[str, object]] = None) -> Program:
    """Parse *tokens* into an AST with pre-collected here-document bodies.

    The map (lexer-produced) is threaded into the parser so each ``<<``/``<<-``
    ``Redirect`` gets its body attached AS IT IS CONSTRUCTED
    (RedirectionParser._attach_heredoc_body) — there is no second AST traversal.
    ``lexer_options`` carries the shell option dict so a nested substitution
    body is re-lexed with the same option-sensitive lexing as the outer command.
    """
    from ..parser import Parser
    return Parser(tokens, heredoc_map=heredoc_map,
                  lexer_options=lexer_options).parse()
