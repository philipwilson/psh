"""Expansion parser for variables, command substitution, and arithmetic."""

from typing import TYPE_CHECKING, Optional, Tuple

from . import pure_helpers
from .cmdsub_scanner import find_command_substitution_end
from .constants import SPECIAL_VARIABLES
from .position import Position
from .token_parts import TokenPart

if TYPE_CHECKING:
    from .position import LexerConfig


class ExpansionParser:
    """Handles all forms of shell expansions."""

    def __init__(self, config: Optional['LexerConfig'] = None):
        """
        Initialize the expansion parser.

        Args:
            config: Optional lexer configuration for feature enablement
        """
        self.config = config

    def parse_expansion(
        self,
        input_text: str,
        start_pos: int,  # Points at $
        quote_context: Optional[str] = None
    ) -> Tuple[TokenPart, int]:
        """
        Parse any form of expansion starting with $.

        Args:
            input_text: The input string
            start_pos: Starting position (at $)
            quote_context: Quote context if inside quotes

        Returns:
            Tuple of (token_part, position_after_expansion)
        """
        if start_pos >= len(input_text) or input_text[start_pos] != '$':
            # Not an expansion
            return self._create_literal_part('$', start_pos, start_pos + 1, quote_context), start_pos + 1

        if start_pos + 1 >= len(input_text):
            # Lone $ at end - treat as literal
            return self._create_literal_part('$', start_pos, start_pos + 1, quote_context), start_pos + 1

        next_char = input_text[start_pos + 1]

        # Dispatch to specific parsers based on what follows $
        if next_char == '(':
            return self._parse_command_or_arithmetic(input_text, start_pos, quote_context)
        elif next_char == '{':
            return self._parse_brace_expansion(input_text, start_pos, quote_context)
        elif next_char == '[':
            return self._parse_dollar_bracket_arithmetic(input_text, start_pos, quote_context)
        else:
            return self._parse_simple_variable(input_text, start_pos, quote_context)

    def _parse_dollar_bracket_arithmetic(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse the deprecated ``$[expr]`` arithmetic form.

        ``$[expr]`` is exactly ``$((expr))`` (bash, deprecated). We rewrite it to
        the canonical ``$((...))`` token value so the whole arithmetic pipeline
        downstream is unchanged; the inner ``[``/``]`` are balanced so subscripts
        like ``$[a[0]+1]`` work.
        """
        depth = 0
        i = start_pos + 1  # at '['
        close = None
        while i < len(input_text):
            ch = input_text[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    close = i
                    break
            i += 1

        if close is None:
            # Unclosed $[ ... : take what we have (parser reports the error).
            return TokenPart(
                value=input_text[start_pos:], quote_type=quote_context,
                is_expansion=True, expansion_type='arithmetic_unclosed',
                start_pos=Position(start_pos, 0, 0),
                end_pos=Position(len(input_text), 0, 0)
            ), len(input_text)

        # Rewrite any NESTED `$[...]` in the body too, so `$[2*$[3]]` works.
        inner = self._rewrite_dollar_brackets(input_text[start_pos + 2:close])
        end_pos = close + 1
        return TokenPart(
            value=f'$(({inner}))',           # canonical arithmetic form
            quote_type=quote_context,
            is_expansion=True,
            expansion_type='arithmetic',
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        ), end_pos

    @staticmethod
    def _rewrite_dollar_brackets(text: str) -> str:
        """Rewrite every ``$[expr]`` in *text* to ``$((expr))``, recursively."""
        result: list = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == '$' and i + 1 < n and text[i + 1] == '[':
                depth = 0
                j = i + 1
                close = None
                while j < n:
                    if text[j] == '[':
                        depth += 1
                    elif text[j] == ']':
                        depth -= 1
                        if depth == 0:
                            close = j
                            break
                    j += 1
                if close is not None:
                    inner = ExpansionParser._rewrite_dollar_brackets(text[i + 2:close])
                    result.append(f'$(({inner}))')
                    i = close + 1
                    continue
            result.append(text[i])
            i += 1
        return ''.join(result)

    def _parse_command_or_arithmetic(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse $(...) or $((...))."""
        # Check if it's arithmetic expansion $((...))
        if (start_pos + 2 < len(input_text) and
            input_text[start_pos:start_pos+3] == '$(('):

            return self._parse_arithmetic_expansion(input_text, start_pos, quote_context)
        else:
            return self._parse_command_substitution(input_text, start_pos, quote_context)

    def _parse_arithmetic_expansion(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse $((...)) arithmetic expansion."""
        # Find the closing ))
        end_pos, status = pure_helpers.scan_double_paren_arithmetic(
            input_text, start_pos + 3
        )

        if status is pure_helpers.ArithParenScan.NOT_ARITHMETIC:
            # POSIX disambiguation: a `$((` with no matching `))` is a
            # command substitution whose body starts with a subshell —
            # re-read it as `$(` (bash parse.y does the same).
            return self._parse_command_substitution(
                input_text, start_pos, quote_context)

        if status is pure_helpers.ArithParenScan.CLOSED:
            value = input_text[start_pos:end_pos]
            expansion_type = 'arithmetic'
        else:
            # Unclosed - take what we have
            value = input_text[start_pos:]
            end_pos = len(input_text)
            expansion_type = 'arithmetic_unclosed'

        return TokenPart(
            value=value,
            quote_type=quote_context,
            is_expansion=True,
            expansion_type=expansion_type,
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        ), end_pos

    def _parse_command_substitution(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse $(...) command substitution."""
        # Find the closing ) with the grammar-aware extent scanner rather
        # than by counting parens: shell grammar allows unmatched ')' inside
        # the substitution (case patterns: `$(case x in x) echo hi;; esac)`),
        # and parens inside quotes, comments, and heredoc bodies are not
        # delimiters at all. See find_command_substitution_end() in
        # cmdsub_scanner.py for the full design (it mirrors what bash does by
        # recursively invoking its parser in xparse_dolparen()). When no
        # closer is found the token is marked 'command_unclosed', which the
        # parser turns into an incomplete-input error so interactive and
        # script line-gathering can read more lines (multi-line $(...),
        # including heredocs inside the substitution).
        end_pos, found = find_command_substitution_end(
            input_text, start_pos + 2
        )

        if found:
            value = input_text[start_pos:end_pos]
            expansion_type = 'command'
        else:
            # Unclosed - take what we have
            value = input_text[start_pos:]
            end_pos = len(input_text)
            expansion_type = 'command_unclosed'

        return TokenPart(
            value=value,
            quote_type=quote_context,
            is_expansion=True,
            expansion_type=expansion_type,
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        ), end_pos

    def _parse_brace_expansion(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse ${...} parameter expansion."""
        # Find the closing }
        content, end_pos, found = pure_helpers.validate_brace_expansion(
            input_text, start_pos + 2
        )

        if found:
            value = '${' + content + '}'
            expansion_type = 'parameter'
        else:
            # Unclosed - take what we have
            value = '${' + content
            end_pos = len(input_text)
            expansion_type = 'parameter_unclosed'

        return TokenPart(
            value=value,
            quote_type=quote_context,
            is_variable=True,
            is_expansion=True,
            expansion_type=expansion_type,
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        ), end_pos

    def _parse_simple_variable(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str]
    ) -> Tuple[TokenPart, int]:
        """Parse simple variable $VAR."""
        # Extract variable name
        var_name, end_pos = pure_helpers.extract_variable_name(
            input_text, start_pos + 1, SPECIAL_VARIABLES,
            posix_mode=self.config.posix_mode if self.config else False
        )

        if not var_name:
            # No valid variable name follows $ — treat as literal '$'
            return self._create_literal_part(
                '$', start_pos, start_pos + 1, quote_context
            ), start_pos + 1

        # Normalize variable name if configured
        if self.config and var_name and len(var_name) > 1:  # Don't normalize special vars
            from .unicode_support import normalize_identifier
            var_name = normalize_identifier(
                var_name,
                posix_mode=self.config.posix_mode,
            )

        return TokenPart(
            value=var_name,
            quote_type=quote_context,
            is_variable=True,
            is_expansion=True,
            expansion_type='variable',
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        ), end_pos

    def parse_backtick_substitution(
        self,
        input_text: str,
        start_pos: int,
        quote_context: Optional[str] = None
    ) -> Tuple[TokenPart, int]:
        r"""Parse `...` backtick command substitution.

        Inside backticks a backslash quotes backslash, backtick, and
        dollar. When the backtick itself sits inside double quotes
        (*quote_context* is ``"``) bash ALSO strips a backslash before
        ``"`` — probed: ``echo "`echo \"q\"`"`` prints ``q`` while the
        bare ``echo `echo \"q\"``` keeps the quotes (and ``$(...)``
        inside double quotes keeps ``\"`` too — the rule is
        backtick-specific).
        """
        # Find closing backtick
        pos = start_pos + 1
        content = ""
        unescape = '`$\\' + ('"' if quote_context == '"' else '')

        while pos < len(input_text) and input_text[pos] != '`':
            if input_text[pos] == '\\' and pos + 1 < len(input_text):
                # Handle escape sequences in backticks
                next_char = input_text[pos + 1]
                if next_char in unescape:
                    pos += 1  # Skip backslash
                    content += input_text[pos] if pos < len(input_text) else ''
                else:
                    content += input_text[pos]
            else:
                content += input_text[pos]
            pos += 1

        # Check for closing backtick
        if pos < len(input_text) and input_text[pos] == '`':
            pos += 1  # Skip closing backtick
            value = '`' + content + '`'
            expansion_type = 'backtick'
        else:
            # Unclosed backtick
            value = '`' + content
            expansion_type = 'backtick_unclosed'

        return TokenPart(
            value=value,
            quote_type=quote_context,
            is_expansion=True,
            expansion_type=expansion_type,
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(pos, 0, 0)
        ), pos

    def is_expansion_sigil(self, input_text: str, pos: int) -> bool:
        """Whether the char at *pos* is an expansion sigil (``$`` or backtick).

        This is only the cheap "does an expansion sigil start here" test — NOT
        the precise "is this a VALID expansion" check (a lone ``$`` passes here
        and the expansion parser later renders it literal). The stricter
        validation lives in ``recognizers/word_scanners.can_start_expansion``,
        which the literal recognizer uses for word-boundary decisions; the two
        are deliberately different and now have distinct names.
        """
        if pos >= len(input_text):
            return False

        return input_text[pos] in ('$', '`')

    def _create_literal_part(
        self,
        value: str,
        start_pos: int,
        end_pos: int,
        quote_context: Optional[str]
    ) -> TokenPart:
        """Create a literal token part."""
        return TokenPart(
            value=value,
            quote_type=quote_context,
            is_variable=False,
            is_expansion=False,
            start_pos=Position(start_pos, 0, 0),
            end_pos=Position(end_pos, 0, 0)
        )


class ExpansionContext:
    """Context for expansion parsing operations."""

    def __init__(
        self,
        input_text: str,
        config: Optional['LexerConfig'] = None,
    ):
        """
        Initialize expansion context.

        Args:
            input_text: The input string being parsed
            config: Optional lexer configuration
        """
        self.input_text = input_text
        self.config = config
        self.parser = ExpansionParser(config)

    def parse_expansion_at_position(
        self,
        pos: int,
        quote_context: Optional[str] = None
    ) -> Tuple[TokenPart, int]:
        """
        Parse an expansion starting at the given position.

        Args:
            pos: Position to start parsing
            quote_context: Quote context if inside quotes

        Returns:
            Tuple of (token_part, position_after_expansion)
        """
        return self.parser.parse_expansion(self.input_text, pos, quote_context)

    def is_expansion_start(self, pos: int) -> bool:
        """Check if position starts an expansion."""
        return self.parser.is_expansion_sigil(self.input_text, pos)

