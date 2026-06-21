"""
Redirection parsing for PSH shell.

This module handles parsing of I/O redirections, heredocs, and here-strings.
"""

import re
from typing import List

from ....ast_nodes import Redirect
from ....lexer.token_types import Token, TokenType
from ..helpers import TokenGroups
from .base import ParserSubcomponent

# Pre-compiled regex for fd duplication (e.g. "2>&1", ">&-")
_FD_DUP_RE = re.compile(r'^(\d*)([><])&(-|\d+)$')
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
        """Parse here document redirect."""
        if not self.parser.match(TokenType.WORD, TokenType.STRING):
            raise self.parser.error("Expected delimiter after here document operator")

        delimiter_token = self.parser.advance()
        delimiter = delimiter_token.value

        # Determine if delimiter was quoted (disables variable expansion)
        heredoc_quoted = delimiter_token.type == TokenType.STRING

        redirect = Redirect(
            type=token.value,
            target=delimiter,
            heredoc_content=None,  # Content filled later
            heredoc_quoted=heredoc_quoted,
            fd=token.fd
        )

        # Store the heredoc key if available
        if hasattr(token, 'heredoc_key'):
            redirect.heredoc_key = token.heredoc_key

        return redirect

    def _parse_here_string(self, token: Token) -> Redirect:
        """Parse here string redirect."""
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self.parser.error("Expected string after here string operator")

        # Use Word AST parsing to handle variables and quotes properly
        word = self.parser.commands.parse_argument_as_word()
        content_value = word.display_text()
        quote_type = word.effective_quote_char

        return Redirect(
            type=token.value,
            target=content_value,
            quote_type=quote_type,
            fd=token.fd
        )

    def _parse_dup_redirect(self, token: Token) -> Redirect:
        """Parse file descriptor duplication redirect."""
        # Bare operator forms whose target is a separate token: ">& 2", "<& 0",
        # and the dynamic forms ">&$fd", "2>&$((n+1))". The lexer emits the
        # operator (with any fd prefix) as one token and the target separately.
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
                return Redirect(type=direction + '&-', target=None, fd=fd)
            if dup_part.isdigit():
                # Static numeric fd — resolve now (e.g. ">& 2").
                return Redirect(type=direction + '&', target=dup_part,
                                fd=fd, dup_fd=int(dup_part))
            # Dynamic target: keep the (expandable) string; dup_fd resolved at
            # execution time by FileRedirector._resolve_dup_fd.
            return Redirect(type=direction + '&', target=dup_part,
                            fd=fd, dup_fd=None)

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
                    fd=fd
                )
            else:
                return Redirect(
                    type=direction + '&',
                    target=None,
                    fd=fd,
                    dup_fd=int(target)
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
            # Keep the parsed Word so the executor can apply bash's
            # "ambiguous redirect" rule (unquoted target → ≠1 word is an error).
            target_word=word,
        )
