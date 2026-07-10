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
        tokens: List[Token] = []
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
                            tokens.append(token)
                        self.advance()  # consume (token already captured above)
                        break

            tokens.append(token)
            self.advance()

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
        tokens: List[Token] = []

        while not self.at_end():
            token = self.peek()
            if not token:
                break

            # Check if current token is quoted content
            in_quotes = respect_quotes and token.type == TokenType.STRING

            # Check for stop token only if not in quotes
            if not in_quotes and token.type in stop_types:
                if include_stop:
                    tokens.append(token)
                    self.advance()
                break

            tokens.append(token)
            self.advance()

        return tokens

    def save_position(self) -> int:
        """Save current position for later restoration."""
        return self.pos

    def restore_position(self, pos: int) -> None:
        """Restore to a previously saved position."""
        self.pos = pos

    def remaining_tokens(self) -> List[Token]:
        """Get all remaining tokens from current position."""
        return self.tokens[self.pos:] if self.pos < len(self.tokens) else []

    def _split_double_rparen(self) -> None:
        """Split the ``DOUBLE_RPAREN`` at the current position into two ``RPAREN``.

        The lexer greedily fuses adjacent ``)`` into a single ``))`` token.  When
        only the first ``)`` belongs to an arithmetic expression (it closes an
        inner group) and the second begins the enclosing ``))`` terminator, we
        split the fused token so each ``)`` can be handled on its own.
        """
        fused = self.tokens[self.pos]
        first = Token(
            type=TokenType.RPAREN, value=')',
            position=fused.position, end_position=fused.position + 1,
            line=fused.line, column=fused.column,
            adjacent_to_previous=fused.adjacent_to_previous,
        )
        second = Token(
            type=TokenType.RPAREN, value=')',
            position=fused.position + 1, end_position=fused.end_position,
            line=fused.line,
            column=(fused.column + 1) if fused.column is not None else None,
            adjacent_to_previous=True,
        )
        self.tokens[self.pos:self.pos + 1] = [first, second]

    def collect_arithmetic_expression(self,
                                    stop_at_semicolon: bool = False,
                                    transform_redirects: bool = True) -> Tuple[List[Token], str]:
        """Collect the tokens of one arithmetic (sub)expression inside a ``(( ))``.

        The expression is the interior of a ``(( ))`` construct — an arithmetic
        command/evaluation, or one ``;``-separated section of a C-style ``for``
        header — so it starts at paren-depth 0.  A single depth-tracked discipline
        governs where it ends::

            (   -> +1        )   -> -1
            ((  -> +2        ))  -> -2      (the lexer fuses adjacent parens)

        The expression ends *before* its terminator (the caller consumes it):

        * a top-level ``;`` / ``;;`` — only when ``stop_at_semicolon`` is set
          (the ``for``-header sections); or
        * the enclosing ``))`` — any closing paren met at depth 0, i.e. one that
          would drop below the section's base depth.

        Greedy lexing can fuse an inner group's closing ``)`` with the header's
        first ``)``: ``(i++))`` lexes as ``(`` ``i++`` ``))``.  Such a ``))`` met
        at depth 1 straddles the boundary, so it is split into two ``)`` — the
        first closes the inner group (kept here), the second begins the terminator.

        Args:
            stop_at_semicolon: Stop at a top-level ``;``/``;;`` (for-header sections).
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

            # Terminators live at the section's top level (depth 0).
            if paren_depth == 0:
                if stop_at_semicolon and token.type in (
                        TokenType.SEMICOLON, TokenType.DOUBLE_SEMICOLON):
                    break
                # Any closing paren at depth 0 is the enclosing ``))`` — it would
                # drop below the base depth, so it belongs to the caller.
                if token.type in (TokenType.RPAREN, TokenType.DOUBLE_RPAREN):
                    break

            # A ``))`` met at depth 1 straddles an inner close and the terminator;
            # split it so only the inner ``)`` is collected here.
            if token.type == TokenType.DOUBLE_RPAREN and paren_depth == 1:
                self._split_double_rparen()
                split = self.peek()  # first half: a single RPAREN closing the group
                assert split is not None  # just inserted two tokens at self.pos
                token = split

            # Track parentheses depth (fused ((/)) count as two).
            if token.type == TokenType.LPAREN:
                paren_depth += 1
            elif token.type == TokenType.DOUBLE_LPAREN:
                paren_depth += 2
            elif token.type == TokenType.RPAREN:
                paren_depth -= 1
            elif token.type == TokenType.DOUBLE_RPAREN:
                paren_depth -= 2

            # Collect token
            tokens.append(token)
            self.advance()

            # Build expression string with transformations.
            #
            # The lexer strips the leading '$' from VARIABLE tokens
            # ('$1' -> '1', '$#' -> '#', '${#a[@]}' -> '{#a[@]}'). This string is
            # frozen onto the ArithmeticEvaluation node and re-parsed later by the
            # arithmetic evaluator, so we must re-add the '$' here — otherwise '$1'
            # collapses to the literal integer 1 and '${#a[@]}' fails to parse.
            # (The '$((...))' *expansion* form keeps its own single token and never
            # reaches this path, which is why only the command/loop forms were
            # affected.) Mirrors the subscript reconstruction in
            # psh/parser/combinators/arrays.py.
            if transform_redirects and token.type == TokenType.REDIRECT_IN:
                expr_parts.append('<')
            elif transform_redirects and token.type == TokenType.REDIRECT_OUT:
                expr_parts.append('>')
            elif token.type == TokenType.VARIABLE:
                expr_parts.append(f'${token.value}')
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
