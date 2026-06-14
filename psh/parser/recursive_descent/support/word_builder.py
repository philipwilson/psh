"""Word builder for creating Word AST nodes from tokens.

This module provides utilities for building Word nodes that properly
represent expansions within command arguments.
"""

import re
from typing import List, Optional

from ....ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    Expansion,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    ProcessSubstitution,
    VariableExpansion,
    Word,
    WordPart,
)
from ....expansion.param_parser import parse_parameter_expansion
from ....lexer.token_types import Token, TokenType

# Token types that represent standalone expansion tokens
# Pre-compiled regex patterns for variable name classification
_SIMPLE_VAR_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\[.+?\])?$')
_SPECIAL_VAR_RE = re.compile(r'^[0-9$?!@*#-]$')

EXPANSION_TYPES = frozenset({
    TokenType.VARIABLE, TokenType.COMMAND_SUB,
    TokenType.COMMAND_SUB_BACKTICK, TokenType.ARITH_EXPANSION,
    TokenType.PARAM_EXPANSION,
    TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
})


def strip_command_sub(value: str) -> str:
    """Strip ``$(``/``)`` from a command substitution's source text.

    Returns the inner command. Falls back to the whole value when the
    delimiters are absent (shouldn't happen with proper lexing).
    """
    if value.startswith('$(') and value.endswith(')'):
        return value[2:-1]
    return value


def strip_backtick(value: str) -> str:
    """Strip the surrounding backticks from `` `...` `` command substitution."""
    if value.startswith('`') and value.endswith('`'):
        return value[1:-1]
    return value


def strip_arithmetic(value: str) -> str:
    """Strip ``$((``/``))`` from an arithmetic expansion's source text."""
    if value.startswith('$((') and value.endswith('))'):
        return value[3:-2]
    return value


def strip_process_sub(value: str) -> str:
    """Strip ``<(``/``>(`` and the trailing ``)`` from a process substitution.

    Leaves the value untouched when it isn't a complete ``<(...)``/``>(...)``.
    """
    if value.startswith(('<(', '>(')) and value.endswith(')'):
        return value[2:-1]
    return value


class WordBuilder:
    """Builds Word AST nodes from tokens."""

    @staticmethod
    def parse_expansion_token(token: Token) -> Expansion:
        """Parse an expansion token into an Expansion AST node."""
        token_type = token.type
        value = token.value

        if token_type == TokenType.VARIABLE:
            # Simple variable like $USER or ${USER}
            # Lexer already stripped the leading $, so value is just the name
            # (e.g. 'USER', '$' for $$, '?' for $?, '{HOME}' for ${HOME})
            name = value
            if name.startswith('{') and name.endswith('}'):
                inner = name[1:-1]
                # Check if this is a simple variable name or a parameter expansion
                # with operators. Simple names: alphanumeric/underscores, or special
                # single-char vars ($, ?, #, !, @, *, 0-9).
                # Array subscripts (arr[@], arr[0]) are also simple.
                if _SIMPLE_VAR_RE.match(inner) or \
                   _SPECIAL_VAR_RE.match(inner):
                    name = inner
                else:
                    # Contains operators — delegate to parameter expansion parser
                    return WordBuilder._parse_parameter_expansion(f"${{{inner}}}")
            return VariableExpansion(name)

        elif token_type == TokenType.COMMAND_SUB:
            # Command substitution $(...)
            return CommandSubstitution(strip_command_sub(value), backtick_style=False)

        elif token_type == TokenType.COMMAND_SUB_BACKTICK:
            # Backtick command substitution `...`
            return CommandSubstitution(strip_backtick(value), backtick_style=True)

        elif token_type == TokenType.ARITH_EXPANSION:
            # Arithmetic expansion $((...))
            return ArithmeticExpansion(strip_arithmetic(value))

        elif token_type == TokenType.PARAM_EXPANSION:
            # Complex parameter expansion ${var:-default} etc.
            return WordBuilder._parse_parameter_expansion(value)

        elif token_type in (TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT):
            # Process substitution <(cmd) or >(cmd) — may stand alone as a
            # word or be embedded in a composite (pre<(cmd)post)
            direction = 'in' if token_type == TokenType.PROCESS_SUB_IN else 'out'
            return ProcessSubstitution(direction=direction,
                                       command=strip_process_sub(value))

        else:
            # Fallback - treat as variable
            return VariableExpansion(value)

    @staticmethod
    def _parse_parameter_expansion(value: str) -> ParameterExpansion:
        """Parse a parameter expansion like ${var:-default}.

        Thin wrapper stripping the ``${``/``}`` delimiters; the grammar
        lives in the single shared parser (expansion/param_parser.py),
        which is also used by the runtime string-expansion entry point.
        Subscripted forms are fully parsed here — ``${arr[@]:1:2}`` is
        ParameterExpansion('arr[@]', ':', '1:2') at parse time, not a
        deferred opaque parameter string.
        """
        if value.startswith('${') and value.endswith('}'):
            value = value[2:-1]
        return parse_parameter_expansion(value)

    @staticmethod
    def token_part_to_word_part(tp) -> WordPart:
        """Convert a lexer TokenPart into a Word AST WordPart node.

        Uses the TokenPart's expansion metadata to create either a
        LiteralPart or ExpansionPart with proper quote context.
        """
        qt = tp.quote_type
        is_quoted = qt is not None

        if tp.is_expansion:
            # A bare $ (empty variable name) is not a real expansion — keep literal
            if getattr(tp, 'expansion_type', None) == 'variable' and tp.value == '':
                return LiteralPart('$', quoted=is_quoted, quote_char=qt)
            expansion = WordBuilder._parse_token_part_expansion(tp)
            return ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)
        else:
            return LiteralPart(tp.value, quoted=is_quoted, quote_char=qt)

    @staticmethod
    def _parse_token_part_expansion(tp) -> Expansion:
        """Convert a TokenPart's expansion metadata into an Expansion AST node.

        The TokenPart has ``expansion_type`` (variable, parameter, command,
        arithmetic, backtick) and ``value`` with varying conventions:
        - variable: value is just the var name (e.g. ``HOME``)
        - parameter: value is the full ``${...}`` syntax
        - command: value is the full ``$(...)`` syntax
        - arithmetic: value is the full ``$((...))`` syntax
        - backtick: value is the full `` `...` `` syntax
        """
        etype = tp.expansion_type

        if etype == 'variable':
            # TokenPart.value is the bare variable name (no $)
            return VariableExpansion(tp.value)

        elif etype == 'parameter':
            # Value is the full ${...} syntax
            return WordBuilder._parse_parameter_expansion(tp.value)

        elif etype == 'command':
            return CommandSubstitution(strip_command_sub(tp.value), backtick_style=False)

        elif etype == 'arithmetic':
            return ArithmeticExpansion(strip_arithmetic(tp.value))

        elif etype == 'backtick':
            return CommandSubstitution(strip_backtick(tp.value), backtick_style=True)

        else:
            # Unknown expansion type — treat as variable
            return VariableExpansion(tp.value)

    @staticmethod
    def has_decomposable_parts(token: Token) -> bool:
        """Check if a token has TokenPart metadata suitable for decomposition.

        Public (with token_part_to_word_part) so the combinator parser can build
        the same Word AST without reaching into private helpers.

        Returns True when the token is a RichToken (or at least has a
        non-empty ``parts`` list) whose parts contain expansion information
        that the WordBuilder should decompose rather than treating the token
        value as a single opaque literal.
        """
        parts = getattr(token, 'parts', None)
        if not parts:
            return False
        # Only decompose if at least one part is an expansion
        return any(getattr(p, 'is_expansion', False) for p in parts)

    @staticmethod
    def build_word_from_token(token: Token, quote_type: Optional[str] = None) -> Word:
        """Build a Word from a single token."""
        is_quoted = quote_type is not None

        # Check if token has decomposable parts from the lexer (RichToken)
        if WordBuilder.has_decomposable_parts(token) and quote_type == '"':
            # Decompose double-quoted string using lexer's TokenPart data.
            # The parts carry the per-part quote context; the whole-word
            # quote_type is DERIVED from them (single quoted part -> its
            # quote char), so no field to set here.
            word_parts = [WordBuilder.token_part_to_word_part(tp)
                          for tp in (token.parts or [])]
            return Word(parts=word_parts)

        if token.type in EXPANSION_TYPES:
            # This is an expansion token. The part carries the quote context;
            # Word.quote_type is derived from it.
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=quote_type)])
        else:
            # This is a literal token. The part carries the quote context.
            return Word(parts=[LiteralPart(token.value, quoted=is_quoted, quote_char=quote_type)])

    @staticmethod
    def build_composite_word(tokens: List[Token], quote_type: Optional[str] = None) -> Word:
        """Build a Word from multiple tokens (for composite words).

        Each part carries its own quote context derived from the token's
        quote_type.  Composites don't have a single quote_type — each
        part carries its own.
        """
        parts: List[WordPart] = []

        for token in tokens:
            qt = getattr(token, 'quote_type', None)

            # Check if this STRING token has decomposable parts
            if WordBuilder.has_decomposable_parts(token) and qt == '"':
                # Flatten decomposed parts into composite
                for tp in (token.parts or []):
                    parts.append(WordBuilder.token_part_to_word_part(tp))
            elif token.type in EXPANSION_TYPES:
                is_quoted = qt is not None
                expansion = WordBuilder.parse_expansion_token(token)
                parts.append(ExpansionPart(expansion, quoted=is_quoted, quote_char=qt))
            else:
                is_quoted = qt is not None
                parts.append(LiteralPart(token.value, quoted=is_quoted, quote_char=qt))

        return Word(parts=parts)

    @staticmethod
    def build_word_from_string(text: str, token_type: str = 'WORD',
                             quote_type: Optional[str] = None) -> Word:
        """Build a Word from a string, parsing any embedded expansions.

        This is used when we have a string that might contain expansions
        that weren't tokenized separately (e.g., in quoted strings).
        """
        # For now, just create a literal word
        # TODO: Parse embedded expansions in quoted strings
        return Word.from_string(text, quote_type)
