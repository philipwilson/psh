"""Redirection parsers for the shell parser combinator.

This module provides the mixin parsing I/O redirections, heredocs, here
strings, and fd-duplication words for ``CommandParsers``.
"""

from typing import TYPE_CHECKING, List, Optional

from ....ast_nodes import Redirect
from ....lexer.heredoc_lexer import (
    delimiter_token_acceptable,
    raw_delimiter_from_tokens,
)
from ....lexer.token_types import Token
from ....utils.heredoc_detection import unquote_heredoc_delimiter
from ..core import ParseResult
from ._constants import (
    _FD_DUP_BARE_RE,
    _FD_DUP_MOVE_RE,
    _FD_DUP_RE,
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
            # The delimiter tokens are consumed POSITIONALLY; the delimiter
            # TRUTH (raw spelling, quotedness, body) comes from the
            # LexedUnit's spec entry, keyed by the operator token's
            # heredoc_id — mirrors the recursive descent parser's
            # _parse_heredoc. The accept rule is shared with the lexer's
            # registration scan (delimiter_token_acceptable).
            if (pos >= len(tokens)
                    or not delimiter_token_acceptable(tokens[pos])):
                return ParseResult(
                    success=False,
                    error="Expected heredoc delimiter",
                    position=pos
                )

            delim_tokens = [tokens[pos]]
            pos += 1
            # A composite delimiter spans several ADJACENT word-like tokens
            # (`<<E"O"F`, `<<E$X`, `<<E<(x)`); consume them all so the
            # trailing parts are not parsed as command arguments.
            while (pos < len(tokens)
                   and delimiter_token_acceptable(tokens[pos])
                   and getattr(tokens[pos], 'adjacent_to_previous', False)):
                delim_tokens.append(tokens[pos])
                pos += 1

            heredocs = self.heredocs
            heredoc_id = op_token.heredoc_id
            if heredocs is not None and heredoc_id is not None:
                entry = heredocs.get(heredoc_id)
                if entry is None:
                    return ParseResult(
                        success=False,
                        error=f"here document body not collected (id {heredoc_id})",
                        position=pos)
                redirect = Redirect(type=op_token.value,
                                    target=entry.spec.raw,
                                    heredoc_content=entry.collected.body,
                                    heredoc_quoted=entry.spec.quoted,
                                    heredoc_id=heredoc_id,
                                    fd=fd, var_fd=var_fd)
                return ParseResult(success=True, value=redirect, position=pos)

            # Bare parse (no collected map — bodies still in the stream):
            # reconstruct the raw spelling from token values (the combinator
            # has no source text) and derive quotedness through the one
            # quote-removal rule — never a private token-type heuristic.
            raw = raw_delimiter_from_tokens(delim_tokens)
            _, heredoc_quoted = unquote_heredoc_delimiter(raw)
            redirect = Redirect(type=op_token.value, target=raw,
                                heredoc_quoted=heredoc_quoted, fd=fd,
                                var_fd=var_fd, heredoc_id=heredoc_id)
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
