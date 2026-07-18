"""Expansion and word-building parsers for the shell parser combinator.

This module provides parsers for shell expansions (variable, command substitution,
arithmetic, process substitution) and Word AST node construction.
"""

from typing import Optional

from ...ast_nodes import (
    ExpansionPart,
    LiteralPart,
    Word,
)
from ...lexer.token_types import Token
from ..config import ParserConfig
from ..recursive_descent.support.word_builder import (
    WordBuilder,
)
from .core import Parser, token


class ExpansionParsers:
    """Parsers for shell expansions and word building.

    The live content of this class is :meth:`build_word_from_token` — the
    shared token→Word AST builder used by the command, loop, conditional, and
    special-command parsers. (The formatting/word/expansion-chain helpers that
    used to live here were dead duplicates of ``utils.format_token_value`` and
    ``TokenParsers``' expansion chain, and were removed.)
    """

    def __init__(self, config: Optional[ParserConfig] = None):
        """Initialize expansion parsers.

        Args:
            config: Parser configuration for controlling features
        """
        self.config = config or ParserConfig()
        # WordBuilder uses static methods, no need to instantiate.
        # Per-call parse budget (campaign S4 handoff 3): a ParseInputs carrying
        # the shell's lexer_options and line_offset, so the combinator builds
        # nested-substitution/syntax templates with the SAME budgets the
        # recursive-descent parser threads through its ParserContext (notably
        # extglob-aware re-lexing of a nested substitution body). Set for the
        # duration of a parse by ParserCombinatorShellParser and cleared in its
        # finally; None (defaults 0/None) outside a parse and for standalone use.
        self.parse_ctx: "Optional[object]" = None

    def build_word_from_token(self, token: Token) -> Word:
        """Build a Word AST node from a token.

        Args:
            token: Token to convert to Word

        Returns:
            Word AST node with appropriate parts
        """
        qt = getattr(token, 'quote_type', None)
        is_quoted = qt is not None and qt != 'mixed'

        # A fused WORD (word_fusion) carries the whole shell word's parts, one
        # per constituent piece — map them straight through. Primary path now
        # that the lexer emits one WORD per multi-piece word. (A plain WORD has
        # no parts and falls through to the literal branch below.)
        if token.type.name == 'WORD' and token.parts:
            return Word(parts=[WordBuilder.token_part_to_word_part(tp, ctx=self.parse_ctx)
                               for tp in token.parts])

        # Check for decomposable parts from the lexer (a token with expansion parts)
        if WordBuilder.has_decomposable_parts(token):
            # Parts carry per-part quote context; Word.quote_type is derived.
            word_parts = [WordBuilder.token_part_to_word_part(tp, ctx=self.parse_ctx)
                          for tp in (token.parts or [])]
            return Word(parts=word_parts)

        # Use TokenType enum values
        if token.type.name == 'STRING':
            # String token - the part carries the quote context.
            return Word(parts=[LiteralPart(token.value, quoted=is_quoted, quote_char=qt)])

        elif token.type.name == 'VARIABLE':
            # Variable expansion — delegate to WordBuilder for brace-stripping
            expansion = WordBuilder.parse_expansion_token(token, self.parse_ctx)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name in ('COMMAND_SUB', 'COMMAND_SUB_BACKTICK'):
            # Command substitution $(...) / `...`. Delegate to WordBuilder so
            # the recursive-descent and combinator parsers build the SAME node:
            # $(...) carries a nested Program (parsed now, rejecting invalid
            # syntax at the outer parse); backticks keep program=None.
            expansion = WordBuilder.parse_expansion_token(token, self.parse_ctx)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name == 'ARITH_EXPANSION':
            # Arithmetic expansion $((...)) — delegate to WordBuilder so both
            # parsers attach the same S3 template (read-time validates nested
            # $(); arithmetic grammar stays lazy).
            expansion = WordBuilder._build_arith_expansion(token.value, self.parse_ctx)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        elif token.type.name in ('PROCESS_SUB_IN', 'PROCESS_SUB_OUT'):
            # Process substitution <(...) / >(...) — same ExpansionPart
            # representation as the recursive descent parser (WordBuilder),
            # so the expansion manager performs the substitution and
            # splices the /dev/fd/N path into the word.
            expansion = WordBuilder.parse_expansion_token(token, self.parse_ctx)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)])

        else:
            # Regular word token
            return Word(parts=[LiteralPart(text=token.value, quoted=is_quoted, quote_char=qt)])


# Convenience functions

def create_expansion_parsers(config: Optional[ParserConfig] = None) -> ExpansionParsers:
    """Create and return an ExpansionParsers instance.

    Args:
        config: Optional parser configuration

    Returns:
        Initialized ExpansionParsers object
    """
    return ExpansionParsers(config)


def parse_variable_expansion() -> Parser[Token]:
    """Create parser for variable expansion tokens.

    Returns:
        Parser that matches $VAR tokens
    """
    return token('VARIABLE')


def parse_command_substitution() -> Parser[Token]:
    """Create parser for command substitution tokens.

    Returns:
        Parser that matches $(cmd) or `cmd` tokens
    """
    return token('COMMAND_SUB').or_else(token('COMMAND_SUB_BACKTICK'))


def parse_arithmetic_expansion() -> Parser[Token]:
    """Create parser for arithmetic expansion tokens.

    Returns:
        Parser that matches $((expr)) tokens
    """
    return token('ARITH_EXPANSION')


def parse_process_substitution() -> Parser[Token]:
    """Create parser for process substitution tokens.

    Returns:
        Parser that matches <(cmd) or >(cmd) tokens
    """
    return token('PROCESS_SUB_IN').or_else(token('PROCESS_SUB_OUT'))
