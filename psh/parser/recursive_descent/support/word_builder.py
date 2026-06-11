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
            # Extract command from $(...)
            if value.startswith('$(') and value.endswith(')'):
                command = value[2:-1]
                return CommandSubstitution(command, backtick_style=False)
            else:
                # Shouldn't happen with proper lexing
                return CommandSubstitution(value, backtick_style=False)

        elif token_type == TokenType.COMMAND_SUB_BACKTICK:
            # Backtick command substitution `...`
            # Extract command from `...`
            if value.startswith('`') and value.endswith('`'):
                command = value[1:-1]
                return CommandSubstitution(command, backtick_style=True)
            else:
                return CommandSubstitution(value, backtick_style=True)

        elif token_type == TokenType.ARITH_EXPANSION:
            # Arithmetic expansion $((...)
            # Extract expression from $((...))
            if value.startswith('$((') and value.endswith('))'):
                expression = value[3:-2]
                return ArithmeticExpansion(expression)
            else:
                return ArithmeticExpansion(value)

        elif token_type == TokenType.PARAM_EXPANSION:
            # Complex parameter expansion ${var:-default} etc.
            return WordBuilder._parse_parameter_expansion(value)

        elif token_type in (TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT):
            # Process substitution <(cmd) or >(cmd) — may stand alone as a
            # word or be embedded in a composite (pre<(cmd)post)
            direction = 'in' if token_type == TokenType.PROCESS_SUB_IN else 'out'
            command = value
            if command.startswith(('<(', '>(')) and command.endswith(')'):
                command = command[2:-1]
            return ProcessSubstitution(direction=direction, command=command)

        else:
            # Fallback - treat as variable
            return VariableExpansion(value)

    @staticmethod
    def _parse_parameter_expansion(value: str) -> ParameterExpansion:
        """Parse a parameter expansion like ${var:-default}.

        Operator precedence matters:
        - Longer operators before shorter (## before #, %% before %, // before /)
        - /# and /% (prefix/suffix substitution) before # and %
        - : (substring) after :-, :=, :?, :+ to avoid false matches
        """
        # Remove ${ and }
        if value.startswith('${') and value.endswith('}'):
            inner = value[2:-1]
        else:
            inner = value

        # Transformation operators ${param@OP}: a single '@' followed by one
        # transform letter at the very end (e.g. ${x@Q}, ${arr[@]@Q}, ${@@Q}).
        # The trailing-position check distinguishes the transform '@' from the
        # array-subscript '@' in ${arr[@]} (which is followed by ']').
        if len(inner) >= 2 and inner[-2] == '@' and inner[-1] in 'QEPAUuLakK':
            return ParameterExpansion(inner[:-2], '@' + inner[-1], '')

        # Indirection of a special parameter: ${!#}, ${!?}, ${!$}, ${!-},
        # ${!!} — checked before the operator scan, which would otherwise
        # read '#'/'?'/'-' as an operator with parameter '!'.
        if len(inner) == 2 and inner[0] == '!' and inner[1] in '#?$-!':
            return ParameterExpansion(inner[1], '!', None)

        # Check for operators.
        # We find the operator that matches at the earliest position.
        # When two operators match at the same position, prefer the longer one
        # (e.g. ':-' over ':' at the same index, '//' over '/' at the same index).
        operators = [':-', ':=', ':?', ':+', '##', '%%', '/#', '/%', '//',
                     '#', '%', '/', ':', '-', '=', '+', '?']

        best_idx = len(inner)
        best_op = None
        for op in operators:
            idx = inner.find(op)
            if idx > 0:  # Must have a variable name before operator
                before = inner[:idx]
                # For ':' (substring operator), only match if the parameter
                # part is a clean variable name (no ':' already in it).
                # This prevents re-matching inside operands like '0:-1'.
                if op == ':' and ':' in before:
                    continue
                # A non-colon single-char op preceded by ':' is part of a colon
                # operator (':-', ':=', ':+', ':?'), not a standalone one.
                if op in ('-', '=', '+', '?') and before.endswith(':'):
                    continue
                # Don't match operators inside an unclosed bracket expression
                # — an array subscript ${arr[-1]} / ${arr[i+1]} or a case-mod
                # pattern like ${arr[@]^^[a-m]}.
                if before.count('[') > before.count(']'):
                    continue
                # Don't match operators once a closed array subscript precedes
                # the operator position. ${arr[@]:2:3} (slice), ${arr[0]:-def}
                # (element default), ${arr[@]:1:-1} (negative length) etc. are
                # all routed through the string-path parser (parse_expansion),
                # which resolves the subscript before applying the operator.
                # Checking only ']'-suffix missed operators buried in the
                # operand, e.g. the ':-' inside ${arr[@]:1:-1}.
                if '[' in before and ']' in before and before.index('[') < before.rindex(']'):
                    continue
                if idx < best_idx or (idx == best_idx and best_op and len(op) > len(best_op)):
                    best_idx = idx
                    best_op = op

        if best_op is not None:
            parameter = inner[:best_idx]
            word = inner[best_idx + len(best_op):]
            return ParameterExpansion(parameter, best_op, word)

        # Check for length operator ${#var}
        if inner.startswith('#'):
            return ParameterExpansion(inner[1:], '#', None)

        # Indirect / nameref-name expansion ${!name} for a plain identifier.
        # (The ${!prefix*}, ${!prefix@}, and ${!arr[@]} forms contain *, @, or
        # [ and are handled separately; they are excluded here.)
        if inner.startswith('!') and len(inner) > 1:
            ind = inner[1:]
            if not ind.endswith(('*', '@')) and all(c.isalnum() or c == '_' for c in ind):
                return ParameterExpansion(ind, '!', None)

        # No operator, just a variable
        return ParameterExpansion(inner, None, None)

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
            cmd = tp.value
            if cmd.startswith('$(') and cmd.endswith(')'):
                cmd = cmd[2:-1]
            return CommandSubstitution(cmd, backtick_style=False)

        elif etype == 'arithmetic':
            expr = tp.value
            if expr.startswith('$((') and expr.endswith('))'):
                expr = expr[3:-2]
            return ArithmeticExpansion(expr)

        elif etype == 'backtick':
            cmd = tp.value
            if cmd.startswith('`') and cmd.endswith('`'):
                cmd = cmd[1:-1]
            return CommandSubstitution(cmd, backtick_style=True)

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
            # Decompose double-quoted string using lexer's TokenPart data
            word_parts = [WordBuilder.token_part_to_word_part(tp)
                          for tp in token.parts]
            return Word(parts=word_parts, quote_type='"')

        if token.type in EXPANSION_TYPES:
            # This is an expansion token
            expansion = WordBuilder.parse_expansion_token(token)
            return Word(parts=[ExpansionPart(expansion, quoted=is_quoted, quote_char=quote_type)],
                        quote_type=quote_type)
        else:
            # This is a literal token
            return Word(parts=[LiteralPart(token.value, quoted=is_quoted, quote_char=quote_type)],
                        quote_type=quote_type)

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
                for tp in token.parts:
                    parts.append(WordBuilder.token_part_to_word_part(tp))
            elif token.type in EXPANSION_TYPES:
                is_quoted = qt is not None
                expansion = WordBuilder.parse_expansion_token(token)
                parts.append(ExpansionPart(expansion, quoted=is_quoted, quote_char=qt))
            else:
                is_quoted = qt is not None
                parts.append(LiteralPart(token.value, quoted=is_quoted, quote_char=qt))

        return Word(parts=parts, quote_type=None)

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
