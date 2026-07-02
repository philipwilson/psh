"""Redirection parsers for the shell parser combinator.

This module provides the mixin parsing I/O redirections, heredocs, here
strings, and fd-duplication words for ``CommandParsers``.
"""

from typing import TYPE_CHECKING, List, Optional

from ....ast_nodes import Redirect
from ....lexer.token_types import Token
from ..core import ParseResult
from ._constants import _FD_DUP_RE, _WORD_LIKE_TYPES

if TYPE_CHECKING:
    from ._protocols import CommandParsersProtocol
    _Base = CommandParsersProtocol
else:
    _Base = object


class RedirectionMixin(_Base):
    """Mixin providing redirection parsers for CommandParsers."""

    def _parse_word_as_word(self, tokens: List[Token], pos: int) -> ParseResult:
        """Parse one word-like shell word, including adjacent composite parts."""
        return self.arrays.parse_word_as_word(tokens, pos)

    def _parse_redirection(self, tokens: List[Token], pos: int) -> ParseResult[Redirect]:
        """Parse I/O redirection.

        Args:
            tokens: List of tokens
            pos: Current position

        Returns:
            ParseResult with Redirect node
        """
        # First try to parse a redirection operator
        op_result = self.tokens.redirect_operator.parse(tokens, pos)
        if not op_result.success:
            return ParseResult(success=False, error=op_result.error, position=pos)

        op_token = op_result.value
        assert op_token is not None  # success implies a token
        pos = op_result.position

        # Propagate fd from token metadata (set by lexer for fd-prefixed
        # redirects like 2>, 3>>)
        fd = op_token.fd

        # Handle redirect duplication (e.g., 2>&1, >&2, etc.)
        if op_token.type.name == 'REDIRECT_DUP':
            # REDIRECT_DUP tokens contain the full operator (e.g., "2>&1")
            # Parse the fd and dup_fd from the token value
            dup_match = _FD_DUP_RE.match(op_token.value)
            if dup_match:
                source_fd_str, direction, target = dup_match.groups()
                default_fd = 1 if direction == '>' else 0
                source_fd = int(source_fd_str) if source_fd_str else default_fd
                if target == '-':
                    redirect = Redirect(type=direction + '&-', target=None, fd=source_fd)
                else:
                    redirect = Redirect(
                        type=direction + '&', target=None,
                        fd=source_fd, dup_fd=int(target),
                    )
            else:
                redirect = Redirect(type=op_token.value, target='', fd=fd)
            return ParseResult(success=True, value=redirect, position=pos)

        # Handle heredoc operators
        if op_token.type.name in ['HEREDOC', 'HEREDOC_STRIP']:
            # Parse delimiter
            if pos >= len(tokens) or tokens[pos].type.name == 'EOF':
                return ParseResult(
                    success=False,
                    error="Expected heredoc delimiter",
                    position=pos
                )

            delimiter_token = tokens[pos]
            delimiter = delimiter_token.value
            pos += 1

            # Quoting anywhere in the delimiter disables body expansion. A
            # composite delimiter spans several ADJACENT word-like tokens
            # (`<<E"O"F`, `<<E$X`); consume them all so the trailing parts
            # are not parsed as command arguments — mirrors the recursive
            # descent parser's _parse_heredoc.
            heredoc_quoted = (delimiter_token.type.name == 'STRING'
                              or '\\' in delimiter_token.value)
            while (pos < len(tokens)
                   and tokens[pos].type.name in _WORD_LIKE_TYPES
                   and getattr(tokens[pos], 'adjacent_to_previous', False)):
                part = tokens[pos]
                delimiter += part.value
                if part.type.name == 'STRING' or '\\' in part.value:
                    heredoc_quoted = True
                pos += 1

            redirect = Redirect(type=op_token.value, target=delimiter,
                                heredoc_quoted=heredoc_quoted, fd=fd)
            # The lexer's collector key links this redirect to its body
            # (populated post-parse by HeredocProcessor).
            if hasattr(op_token, 'heredoc_key'):
                redirect.heredoc_key = op_token.heredoc_key
            return ParseResult(success=True, value=redirect, position=pos)

        # Handle here string (<<<)
        if op_token.type.name == 'HERE_STRING':
            # Parse the content
            content_result = self._parse_word_as_word(tokens, pos)
            if not content_result.success:
                return ParseResult(
                    success=False,
                    error="Expected content after <<<",
                    position=pos
                )

            content_word = content_result.value
            assert content_word is not None  # success implies a value
            content_value = content_word.display_text()

            redirect = Redirect(
                type=op_token.value, target=content_value,
                quote_type=content_word.effective_quote_char, fd=fd,
                target_word=content_word,
            )
            return ParseResult(success=True, value=redirect, position=content_result.position)

        # Normal redirection - needs a target
        target_result = self._parse_word_as_word(tokens, pos)
        if not target_result.success:
            return ParseResult(
                success=False,
                error=f"Expected redirection target after {op_token.value}",
                position=pos
            )

        target_word = target_result.value
        assert target_word is not None  # success implies a value
        target_value = target_word.display_text()

        # Check for combined redirect (&> or &>>)
        combined = getattr(op_token, 'combined_redirect', False)

        redirect = Redirect(
            type=op_token.value,
            target=target_value,
            fd=fd,
            combined=combined,
            target_word=target_word,
        )
        return ParseResult(success=True, value=redirect, position=target_result.position)

    @staticmethod
    def _parse_fd_dup_word(tok: Token) -> Optional[Redirect]:
        """Try to parse a WORD token as an FD duplication (e.g., 2>&1, >&-, <&0).

        Returns a Redirect node if the token matches, otherwise None.
        """
        if tok.type.name != 'WORD':
            return None
        match = _FD_DUP_RE.match(tok.value)
        if not match:
            return None

        source_fd_str, direction, target = match.groups()
        default_fd = 1 if direction == '>' else 0
        source_fd = int(source_fd_str) if source_fd_str else default_fd

        if target == '-':
            return Redirect(type=direction + '&-', target=None, fd=source_fd)
        return Redirect(
            type=direction + '&', target=None,
            fd=source_fd, dup_fd=int(target),
        )
