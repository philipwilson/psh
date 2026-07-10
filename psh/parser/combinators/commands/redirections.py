"""Redirection parsers for the shell parser combinator.

This module provides the mixin parsing I/O redirections, heredocs, here
strings, and fd-duplication words for ``CommandParsers``.
"""

from typing import TYPE_CHECKING, List, Optional

from ....ast_nodes import Redirect
from ....lexer.token_types import Token
from ..core import ParseResult
from ._constants import (
    _FD_DUP_BARE_RE,
    _FD_DUP_MOVE_RE,
    _FD_DUP_RE,
    _WORD_LIKE_TYPES,
)

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
        # redirects like 2>, 3>>). The named-fd prefix (``{name}>``, set by the
        # lexer's _try_var_fd_redirect) rides on ``var_fd`` and must be carried
        # onto every Redirect built here — mirrors the recursive descent parser.
        fd = op_token.fd
        var_fd = getattr(op_token, 'var_fd', None)

        # Handle redirect duplication (e.g., 2>&1, >&2, etc.)
        if op_token.type.name == 'REDIRECT_DUP':
            return self._parse_dup_redirection(tokens, pos, op_token)

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
                                heredoc_quoted=heredoc_quoted, fd=fd,
                                var_fd=var_fd)
            # The lexer's collector key links this redirect to its body
            # (populated post-parse by HeredocProcessor). A non-None key means a
            # body was collected for this operator token.
            if op_token.heredoc_key is not None:
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
                target_word=content_word, var_fd=var_fd,
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
            var_fd=var_fd,
        )
        return ParseResult(success=True, value=redirect, position=target_result.position)

    def _parse_dup_redirection(
        self, tokens: List[Token], pos: int, op_token: Token
    ) -> ParseResult[Redirect]:
        """Parse an fd-duplication redirect: ``2>&1``, ``>&-``, the move form
        ``[n]>&m-``, and the bare forms (``>&$fd`` dynamic, ``>&word`` csh).

        The named-fd prefix (``{name}>&``, set by the lexer's
        ``_try_var_fd_redirect``) rides on ``op_token.var_fd`` and is carried
        onto every Redirect built here — mirrors the recursive descent parser.
        """
        var_fd = getattr(op_token, 'var_fd', None)
        # Single-token dup/close: 2>&1, 3<&0, >&-, 3>&-.
        dup_match = _FD_DUP_RE.match(op_token.value)
        if dup_match:
            source_fd_str, direction, target = dup_match.groups()
            default_fd = 1 if direction == '>' else 0
            source_fd = int(source_fd_str) if source_fd_str else default_fd
            if target == '-':
                redirect = Redirect(type=direction + '&-', target=None,
                                    fd=source_fd, var_fd=var_fd)
            else:
                redirect = Redirect(
                    type=direction + '&', target=None,
                    fd=source_fd, dup_fd=int(target), var_fd=var_fd,
                )
            return ParseResult(success=True, value=redirect, position=pos)

        # Move form: [n]>&m- / [n]<&m- (dup m onto n, then close source m).
        move_match = _FD_DUP_MOVE_RE.match(op_token.value)
        if move_match:
            source_fd_str, direction, target = move_match.groups()
            default_fd = 1 if direction == '>' else 0
            source_fd = int(source_fd_str) if source_fd_str else default_fd
            redirect = Redirect(type=direction + '&', target=None, fd=source_fd,
                                dup_fd=int(target), move=True, var_fd=var_fd)
            return ParseResult(success=True, value=redirect, position=pos)

        # Bare operator with the target in the following token: ">& 2", ">&$fd",
        # and the csh-style ">&word" combined redirect.
        bare = _FD_DUP_BARE_RE.match(op_token.value)
        if bare:
            source_fd_str, direction = bare.groups()
            default_fd = 1 if direction == '>' else 0
            source_fd = int(source_fd_str) if source_fd_str else default_fd
            target_result = self._parse_word_as_word(tokens, pos)
            if not target_result.success:
                return ParseResult(
                    success=False,
                    error=f"Expected file descriptor after {op_token.value}",
                    position=pos)
            word = target_result.value
            assert word is not None
            dup_part = word.display_text()
            if dup_part == '-':
                redirect = Redirect(type=direction + '&-', target=None,
                                    fd=source_fd, var_fd=var_fd)
            elif dup_part.isdigit():
                redirect = Redirect(type=direction + '&', target=dup_part,
                                    fd=source_fd, dup_fd=int(dup_part),
                                    var_fd=var_fd)
            elif (direction == '>' and not source_fd_str
                    and not word.has_expansion_parts):
                # csh-style `>&word`: combined redirect to the file (== &>word).
                redirect = Redirect(type='>&', target=dup_part, fd=None,
                                    combined=True, target_word=word,
                                    var_fd=var_fd)
            else:
                redirect = Redirect(type=direction + '&', target=dup_part,
                                    fd=source_fd, dup_fd=None, var_fd=var_fd)
            return ParseResult(success=True, value=redirect,
                               position=target_result.position)

        # Unrecognized shape: keep the old lenient fallback.
        redirect = Redirect(type=op_token.value, target='', fd=op_token.fd,
                            var_fd=var_fd)
        return ParseResult(success=True, value=redirect, position=pos)

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
