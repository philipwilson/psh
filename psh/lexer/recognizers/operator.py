"""Operator token recognizer."""

from typing import Optional, Set, Tuple

from ..state_context import LexerContext
from ..token_types import Token, TokenType
from .base import ContextualRecognizer


class OperatorRecognizer(ContextualRecognizer):
    """Recognizes shell operators with context awareness."""

    def __init__(self):
        super().__init__()
        self.config = None  # Will be set by ModularLexer

    # Operators organized by length (longest first for greedy matching)
    OPERATORS = {
        3: {
            '<<<': TokenType.HERE_STRING,
            '<<-': TokenType.HEREDOC_STRIP,
            ';;&': TokenType.AMP_SEMICOLON,
            '&>>': TokenType.REDIRECT_APPEND,  # combined append (stdout+stderr)
        },
        2: {
            '>>': TokenType.REDIRECT_APPEND,
            '<<': TokenType.HEREDOC,
            '<>': TokenType.REDIRECT_READWRITE,
            '>|': TokenType.REDIRECT_CLOBBER,
            '&>': TokenType.REDIRECT_OUT,       # combined redirect (stdout+stderr)
            '|&': TokenType.PIPE_AND,
            '&&': TokenType.AND_AND,
            '||': TokenType.OR_OR,
            '((': TokenType.DOUBLE_LPAREN,
            '))': TokenType.DOUBLE_RPAREN,
            '[[': TokenType.DOUBLE_LBRACKET,
            ']]': TokenType.DOUBLE_RBRACKET,
            '=~': TokenType.REGEX_MATCH,
            '==': TokenType.EQUAL,
            '!=': TokenType.NOT_EQUAL,
            ';;': TokenType.DOUBLE_SEMICOLON,
            ';&': TokenType.SEMICOLON_AMP,
        },
        1: {
            '|': TokenType.PIPE,
            '&': TokenType.AMPERSAND,
            ';': TokenType.SEMICOLON,
            '(': TokenType.LPAREN,
            ')': TokenType.RPAREN,
            '{': TokenType.LBRACE,
            '}': TokenType.RBRACE,
            '[': TokenType.LBRACKET,
            ']': TokenType.RBRACKET,
            '<': TokenType.REDIRECT_IN,
            '>': TokenType.REDIRECT_OUT,
            '!': TokenType.EXCLAMATION,
            '\n': TokenType.NEWLINE,  # Special handling for newlines
        }
    }

    # Characters that can start operators
    OPERATOR_START_CHARS: Set[str] = {
        '<', '>', '&', '|', ';', '(', ')', '{', '}', '[', ']', '!', '=', '2', '\n',
        '0', '1', '3', '4', '5', '6', '7', '8', '9'  # All digits for file descriptor duplication
    }

    @staticmethod
    def _is_shell_token_delimiter(char: str) -> bool:
        """Return True when char can delimit a standalone shell token."""
        return char.isspace() or char in '|&;(){}[]<>'

    def _try_fd_duplication(self, input_text: str, pos: int) -> bool:
        """Check if position starts a file descriptor duplication pattern."""
        # Check for patterns: >&N, <&N, N>&M, N<&M
        remaining = input_text[pos:]

        # Check for >&N or <&N (N a digit, '-', or a dynamic $.../`...` target)
        if len(remaining) >= 3 and remaining[0] in '><' and remaining[1] == '&':
            return remaining[2].isdigit() or remaining[2] == '-' or remaining[2] in '$`'

        # Check for N>&M or N<&M (where we're at the digit)
        if remaining and remaining[0].isdigit():
            # Look ahead to see if this is N>&M pattern
            i = 1
            while i < len(remaining) and remaining[i].isdigit():
                i += 1
            if i < len(remaining) - 1 and remaining[i] in '><' and remaining[i+1] == '&':
                return True

        # Check for N>&M or N<&M (where we're at the > or <)
        if pos > 0 and input_text[pos-1].isdigit():
            if len(remaining) >= 2 and remaining[0] in '><' and remaining[1] == '&':
                return True

        return False

    def _parse_fd_duplication(self, input_text: str, pos: int) -> Optional[Tuple[Token, int]]:
        """Parse file descriptor duplication operators (>&N, N>&M, >&-, ...)."""
        start_pos = pos

        if pos < len(input_text) and input_text[pos].isdigit():
            # N>&M pattern starting at the digit(s)
            while pos < len(input_text) and input_text[pos].isdigit():
                pos += 1
        elif pos > 0 and input_text[pos-1].isdigit():
            # N>&M pattern where we're already at > or < — backtrack so the
            # token value includes the leading digit(s)
            digit_start = pos - 1
            while digit_start > 0 and input_text[digit_start-1].isdigit():
                digit_start -= 1
            start_pos = digit_start

        return self._parse_dup_operator_and_target(input_text, pos, start_pos)

    def _parse_dup_operator_and_target(
        self,
        input_text: str,
        pos: int,
        start_pos: int
    ) -> Optional[Tuple[Token, int]]:
        """Parse the ``>&target``/``<&target`` tail of an fd duplication.

        ``pos`` must point at the ``>`` or ``<``; ``start_pos`` is where the
        token value begins (may precede ``pos`` to include leading digits).
        """
        # Must be > or < followed by &
        if pos >= len(input_text) or input_text[pos] not in '><':
            return None
        pos += 1
        if pos >= len(input_text) or input_text[pos] != '&':
            return None
        pos += 1

        # Get the target: fd digits, '-' (close), or a dynamic expansion
        if pos >= len(input_text):
            return None

        if input_text[pos] == '-':
            pos += 1
        elif input_text[pos].isdigit():
            while pos < len(input_text) and input_text[pos].isdigit():
                pos += 1
        elif input_text[pos] in '$`':
            # Dynamic target (e.g. 2>&$((1+1)), >&$fd): emit only the bare
            # operator (N>& / >&); the following expansion is tokenized
            # separately and consumed by the parser as the dup target.
            pass
        else:
            return None

        op_string = input_text[start_pos:pos]
        return Token(TokenType.REDIRECT_DUP, op_string, start_pos, pos), pos

    def _try_fd_prefixed_redirect(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Try to parse an fd-prefixed redirect like 2>, 3>>, 0<, 5<<<.

        Called when pos is at a digit. Scans forward past digits, then
        checks for a redirect operator (including the heredoc/here-string
        operators <<<, <<-, <<). Returns a single redirect token with the
        fd number stored in token.fd, mirroring how N>&M is emitted as a
        single REDIRECT_DUP token. The heredoc operators must be matched
        BEFORE the shorter '<' so '5<<<' is not split into '5<' + '<<'.
        """
        start = pos
        while pos < len(input_text) and input_text[pos].isdigit():
            pos += 1

        if pos >= len(input_text):
            return None

        # Try longest redirect operators first. Heredoc/here-string
        # operators are included so an explicit fd prefix attaches to them
        # the same way it does to plain redirects (bash: `cat 0<<EOF`).
        for op, tok_type in (
            ('<<<', TokenType.HERE_STRING),
            ('<<-', TokenType.HEREDOC_STRIP),
            ('<<', TokenType.HEREDOC),
            ('>>', TokenType.REDIRECT_APPEND),
            ('>', TokenType.REDIRECT_OUT),
            ('<>', TokenType.REDIRECT_READWRITE),
            ('<', TokenType.REDIRECT_IN),
        ):
            if input_text[pos:pos + len(op)] == op:
                # Make sure the redirect operator is valid in context
                if not self.is_valid_in_context(op, context):
                    return None
                fd = int(input_text[start:pos])
                end = pos + len(op)
                token = Token(tok_type, op, start, end, fd=fd)
                return token, end

        return None

    @property
    def priority(self) -> int:
        """High priority for operators."""
        return 150

    def can_recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> bool:
        """Check if current position might be an operator."""
        if pos >= len(input_text):
            return False

        char = input_text[pos]

        # Quick check for operator start characters
        if char in self.OPERATOR_START_CHARS:
            return True

        # Special handling for newlines
        if char == '\n':
            return True

        return False

    def recognize(
        self,
        input_text: str,
        pos: int,
        context: LexerContext
    ) -> Optional[Tuple[Token, int]]:
        """Recognize operators with context awareness."""
        # Special handling for newlines
        if input_text[pos] == '\n':
            token = Token(
                TokenType.NEWLINE,
                '\n',
                pos,
                pos + 1
            )
            return token, pos + 1

        # Special handling for file descriptor duplication: >&N or N>&M
        # This MUST come before regular operator matching to handle "2>&1" correctly
        if self._try_fd_duplication(input_text, pos):
            result = self._parse_fd_duplication(input_text, pos)
            if result is not None:
                return result

        # Detect fd-prefixed redirects: N>, N>>, N< (digit(s) immediately
        # followed by a redirect operator). Emit a single redirect token with
        # the fd number stored as metadata, consistent with how REDIRECT_DUP
        # already handles N>&M as a single token.
        if input_text[pos].isdigit():
            result = self._try_fd_prefixed_redirect(input_text, pos, context)
            if result is not None:
                return result

        # Try longest operators first for greedy matching
        for length in sorted(self.OPERATORS.keys(), reverse=True):
            if pos + length <= len(input_text):
                candidate = input_text[pos:pos + length]

                if candidate in self.OPERATORS[length]:
                    # Extglob: don't match ! as EXCLAMATION when followed by (
                    if (candidate == '!' and self.config
                            and self.config.enable_extglob
                            and pos + 1 < len(input_text)
                            and input_text[pos + 1] == '('):
                        return None

                    # '!' is a reserved-word operator only when it forms a
                    # standalone token (e.g. "! cmd"). Keep "!!" and "!name"
                    # as regular words for command lookup/history-disabled mode.
                    if candidate == '!' and pos + 1 < len(input_text):
                        if not self._is_shell_token_delimiter(input_text[pos + 1]):
                            continue

                    # { and } are reserved words only when standalone.
                    # Special case: {} is a single word, not LBRACE + RBRACE.
                    if candidate in ('{', '}'):
                        next_pos = pos + 1
                        if candidate == '{' and next_pos < len(input_text) and input_text[next_pos] == '}':
                            continue  # {} is a word, not brace group
                        # } is a reserved word (RBRACE) only at command position
                        if candidate == '}' and not context.command_position:
                            continue
                        # { is a brace-group token only when followed by
                        # whitespace or a command operator. Unlike the general
                        # delimiter check, '[' and ']' do NOT count here, so
                        # {[ab]} stays a single word (e.g. a glob) instead of
                        # being split into LBRACE + '[ab]}'.
                        if candidate == '{':
                            if next_pos < len(input_text):
                                nxt = input_text[next_pos]
                                if not (nxt.isspace() or nxt in '|&;()<>\n'):
                                    continue

                    # Check if operator is valid in current context
                    if self.is_valid_in_context(candidate, context):
                        token_type = self.OPERATORS[length][candidate]
                        token = Token(
                            token_type,
                            candidate,
                            pos,
                            pos + length
                        )
                        # Set combined_redirect flag for &> and &>>
                        if candidate in ('&>', '&>>'):
                            token.combined_redirect = True
                        return token, pos + length

        return None

    def is_valid_in_context(
        self,
        operator: str,
        context: LexerContext
    ) -> bool:
        """Check if operator is valid in current context."""
        # Inside arithmetic context, some operators should not be recognized
        if context.arithmetic_depth > 0:
            # Inside ((...)), don't tokenize these as redirects/operators
            if operator in ['<', '>', '<<', '>>', '<>', '>|', ';&', ';;&']:
                return False

        # [[ and ]] have special context rules
        if operator == '[[':
            # [[ is only valid at command position
            return context.command_position

        elif operator == ']]':
            # ]] is only valid when we're inside [[ ]]
            return context.bracket_depth > 0

        elif operator == '[':
            # [ should be an operator in these contexts:
            # 1. Test command: [ expression ] (at command position with whitespace before)
            # 2. Array assignments: arr[index]=value (at command position after identifier)
            #
            # [ should NOT be an operator (should be part of word) in these contexts:
            # 3. Glob patterns in arguments: echo [abc]* (not at command position)
            # 4. Glob patterns in filenames: echo file[12].txt (not at command position)
            # 5. Inside case patterns: case x in [a-z]*) ... (glob character class)

            # Inside case patterns, [ starts a glob character class, not test command
            if context.in_case_pattern:
                return False

            if not context.command_position:
                # Not at command position - must be argument/glob pattern
                return False

            # At command position - could be test command or array assignment
            # For now, allow both - let the parser determine which one it is
            return True

        elif operator == ']':
            # ] is only an operator in specific contexts:
            # 1. At command position (for test command)
            # 2. Inside [[ ]] (for closing conditional)
            # Otherwise it's part of a word (e.g., glob patterns like [abc]*)
            if context.command_position:
                return True
            if context.bracket_depth > 0:
                return True
            return False

        elif operator in ['=~', '==', '!=']:
            # =~, ==, != are only operators inside [[ ]], otherwise they're words
            return context.bracket_depth > 0

        elif operator == '!':
            # Negation is only valid as a command-position reserved word.
            return context.command_position

        elif operator in ['<', '>']:
            # Inside [[ ]], < and > are comparison operators, not redirections
            if context.bracket_depth > 0:
                return False  # Don't recognize as redirect operators inside [[ ]]
            return True  # Outside [[ ]], they are normal redirections

        elif operator == '))':
            # )) is only valid as DOUBLE_RPAREN when closing an arithmetic
            # context like (( expr )). Outside arithmetic, )) should be
            # tokenized as two separate RPAREN tokens (e.g., nested subshells:
            # (echo "outer"; (echo "inner")) ).
            return context.arithmetic_depth > 0

        # Most operators are valid in any context
        return True
