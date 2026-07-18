"""
Parser utilities for PSH shell.

This module exposes :func:`parse_with_heredocs`, the recursive-descent entry
point for token streams whose here-document bodies were collected separately
by the lexer.
"""

from typing import Mapping, Optional, Sequence

from ....ast_nodes import Program
from ....lexer.token_types import Token


def parse_with_heredocs(tokens: Sequence[Token],
                        heredocs: Mapping[int, object],
                        lexer_options: Optional[Mapping[str, object]] = None) -> Program:
    """Parse *tokens* into an AST with pre-collected here-documents.

    ``heredocs`` is the LexedUnit's id-keyed map (spec + collected body); it is
    threaded into the parser so each ``<<``/``<<-`` ``Redirect`` gets its
    delimiter truth and body AS IT IS CONSTRUCTED
    (RedirectionParser._parse_heredoc) — there is no second AST traversal.
    ``lexer_options`` carries the shell option dict so a nested substitution
    body is re-lexed with the same option-sensitive lexing as the outer command.
    """
    from ..parser import Parser
    return Parser(list(tokens), heredocs=heredocs,
                  lexer_options=lexer_options).parse()
