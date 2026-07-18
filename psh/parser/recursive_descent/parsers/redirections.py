"""
Redirection parsing for PSH shell.

This module handles parsing of I/O redirections, heredocs, and here-strings.
"""

import re
from typing import List

from ....ast_nodes import Redirect
from ....lexer.heredoc_lexer import (
    delimiter_token_acceptable,
    raw_delimiter_from_tokens,
)
from ....lexer.token_types import Token, TokenType
from ....utils.heredoc_detection import unquote_heredoc_delimiter
from ..helpers import TokenGroups
from .base import ParserSubcomponent

# Pre-compiled regex for fd duplication (e.g. "2>&1", ">&-")
_FD_DUP_RE = re.compile(r'^(\d*)([><])&(-|\d+)$')
# Move form "[n]>&m-" / "[n]<&m-": dup m onto n, then close the source m.
_FD_DUP_MOVE_RE = re.compile(r'^(\d*)([><])&(\d+)-$')
# Bare dup operator whose target is a separate (dynamic) token, e.g. ">&$fd",
# "2>&$((n+1))" — the lexer emits just "N>&"/">&"/"<&" here.
_FD_DUP_BARE_RE = re.compile(r'^(\d*)([><])&$')


class RedirectionParser(ParserSubcomponent):
    """Parser for redirection constructs."""


    def parse_redirects(self) -> List[Redirect]:
        """Parse zero or more redirections."""
        redirects = []
        while self.parser.match_any(TokenGroups.REDIRECTS):
            redirects.append(self.parse_redirect())
        return redirects

    def parse_fd_dup_word(self) -> Redirect:
        """Parse file descriptor duplication from a WORD token."""
        # This is called when we have a WORD token like ">&2" or "2>&1"
        token = self.parser.advance()
        value = token.value

        match = _FD_DUP_RE.match(value)
        if not match:
            raise self.parser.error(f"Invalid fd duplication syntax: {value}")

        source_fd_str, direction, target = match.groups()

        # Default source fd is 1 for > and 0 for <
        if source_fd_str:
            source_fd = int(source_fd_str)
        else:
            source_fd = 1 if direction == '>' else 0

        # Handle closing fd with >&- or <&-
        if target == '-':
            return Redirect(
                type=direction + '&-',
                target=None,
                fd=source_fd
            )
        else:
            # Regular fd duplication
            return Redirect(
                type=direction + '&',
                target=None,
                fd=source_fd,
                dup_fd=int(target)
            )

    def parse_redirect(self) -> Redirect:
        """Parse a single redirection."""
        redirect_token = self.parser.advance()

        # Dispatch to specific redirect parser
        if redirect_token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
            return self._parse_heredoc(redirect_token)
        elif redirect_token.type == TokenType.HERE_STRING:
            return self._parse_here_string(redirect_token)
        elif redirect_token.type == TokenType.REDIRECT_DUP:
            return self._parse_dup_redirect(redirect_token)
        else:
            return self._parse_standard_redirect(redirect_token)

    def _parse_heredoc(self, token: Token) -> Redirect:
        """Parse here document redirect.

        The delimiter tokens are consumed POSITIONALLY (so trailing composite
        parts are not parsed as command arguments); the delimiter TRUTH — raw
        spelling, quotedness, body — comes from the LexedUnit's spec entry,
        keyed by the operator token's ``heredoc_id``. ``Redirect.target`` is
        the RAW delimiter spelling (what the formatter re-emits); the literal
        terminator is derived from it through the one quote-removal rule
        wherever needed. Without a heredoc map (a bare ``Parser(tokens)``,
        bodies still in the stream), the raw spelling is recovered from the
        source span (or token values as a last resort) and quotedness from
        the same one rule — never a private token-type heuristic.
        """
        # The delimiter word may START with any word-like piece taken
        # literally (``<<$VAR`` → terminator ``$VAR``, ``<< <(x)`` →
        # terminator ``<(x)`` — bash never expands the delimiter). The
        # accept rule is shared with the lexer's registration scan
        # (delimiter_token_acceptable: _DELIMITER_PART_TYPES + the procsub
        # no-paren-nesting rule) so the parser accepts exactly the
        # delimiters HeredocLexer registered.
        if (self.parser.at_end()
                or not delimiter_token_acceptable(self.parser.peek())):
            raise self.parser.error("Expected delimiter after here document operator")

        delim_tokens = [self.parser.advance()]
        # A composite delimiter spans several ADJACENT word-like tokens
        # (`<<E"O"F`, `<<E$X`, `<<E<(x)`). Consume them all.
        while (delimiter_token_acceptable(self.parser.peek())
               and getattr(self.parser.peek(), 'adjacent_to_previous', False)):
            delim_tokens.append(self.parser.advance())

        heredocs = self.parser.ctx.heredocs
        heredoc_id = token.heredoc_id
        if heredocs is not None:
            # Heredoc-aware parse: the spec entry is the sole authority. A
            # missing id or entry is a hard error, not a silent None.
            if heredoc_id is None:
                raise self.parser.error(
                    "here document operator has no collected-body id")
            entry = heredocs.get(heredoc_id)
            if entry is None:
                raise self.parser.error(
                    f"here document body not collected (id {heredoc_id})")
            return Redirect(
                type=token.value,
                target=entry.spec.raw,
                heredoc_content=entry.collected.body,
                heredoc_quoted=entry.spec.quoted,
                heredoc_id=heredoc_id,
                fd=token.fd,
            )

        # Bare parse (bodies still in the token stream; unit-test path):
        # recover the raw spelling from the source span when available —
        # token values drop a VARIABLE's `$` and a STRING's quotes — and
        # derive quotedness through the one rule.
        source_text = self.parser.ctx.source_text
        start = delim_tokens[0].position
        end = delim_tokens[-1].end_position
        if source_text is not None and 0 <= start <= end <= len(source_text):
            raw = source_text[start:end]
        else:
            raw = raw_delimiter_from_tokens(delim_tokens)
        _, heredoc_quoted = unquote_heredoc_delimiter(raw)
        return Redirect(
            type=token.value,
            target=raw,
            heredoc_content=None,
            heredoc_quoted=heredoc_quoted,
            fd=token.fd,
        )

    def _parse_here_string(self, token: Token) -> Redirect:
        """Parse here string redirect."""
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self.parser.error("Expected string after here string operator")

        # Use Word AST parsing to handle variables and quotes properly. Carry
        # the parsed Word (per-part quote context) so the executor expands it
        # quote-aware — a composite like `foo$v"dq"` keeps the `$v`/`"dq"`
        # boundary instead of flattening to `foo$vdq` and re-expanding. The
        # flat target/quote_type stay for display and the no-Word fallback.
        word = self.parser.commands.parse_argument_as_word()
        content_value = word.display_text()
        quote_type = word.effective_quote_char

        return Redirect(
            type=token.value,
            target=content_value,
            quote_type=quote_type,
            fd=token.fd,
            target_word=word,
        )

    def _parse_dup_redirect(self, token: Token) -> Redirect:
        """Parse file descriptor duplication redirect."""
        var_fd = getattr(token, 'var_fd', None)
        # Bare operator forms whose target is a separate token: ">& 2", "<& 0",
        # the dynamic forms ">&$fd"/"2>&$((n+1))", and the csh-style combined
        # redirect ">&word" (a filename target). The lexer emits the operator
        # (with any fd prefix) as one token and the target separately.
        bare = _FD_DUP_BARE_RE.match(token.value)
        if bare:
            source_fd_str, direction = bare.groups()
            default_fd = 1 if direction == '>' else 0
            fd = int(source_fd_str) if source_fd_str else default_fd

            if not self.parser.match_any(TokenGroups.WORD_LIKE):
                raise self.parser.error(f"Expected file descriptor after {token.value}")

            # Parse the target as a Word so $fd / $((expr)) / $(cmd) are captured
            # and resolved at execution time.
            word = self.parser.commands.parse_argument_as_word()
            dup_part = word.display_text()

            if dup_part == '-':
                return Redirect(type=direction + '&-', target=None, fd=fd,
                                var_fd=var_fd)
            if dup_part.isdigit():
                # Static numeric fd — resolve now (e.g. ">& 2").
                return Redirect(type=direction + '&', target=dup_part,
                                fd=fd, dup_fd=int(dup_part), var_fd=var_fd)
            if (direction == '>' and not source_fd_str
                    and not word.has_expansion_parts):
                # csh-style `>&word`: fd omitted + a static, non-numeric,
                # non-'-' word redirects BOTH stdout and stderr to that file,
                # exactly like `&>word`. `combined` is honored ahead of `type`
                # everywhere, so keep `>&` for a faithful round-trip.
                return Redirect(type='>&', target=dup_part, fd=None,
                                combined=True, var_fd=var_fd, target_word=word)
            # Dynamic target: keep the (expandable) string; dup_fd resolved at
            # execution time by FileRedirector._resolve_dup_fd.
            return Redirect(type=direction + '&', target=dup_part,
                            fd=fd, dup_fd=None, var_fd=var_fd)

        # Move form "[n]>&m-" / "[n]<&m-": dup m onto n, then close source m.
        move = _FD_DUP_MOVE_RE.match(token.value)
        if move:
            source_fd_str, direction, target = move.groups()
            default_fd = 1 if direction == '>' else 0
            fd = int(source_fd_str) if source_fd_str else default_fd
            return Redirect(type=direction + '&', target=None, fd=fd,
                            dup_fd=int(target), move=True, var_fd=var_fd)

        # Handle single-token forms containing >&  or <&  (e.g., "2>&1", "3<&0", "3>&-", "3<&-")
        match = _FD_DUP_RE.match(token.value)
        if match:
            source_fd_str, direction, target = match.groups()
            default_fd = 1 if direction == '>' else 0
            fd = int(source_fd_str) if source_fd_str else default_fd

            if target == '-':
                return Redirect(
                    type=direction + '&-',
                    target=None,
                    fd=fd,
                    var_fd=var_fd,
                )
            else:
                return Redirect(
                    type=direction + '&',
                    target=None,
                    fd=fd,
                    dup_fd=int(target),
                    var_fd=var_fd,
                )

        raise self.parser.error(f"Invalid redirection operator: {token.value}")

    def _parse_standard_redirect(self, token: Token) -> Redirect:
        """Parse standard redirection (< > >> <> >| and combined &> &>>)."""
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self.parser.error("Expected file name")

        # Use Word AST parsing to handle quoted composites like test'file'.txt
        word = self.parser.commands.parse_argument_as_word()
        target_value = word.display_text()

        # Check for combined redirect (&> or &>>)
        combined = getattr(token, 'combined_redirect', False)

        return Redirect(
            type=token.value,
            target=target_value,
            fd=token.fd,
            combined=combined,
            var_fd=getattr(token, 'var_fd', None),
            # Keep the parsed Word so the executor can apply bash's
            # "ambiguous redirect" rule (unquoted target → ≠1 word is an error).
            target_word=word,
        )
