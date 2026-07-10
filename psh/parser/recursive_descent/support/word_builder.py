"""Word builder for creating Word AST nodes from tokens.

This module provides utilities for building Word nodes that properly
represent expansions within command arguments.
"""

import re
from typing import Optional

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
from ....core.assignment_utils import SHELL_NAME
from ....expansion.param_parser import parse_parameter_expansion
from ....lexer.token_types import Token, TokenType

# Token types that represent standalone expansion tokens
# Pre-compiled regex patterns for variable name classification. A ``${inner}``
# is a simple variable when it is a bare name optionally followed by a
# (non-empty) subscript — the name uses the shared SHELL_NAME fragment.
_SIMPLE_VAR_RE = re.compile(rf'^{SHELL_NAME}(\[.+?\])?$')
_SPECIAL_VAR_RE = re.compile(r'^[0-9$?!@*#-]$')

EXPANSION_TYPES = frozenset({
    TokenType.VARIABLE, TokenType.COMMAND_SUB,
    TokenType.COMMAND_SUB_BACKTICK, TokenType.ARITH_EXPANSION,
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


def _nested_program(source: str, token, ctx):
    """Parse a modern substitution body into a Program at outer-parse time.

    ``token`` is the substitution token (its ``.line`` locates the body in the
    enclosing input); ``ctx`` is the active :class:`ParserContext` or None.
    Errors report the enclosing line and the parent's compound-nesting budget
    is carried in, so a syntax error inside ``$(...)``/``<(...)``/``>(...)``
    rejects the outer parse cleanly. See support/nested_parse.py for why this
    is alias-free (execution re-parses ``source`` with runtime aliases).
    """
    from .nested_parse import parse_nested_command
    if ctx is not None:
        base = getattr(ctx, 'line_offset', 0) or 0
        depth = getattr(ctx, 'nesting_depth', 0) or 0
        sub_depth = getattr(ctx, 'substitution_depth', 0) or 0
        lexer_options = getattr(ctx, 'lexer_options', None)
        tline = getattr(token, 'line', None) or 1
        line_offset = base + max(0, tline - 1)
    else:
        line_offset, depth, sub_depth, lexer_options = 0, 0, 0, None
    return parse_nested_command(source, line_offset=line_offset,
                                initial_depth=depth,
                                substitution_depth=sub_depth + 1,
                                lexer_options=lexer_options)


class WordBuilder:
    """Builds Word AST nodes from tokens."""

    @staticmethod
    def parse_expansion_token(token: Token, ctx=None) -> Expansion:
        """Parse an expansion token into an Expansion AST node.

        ``ctx`` (the active ParserContext, when a parser is driving the build)
        binds nested command/process substitutions to the enclosing parse for
        line-offset and nesting-depth accounting; None yields a standalone
        nested parse (used by tests and the combinator).
        """
        token_type = token.type
        value = token.value

        if token_type == TokenType.VARIABLE:
            # Simple variable like $USER or ${USER}. Lexer already stripped the
            # leading $, so value is just the name (e.g. 'USER', '$' for $$,
            # '?' for $?, '{HOME}' for ${HOME}).
            return WordBuilder._variable_name_to_expansion(value)

        elif token_type == TokenType.COMMAND_SUB:
            # Command substitution $(...): parse the body NOW so invalid nested
            # syntax rejects the outer parse (bash validates at read time).
            src = strip_command_sub(value)
            return CommandSubstitution(program=_nested_program(src, token, ctx),
                                       source=src, backtick_style=False)

        elif token_type == TokenType.COMMAND_SUB_BACKTICK:
            # Legacy backtick `...`: EXCLUDED from eager parsing — bash defers
            # backtick parsing and continues around inner errors, so keep the
            # raw source and leave program=None (execution re-parses it).
            return CommandSubstitution(program=None,
                                       source=strip_backtick(value),
                                       backtick_style=True)

        elif token_type == TokenType.ARITH_EXPANSION:
            # Arithmetic expansion $((...))
            return ArithmeticExpansion(strip_arithmetic(value))

        elif token_type in (TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT):
            # Process substitution <(cmd) or >(cmd) — may stand alone as a
            # word or be embedded in a composite (pre<(cmd)post). Parse the
            # body eagerly (same read-time validation as $(...)).
            direction = 'in' if token_type == TokenType.PROCESS_SUB_IN else 'out'
            src = strip_process_sub(value)
            return ProcessSubstitution(direction=direction,
                                       program=_nested_program(src, token, ctx),
                                       source=src)

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
        parsed = parse_parameter_expansion(value)
        # A ${name} / ${name[idx]} with no operator parses to a plain
        # VariableExpansion; flag it as brace-delimited so WordBraceExpander
        # does NOT fuse a following name-char run into it (${v}{1,2} stays
        # ${v}1/${v}2, unlike bare $v{1,2} -> v1/v2).
        if isinstance(parsed, VariableExpansion):
            parsed.braced = True
        return parsed

    @staticmethod
    def _variable_name_to_expansion(name: str) -> Expansion:
        """Classify a ``VARIABLE``-token name into its Expansion node.

        ``name`` is the lexer's stripped form: a bare name (``USER``, ``?``,
        ``1``) or a brace-delimited body (``{HOME}``, ``{arr[@]}``, ``{x:-d}``).
        A simple brace-delimited name becomes a brace-flagged
        :class:`VariableExpansion`; an operator form delegates to the parameter
        parser. Shared by ``parse_expansion_token`` (standalone/composite
        tokens) and ``_parse_token_part_expansion`` (fused-word ``variable``
        parts) so both build the identical node.
        """
        if name.startswith('{') and name.endswith('}'):
            inner = name[1:-1]
            # Simple names: alphanumeric/underscores, or special single-char
            # vars ($, ?, #, !, @, *, 0-9); array subscripts (arr[@], arr[0])
            # count as simple too.
            if _SIMPLE_VAR_RE.match(inner) or _SPECIAL_VAR_RE.match(inner):
                # Brace-DELIMITED ${name}: does not fuse with a following
                # name-char run under brace expansion (see braced field).
                return VariableExpansion(inner, braced=True)
            # Contains operators — delegate to the parameter expansion parser.
            return WordBuilder._parse_parameter_expansion(f"${{{inner}}}")
        return VariableExpansion(name)

    @staticmethod
    def token_part_to_word_part(tp, containing_token=None, ctx=None) -> WordPart:
        """Convert a lexer TokenPart into a Word AST WordPart node.

        Uses the TokenPart's expansion metadata to create either a
        LiteralPart or ExpansionPart with proper quote context.
        ``containing_token``/``ctx`` bind an embedded command/process
        substitution to the enclosing parse (line offset, nesting depth).
        """
        qt = tp.quote_type
        is_quoted = qt is not None

        if tp.is_expansion:
            # A bare $ (empty variable name) is not a real expansion — keep literal
            if getattr(tp, 'expansion_type', None) == 'variable' and tp.value == '':
                return LiteralPart('$', quoted=is_quoted, quote_char=qt)
            expansion = WordBuilder._parse_token_part_expansion(
                tp, containing_token, ctx)
            return ExpansionPart(expansion, quoted=is_quoted, quote_char=qt)
        else:
            return LiteralPart(tp.value, quoted=is_quoted, quote_char=qt)

    @staticmethod
    def _parse_token_part_expansion(tp, containing_token=None,
                                    ctx=None) -> Expansion:
        """Convert a TokenPart's expansion metadata into an Expansion AST node.

        The TokenPart has ``expansion_type`` (variable, parameter, command,
        arithmetic, backtick, process_in, process_out) and ``value`` with
        varying conventions:
        - variable: value is just the var name (e.g. ``HOME``)
        - parameter: value is the full ``${...}`` syntax
        - command: value is the full ``$(...)`` syntax
        - arithmetic: value is the full ``$((...))`` syntax
        - backtick: value is the full `` `...` `` syntax
        - process_in/process_out: value is the full ``<(...)`` / ``>(...)`` syntax
        """
        etype = tp.expansion_type

        if etype == 'variable':
            # TokenPart.value is the VARIABLE-token name form: a bare name
            # (``x``) from a quote-embedded ``$x``, or a brace body (``{v}``,
            # ``{v:-d}``) from a fused ``${...}``. The shared classifier maps
            # a simple braced name to VariableExpansion(braced=True) — matching
            # the standalone/composite path — and operator forms to the
            # parameter parser.
            return WordBuilder._variable_name_to_expansion(tp.value)

        elif etype == 'parameter':
            # Value is the full ${...} syntax
            return WordBuilder._parse_parameter_expansion(tp.value)

        elif etype == 'command':
            src = strip_command_sub(tp.value)
            return CommandSubstitution(
                program=_nested_program(src, containing_token, ctx),
                source=src, backtick_style=False)

        elif etype == 'arithmetic':
            return ArithmeticExpansion(strip_arithmetic(tp.value))

        elif etype == 'backtick':
            # Legacy backtick: not eagerly parsed (see parse_expansion_token).
            return CommandSubstitution(program=None,
                                       source=strip_backtick(tp.value),
                                       backtick_style=True)

        elif etype in ('process_in', 'process_out'):
            # Process substitution <(...) / >(...) carried as a fused-word
            # part. Same eager nested parse + node representation as
            # parse_expansion_token, so a composite like ``pre<(cmd)`` builds
            # the identical ProcessSubstitution. (No ``"..."`` inline form
            # exists for process substitution; these parts only ever arise
            # from word fusion — see lexer/word_fusion.py.)
            direction = 'in' if etype == 'process_in' else 'out'
            src = strip_process_sub(tp.value)
            return ProcessSubstitution(
                direction=direction,
                program=_nested_program(src, containing_token, ctx),
                source=src)

        else:
            # Unknown expansion type — treat as variable
            return VariableExpansion(tp.value)

    @staticmethod
    def has_decomposable_parts(token: Token) -> bool:
        """Check if a token has TokenPart metadata suitable for decomposition.

        Public (with token_part_to_word_part) so the combinator parser can build
        the same Word AST without reaching into private helpers.

        Returns True when the token has a non-empty ``parts`` list whose parts
        contain expansion information that the WordBuilder should decompose
        rather than treating the token value as a single opaque literal.
        """
        parts = getattr(token, 'parts', None)
        if not parts:
            return False
        # Only decompose if at least one part is an expansion
        return any(getattr(p, 'is_expansion', False) for p in parts)

    @staticmethod
    def build_word_from_token(token: Token, quote_type: Optional[str] = None,
                              ctx=None) -> Word:
        """Build a Word from a single token.

        ``ctx`` (the active ParserContext, when a parser drives the build)
        binds embedded substitutions to the enclosing parse.
        """
        # A fused WORD (word_fusion) carries the whole shell word's parts —
        # one per constituent piece, already in the right per-part quote
        # context. Map them straight through; this is the primary path now that
        # the lexer emits one WORD per multi-piece word. (A plain single-piece
        # WORD has no parts and falls through to the literal branch below.)
        if token.type == TokenType.WORD and token.parts:
            return Word(parts=[WordBuilder.token_part_to_word_part(tp, token, ctx)
                               for tp in token.parts])

        is_quoted = quote_type is not None

        # Check if token has decomposable parts from the lexer
        if WordBuilder.has_decomposable_parts(token) and quote_type == '"':
            # Decompose double-quoted string using lexer's TokenPart data.
            # The parts carry the per-part quote context; the whole-word
            # quote_type is DERIVED from them (single quoted part -> its
            # quote char), so no field to set here.
            word_parts = [WordBuilder.token_part_to_word_part(tp, token, ctx)
                          for tp in (token.parts or [])]
            return Word(parts=word_parts)

        if token.type in EXPANSION_TYPES:
            # This is an expansion token. The part carries the quote context;
            # Word.quote_type is derived from it.
            expansion = WordBuilder.parse_expansion_token(token, ctx)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=quote_type)])
        else:
            # This is a literal token. The part carries the quote context.
            return Word(parts=[LiteralPart(token.value, quoted=is_quoted, quote_char=quote_type)])
