"""
Array parsing for PSH shell.

This module handles parsing of array assignments and initializations.
"""

from typing import List

from ....ast_nodes import ArrayAssignment, ArrayElementAssignment, ArrayInitialization, Word
from ....lexer.token_types import Token, TokenType
from ..helpers import TokenGroups


class ArrayParser:
    """Parser for array constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    @staticmethod
    def _word_to_element_type(word: Word) -> str:
        """Derive a legacy element-type string from a Word AST node.

        element_types is display/tooling metadata only (validator and
        formatter visitors); the executor expands the parallel `words`
        list exclusively (fallback audit 2026-06-12).
        """
        if word.is_quoted:
            return 'STRING'
        if any(getattr(p, 'quoted', False) for p in word.parts):
            return 'COMPOSITE_QUOTED'
        if len(word.parts) > 1:
            return 'COMPOSITE'
        return 'WORD'

    def _parse_element_value(self, tail: str) -> tuple:
        """Parse an element-assignment value into (value, word, type, quote_char).

        ``tail`` is literal value text that followed ``=``/``+=`` inside the
        same token as the array name. The lexer splits expansions and quoted
        segments into *adjacent* tokens (``a[0]=pre$x"y"`` arrives as
        WORD ``a[0]=pre`` + VARIABLE ``x`` + STRING ``y``), which are merged
        here into a single value Word with per-part quote context.
        """
        from ....ast_nodes import LiteralPart
        has_continuation = (
            self.parser.match_any(TokenGroups.WORD_LIKE)
            and (not tail or self.parser.peek().adjacent_to_previous))
        if tail:
            parts = [LiteralPart(tail)]
            if has_continuation:
                parts.extend(self.parser.commands.parse_argument_as_word().parts)
            word = Word(parts=parts)
        elif has_continuation:
            word = self.parser.commands.parse_argument_as_word()
        else:
            word = Word(parts=[])
        value = ''.join(str(p) for p in word.parts)
        return (value, word, self._word_to_element_type(word),
                word.effective_quote_char)

    def is_array_assignment(self) -> bool:
        """Check if current position starts an array assignment.

        Detects 6 tokenisation patterns for array syntax:
        - Single token: arr[0]=value or arr[0]+=value
        - Two tokens: arr[0] + =value
        - Initialization: arr=( or arr+=(
        - Separate tokens: arr + = + ( or arr + += + (
        - Bracket token: arr + LBRACKET
        - Word bracket: arr + WORD('[') + bracket scan
        """
        if not self.parser.match(TokenType.WORD):
            return False

        token = self.parser.peek()

        # Check for array element assignment: name[index]=value
        if '[' in token.value and ']' in token.value:
            if self._is_element_assignment_single_token(token.value):
                return True
            # Two-token pattern: "arr[0]" + "=value"
            if self._peek_is_assignment_operator(1):
                return True

        # Check for array initialization: name=( or name+=(
        if self._is_initialization_pattern():
            return True

        # Check for array element assignment with separate bracket: name[…]=…
        if self._is_valid_variable_name(token.value):
            return self._is_element_with_bracket_token()

        return False

    def _is_element_assignment_single_token(self, value: str) -> bool:
        """Check if a single WORD token is arr[i]=value or arr[i]+=value.

        Pure string inspection — no parser state changes.
        """
        if '=' not in value:
            return False
        equals_pos = value.index('+=') if '+=' in value else value.index('=')
        return value.index('[') < equals_pos

    def _peek_is_assignment_operator(self, offset: int) -> bool:
        """Check if token at offset is '=…' or '+='."""
        t = self.parser.peek(offset)
        return (t.type == TokenType.WORD and
                (t.value.startswith('=') or t.value == '+='))

    def _is_initialization_pattern(self) -> bool:
        """Check if current position is arr=(…) or arr+=(…) using peek only."""
        token = self.parser.peek()

        # Single token ending with = or +=, followed by LPAREN
        if (token.value.endswith('=') or token.value.endswith('+=')) and '=' in token.value:
            return self.parser.peek(1).type == TokenType.LPAREN

        # Separate tokens: name + = + ( or name + += + (
        next_token = self.parser.peek(1)
        if next_token.type == TokenType.WORD and next_token.value in ('=', '+='):
            return self.parser.peek(2).type == TokenType.LPAREN

        return False

    def _is_element_with_bracket_token(self) -> bool:
        """Check if current position is name[…]=… with separate bracket tokens.

        Uses peek for LBRACKET detection. Falls back to advance-based
        bracket scanning for WORD '[' (unbounded lookahead depth).
        """
        next_token = self.parser.peek(1)

        # LBRACKET token immediately after name
        if next_token.type == TokenType.LBRACKET:
            return True

        # WORD token containing just "[" — need bracket-counting scan
        if next_token.type == TokenType.WORD and next_token.value == '[':
            return self._scan_bracket_assignment()

        return False

    def _scan_bracket_assignment(self) -> bool:
        """Scan ahead through bracket tokens to verify name[…]=… pattern.

        This is the only lookahead path that requires advance+restore,
        because the scan depth inside brackets is unbounded.
        """
        saved_pos = self.parser.current
        self.parser.advance()  # skip name
        self.parser.advance()  # skip [

        bracket_count = 1
        found_assignment = False
        while bracket_count > 0 and not self.parser.at_end():
            token = self.parser.peek()
            if token.type == TokenType.WORD:
                if '[' in token.value:
                    bracket_count += token.value.count('[')
                if ']' in token.value:
                    bracket_count -= token.value.count(']')
                    if bracket_count == 0:
                        # Check if followed by = or +=
                        self.parser.advance()
                        if not self.parser.at_end():
                            next_token = self.parser.peek()
                            if (next_token.type == TokenType.WORD and
                                    (next_token.value.startswith('=') or next_token.value == '+=')):
                                found_assignment = True
                        break
            self.parser.advance()

        self.parser.current = saved_pos
        return found_assignment

    def _is_valid_variable_name(self, name: str) -> bool:
        """Check if a string is a valid shell variable name."""
        if not name:
            return False
        # Must start with letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        # Rest must be alphanumeric or underscore
        return all(c.isalnum() or c == '_' for c in name[1:])

    def parse_array_assignment(self) -> ArrayAssignment:
        """Parse an array assignment (initialization or element)."""
        name_token = self.parser.expect(TokenType.WORD)

        # Check for array element assignment: name[index]=value
        # ModularLexer might tokenize this differently
        if '[' in name_token.value and ']' in name_token.value:
            # Extract name and handle ModularLexer patterns
            if '=' in name_token.value:
                # Pattern: "arr[0]=value" or "arr[0]+=value" all in one token
                is_append = False
                if '+=' in name_token.value:
                    equals_pos = name_token.value.index('+=')
                    is_append = True
                else:
                    equals_pos = name_token.value.index('=')

                bracket_pos = name_token.value.index('[')
                close_bracket_pos = name_token.value.index(']')

                if bracket_pos < equals_pos < close_bracket_pos:
                    raise self.parser.error("Invalid array syntax")

                name = name_token.value[:bracket_pos]
                index_str = name_token.value[bracket_pos+1:close_bracket_pos]
                tail = name_token.value[equals_pos+(2 if is_append else 1):]

                value, value_word, value_type, quote_type = \
                    self._parse_element_value(tail)

                # Create tokens for the index
                index_tokens = [Token(TokenType.WORD, index_str, 0)]

                return ArrayElementAssignment(
                    name=name,
                    index=index_tokens,
                    value=value,
                    value_type=value_type,
                    value_quote_type=quote_type,
                    is_append=is_append,
                    value_word=value_word
                )
            else:
                # Pattern: "arr[0]" "=value" in separate tokens
                bracket_pos = name_token.value.index('[')
                close_bracket_pos = name_token.value.index(']')
                name = name_token.value[:bracket_pos]
                index_str = name_token.value[bracket_pos+1:close_bracket_pos]

                # Next token should be "=value" or "+="
                if not self.parser.match(TokenType.WORD):
                    raise self.parser.error("Expected '=' after array index")

                equals_token = self.parser.advance()
                if not (equals_token.value.startswith('=') or equals_token.value == '+='):
                    raise self.parser.error("Expected '=' or '+=' after array index")

                is_append = equals_token.value == '+=' or equals_token.value.startswith('+=')

                # Extract value: any literal tail in the equals token, plus
                # adjacent continuation tokens (expansions, quoted segments)
                if equals_token.value == '=' or equals_token.value == '+=':
                    if not self.parser.match_any(TokenGroups.WORD_LIKE):
                        raise self.parser.error("Expected value after '='")
                    tail = ''
                else:
                    tail = (equals_token.value[2:] if is_append
                            else equals_token.value[1:])
                value, value_word, value_type, quote_type = \
                    self._parse_element_value(tail)

                # Create tokens for the index
                index_tokens = [Token(TokenType.WORD, index_str, 0)]

                return ArrayElementAssignment(
                    name=name,
                    index=index_tokens,
                    value=value,
                    value_type=value_type,
                    value_quote_type=quote_type,
                    is_append=is_append,
                    value_word=value_word
                )

        # Check for array element assignment with separate bracket: name[index]=value
        if self.parser.match(TokenType.LBRACKET):
            name = name_token.value
            return self._parse_array_element_assignment(name)
        # Also check for WORD token containing just "[" (from ModularLexer)
        elif self.parser.match(TokenType.WORD) and self.parser.peek().value == '[':
            name = name_token.value
            return self._parse_array_element_assignment(name)

        # Otherwise it's array initialization: name=(elements) or name+=(elements)
        # The name token might end with '=' or '+=' (old lexer) or be followed by separate tokens (new lexer)
        name = name_token.value
        is_append = False

        if name_token.value.endswith('+='):
            name = name_token.value[:-2]  # Remove the trailing '+='
            is_append = True
        elif name_token.value.endswith('='):
            name = name_token.value[:-1]  # Remove the trailing '='
            is_append = False
        else:
            # Check for separate = or += token (ModularLexer)
            if self.parser.match(TokenType.WORD):
                eq_token = self.parser.peek()
                if eq_token.value == '+=':
                    self.parser.advance()  # consume +=
                    is_append = True
                elif eq_token.value == '=':
                    self.parser.advance()  # consume =
                    is_append = False
                else:
                    raise self.parser.error("Expected '=' or '+=' in array initialization")
            else:
                raise self.parser.error("Expected '=' or '+=' in array initialization")

        return self._parse_array_initialization(name, is_append)

    def _parse_array_key_tokens(self) -> List[Token]:
        """Parse array key as list of tokens for later evaluation.

        This implements the late binding approach where we collect tokens
        without evaluation, allowing the executor to determine whether to
        evaluate as arithmetic (indexed arrays) or string (associative arrays).
        """
        tokens = []
        bracket_count = 0

        # Collect tokens until we find the closing bracket
        while not self.parser.at_end():
            current_token = self.parser.peek()

            # Handle different token types
            if current_token.type == TokenType.LBRACKET:
                bracket_count += 1
                tokens.append(current_token)
                self.parser.advance()
            elif current_token.type == TokenType.RBRACKET:
                bracket_count -= 1
                if bracket_count < 0:
                    # This is our closing bracket
                    self.parser.advance()
                    break
                else:
                    tokens.append(current_token)
                    self.parser.advance()
            elif current_token.type == TokenType.WORD and ']' in current_token.value:
                # Handle case where ]=value is a single token
                bracket_pos = current_token.value.find(']')
                if bracket_pos == 0:
                    # Token starts with ], this is our closing bracket
                    # DON'T advance here - leave the token for the equals parsing logic
                    break
                else:
                    # ] is in the middle, extract the part before ]
                    index_part = current_token.value[:bracket_pos]
                    if index_part:
                        # Create a token for the index part
                        index_token = Token(TokenType.WORD, index_part, current_token.position)
                        tokens.append(index_token)
                    # DON'T advance here - leave the token for the equals parsing logic
                    break
            else:
                # Regular token, add to index
                valid_key_tokens = {
                    TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
                    TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
                    TokenType.ARITH_EXPANSION, TokenType.LPAREN, TokenType.RPAREN
                }

                if current_token.type not in valid_key_tokens:
                    raise self.parser.error(f"Invalid token in array key: {current_token.type}")

                tokens.append(current_token)
                self.parser.advance()

        return tokens

    def _parse_array_element_assignment(self, name: str) -> ArrayElementAssignment:
        """Parse array element assignment: name[index]=value"""
        # Handle both LBRACKET token and WORD "[" token
        if self.parser.match(TokenType.LBRACKET):
            self.parser.advance()
        elif self.parser.match(TokenType.WORD) and self.parser.peek().value == '[':
            self.parser.advance()
        else:
            raise self.parser.error("Expected '[' after array name")

        # Parse index as list of tokens for late binding (associative vs indexed array evaluation)
        index_tokens = self._parse_array_key_tokens()

        # Note: _parse_array_key_tokens already consumed the RBRACKET

        # Handle different cases for the equals token
        equals_token = None
        if self.parser.match(TokenType.WORD):
            current_token = self.parser.peek()
            if current_token.value.startswith('=') or current_token.value.startswith('+='):
                # Case: separate token starting with = (like "=value")
                equals_token = current_token
            elif current_token.value.startswith(']=') or current_token.value.startswith(']+='):
                # Case: token like "]=value" - extract the part after ]
                bracket_pos = current_token.value.find(']')
                equals_part = current_token.value[bracket_pos + 1:]
                # Create a new token for the equals part
                equals_token = Token(TokenType.WORD, equals_part, current_token.position + bracket_pos + 1)
            else:
                raise self.parser.error("Expected '=' or '+=' after array index")
        else:
            raise self.parser.error("Expected '=' after array index")

        if not (equals_token.value.startswith('=') or equals_token.value.startswith('+=')):
            raise self.parser.error("Expected '=' or '+=' after array index")

        self.parser.advance()  # consume the equals token

        # Check if it's an append operation
        is_append = equals_token.value.startswith('+=')

        # If the equals token has a literal value tail after '=' or '+=',
        # use it; adjacent continuation tokens are merged by the helper.
        if is_append and len(equals_token.value) > 2:
            tail = equals_token.value[2:]
        elif not is_append and len(equals_token.value) > 1:
            tail = equals_token.value[1:]
        else:
            if not self.parser.match_any(TokenGroups.WORD_LIKE):
                raise self.parser.error("Expected value after '=' in array element assignment")
            tail = ''
        value, value_word, value_type, quote_type = \
            self._parse_element_value(tail)

        return ArrayElementAssignment(
            name=name,
            index=index_tokens,
            value=value,
            value_type=value_type,
            value_quote_type=quote_type,
            is_append=is_append,
            value_word=value_word
        )

    def _parse_array_initialization(self, name: str, is_append: bool = False) -> ArrayInitialization:
        """Parse array initialization: name=(elements)"""
        self.parser.expect(TokenType.LPAREN)

        elements = []
        element_types = []
        element_quote_types = []
        words = []

        # Parse array elements (newlines between elements are allowed, as in bash)
        while not self.parser.match(TokenType.RPAREN) and not self.parser.at_end():
            if self.parser.match(TokenType.NEWLINE):
                self.parser.advance()
            elif self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parser.commands.parse_argument_as_word()
                elements.append(''.join(str(p) for p in word.parts))
                element_types.append(self._word_to_element_type(word))
                element_quote_types.append(word.effective_quote_char)
                words.append(word)
            else:
                break

        self.parser.expect(TokenType.RPAREN)

        return ArrayInitialization(
            name=name,
            elements=elements,
            element_types=element_types,
            element_quote_types=element_quote_types,
            is_append=is_append,
            words=words
        )
