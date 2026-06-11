"""Enhanced token stream with utility methods for parser."""

from typing import List, Optional, Set, Tuple

from .token_types import Token, TokenType


class TokenStream:
    """Enhanced token stream with utility methods.

    This class provides utilities for collecting balanced token sequences,
    handling quotes and nesting, and looking ahead for composite tokens.
    """

    def __init__(self, tokens: List[Token], pos: int = 0):
        """Initialize token stream.

        Args:
            tokens: List of tokens to process
            pos: Starting position in token stream
        """
        self.tokens = tokens
        self.pos = pos

    def peek(self, offset: int = 0) -> Optional[Token]:
        """Look at token at current position + offset without consuming.

        Args:
            offset: Number of tokens to look ahead (0 for current)

        Returns:
            Token at position or None if out of bounds
        """
        idx = self.pos + offset
        if 0 <= idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def advance(self, count: int = 1) -> Optional[Token]:
        """Consume and return token(s).

        Args:
            count: Number of tokens to consume

        Returns:
            Last consumed token or None if at end
        """
        result = None
        for _ in range(count):
            if self.pos < len(self.tokens):
                result = self.tokens[self.pos]
                self.pos += 1
        return result

    def at_end(self) -> bool:
        """Check if at end of token stream."""
        return self.pos >= len(self.tokens) or (
            self.pos < len(self.tokens) and
            self.tokens[self.pos].type == TokenType.EOF
        )

    def collect_until_balanced(self,
                               open_type: TokenType,
                               close_type: TokenType,
                               respect_quotes: bool = True,
                               include_delimiters: bool = False) -> List[Token]:
        """Collect tokens until balanced close token found.

        This method handles nested delimiters and optionally respects quotes.
        For example, collecting until balanced RPAREN will handle nested
        parentheses correctly.

        Args:
            open_type: Token type that opens a nested context
            close_type: Token type that closes the context
            respect_quotes: If True, ignore delimiters inside quotes
            include_delimiters: If True, include the closing delimiter

        Returns:
            List of collected tokens (not including the closing delimiter
            unless include_delimiters is True)
        """
        tokens = []
        depth = 1  # Assume we've already seen one open delimiter
        in_quotes = False

        while not self.at_end() and depth > 0:
            token = self.peek()
            if not token:
                break

            # Handle quote tracking if requested
            # In shell, STRING tokens are already the content inside quotes,
            # so if we see a STRING token, its content should be treated as quoted
            if respect_quotes and token.type == TokenType.STRING:
                in_quotes = True
            else:
                in_quotes = False

            # Track depth only if not in quotes
            if not (respect_quotes and in_quotes):
                if token.type == open_type:
                    depth += 1
                elif token.type == close_type:
                    depth -= 1
                    if depth == 0:
                        if include_delimiters:
                            tokens.append(self.advance())
                        else:
                            self.advance()  # consume but don't include
                        break

            tokens.append(self.advance())

        return tokens

    def collect_until(self,
                      stop_types: Set[TokenType],
                      respect_quotes: bool = True,
                      include_stop: bool = False) -> List[Token]:
        """Collect tokens until one of stop types is encountered.

        Args:
            stop_types: Set of token types to stop at
            respect_quotes: If True, ignore stop tokens inside quotes
            include_stop: If True, include the stop token

        Returns:
            List of collected tokens
        """
        tokens = []

        while not self.at_end():
            token = self.peek()
            if not token:
                break

            # Check if current token is quoted content
            in_quotes = respect_quotes and token.type == TokenType.STRING

            # Check for stop token only if not in quotes
            if not in_quotes and token.type in stop_types:
                if include_stop:
                    tokens.append(self.advance())
                break

            tokens.append(self.advance())

        return tokens

    def peek_composite_sequence(self) -> Optional[List[Token]]:
        """Look ahead for adjacent tokens forming a composite argument.

        Returns:
            List of adjacent tokens that form a composite, or None if
            current token is not part of a composite
        """
        if self.at_end():
            return None

        # Word-like tokens that can form composites
        WORD_LIKE = {
            TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
            TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
            TokenType.ARITH_EXPANSION, TokenType.PARAM_EXPANSION,
            TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
            TokenType.LBRACKET, TokenType.RBRACKET
        }

        first_token = self.peek()
        if not first_token or first_token.type not in WORD_LIKE:
            return None

        composite = [first_token]

        # Look ahead for adjacent tokens
        offset = 1
        while True:
            next_token = self.peek(offset)
            if not next_token:
                break

            # Check if adjacent (using first-class field set by lexer)
            if not next_token.adjacent_to_previous:
                break

            # Check if word-like
            if next_token.type not in WORD_LIKE:
                break

            composite.append(next_token)
            offset += 1

        # Only return if we found a composite (more than one token)
        return composite if len(composite) > 1 else None

    def save_position(self) -> int:
        """Save current position for later restoration."""
        return self.pos

    def restore_position(self, pos: int) -> None:
        """Restore to a previously saved position."""
        self.pos = pos

    def remaining_tokens(self) -> List[Token]:
        """Get all remaining tokens from current position."""
        return self.tokens[self.pos:] if self.pos < len(self.tokens) else []

    def collect_arithmetic_expression(self,
                                    stop_condition=None,
                                    transform_redirects: bool = True) -> Tuple[List[Token], str]:
        """Collect tokens for arithmetic expression with special handling.

        This method is specialized for collecting arithmetic expressions which need:
        - Balanced parenthesis tracking
        - Redirect token transformation (< and > operators)
        - Optional stop conditions (e.g., semicolon at depth 0)

        Args:
            stop_condition: Optional callable(token, paren_depth) -> bool
            transform_redirects: If True, transform REDIRECT_IN/OUT to < and >

        Returns:
            Tuple of (collected tokens, formatted expression string)
        """
        tokens = []
        expr_parts = []
        paren_depth = 0

        while not self.at_end():
            token = self.peek()
            if not token:
                break

            # Check stop condition if provided
            if stop_condition and stop_condition(token, paren_depth):
                break

            # Track parentheses depth
            if token.type == TokenType.LPAREN:
                paren_depth += 1
            elif token.type == TokenType.RPAREN:
                paren_depth -= 1
                # Some stop conditions check for RPAREN at depth 0
                if stop_condition and stop_condition(token, paren_depth):
                    break

            # Collect token
            tokens.append(token)
            self.advance()

            # Build expression string with transformations
            if transform_redirects:
                if token.type == TokenType.REDIRECT_IN:
                    expr_parts.append('<')
                elif token.type == TokenType.REDIRECT_OUT:
                    expr_parts.append('>')
                else:
                    expr_parts.append(token.value)
            else:
                expr_parts.append(token.value)

            # Add space between tokens if needed
            # Always add space after operators for readability
            if not self.at_end():
                next_token = self.peek()
                if next_token:
                    # Add space between word tokens
                    if token.type == TokenType.WORD and next_token.type == TokenType.WORD:
                        expr_parts.append(' ')
                    # Add space after redirect operators, unless next token starts with =
                    elif (transform_redirects and
                          token.type in (TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT) and
                          not (next_token.value and next_token.value.startswith('='))):
                        expr_parts.append(' ')

        expr_string = ''.join(expr_parts).strip()
        return tokens, expr_string
