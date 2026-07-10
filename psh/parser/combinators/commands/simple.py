"""Simple-command parsers for the shell parser combinator.

This module provides the mixin building :class:`SimpleCommand` nodes from
word-like tokens, redirections, fd-dup words, and array assignments.
"""

from typing import TYPE_CHECKING, List, Optional

from ....ast_nodes import ArrayAssignment, Redirect, SimpleCommand
from ....lexer.token_types import Token, TokenType
from ....parser.recursive_descent.helpers import ParseError
from ...array_flat_text import process_unquoted_element_escapes
from ..core import Parser, ParseResult
from ..diagnostics import error_context_for_token

if TYPE_CHECKING:
    from ._protocols import CommandParsersProtocol
    _Base = CommandParsersProtocol
else:
    _Base = object


class SimpleCommandMixin(_Base):
    """Mixin providing simple-command parsers for CommandParsers."""

    def _build_simple_command_parser(self) -> Parser[SimpleCommand]:
        """Build parser for simple commands.

        Returns:
            Parser that produces SimpleCommand nodes
        """
        def parse_simple_command(tokens: List[Token], pos: int) -> ParseResult[SimpleCommand]:
            """Parse a simple command with words, redirections, and FD dups."""
            word_tokens: List[Token] = []
            redirects: List[Redirect] = []
            array_assignments: List[ArrayAssignment] = []
            parsed_regular_arg = False

            # Collect words, redirections, and FD dup words in any order
            while pos < len(tokens):
                # Try FD dup word first (e.g., 2>&1, >&-)
                if pos < len(tokens) and tokens[pos].type.name == 'WORD':
                    fd_dup = self._parse_fd_dup_word(tokens[pos])
                    if fd_dup is not None:
                        redirects.append(fd_dup)
                        pos += 1
                        continue

                if not parsed_regular_arg:
                    array_result = self.arrays.parse_assignment(tokens, pos)
                    if array_result.success:
                        assert array_result.value is not None
                        array_assignments.append(array_result.value)
                        pos = array_result.position
                        continue

                # Try redirection (includes FD-prefixed redirects)
                redir_result = self.redirection.parse(tokens, pos)
                if redir_result.success:
                    redirects.append(redir_result.value)
                    pos = redir_result.position
                    continue
                if pos < len(tokens) and self.tokens.is_redirect_operator(tokens[pos]):
                    error_pos = min(redir_result.position, len(tokens) - 1)
                    raise ParseError(error_context_for_token(
                        tokens[error_pos],
                        redir_result.error or "Invalid redirection",
                    ))

                # Try a word-like token
                word_result = self.tokens.word_like.parse(tokens, pos)
                if word_result.success:
                    assert word_result.value is not None
                    unclosed = self._unclosed_expansion_error(word_result.value)
                    if unclosed is not None:
                        raise ParseError(error_context_for_token(
                            word_result.value, unclosed))
                    if self.arrays.is_initializer_head(tokens, pos):
                        init_result = self.arrays.parse_initialization(tokens, pos)
                        if not init_result.success:
                            return ParseResult(
                                success=False,
                                error=init_result.error,
                                position=init_result.position,
                            )
                        array_init = init_result.value
                        assert array_init is not None
                        # Collapse unquoted escapes so this flat text (the
                        # declaration builtin's lookup key) equals the
                        # escape-processed argv — see array_flat_text (shared
                        # with the recursive-descent path so both keys match).
                        flat_text = process_unquoted_element_escapes(
                            array_init.name
                            + ('+=' if array_init.is_append else '=')
                            + '('
                            + ' '.join(array_init.elements)
                            + ')'
                        )
                        array_token = Token(
                            type=TokenType.WORD,
                            value=flat_text,
                            position=getattr(tokens[pos], 'position', 0),
                            array_init=array_init,
                        )
                        word_tokens.append(array_token)
                        pos = init_result.position
                        parsed_regular_arg = True
                        continue

                    word_tokens.append(word_result.value)
                    pos = word_result.position
                    parsed_regular_arg = True
                    continue

                # Nothing matched — stop collecting
                break

            if not word_tokens and not redirects and not array_assignments:
                return ParseResult(success=False, error="Expected command", position=pos)

            # A trailing '&' is NOT consumed here: backgrounding applies to
            # the whole and-or list and is handled at that level (POSIX).
            cmd = self._build_simple_command(
                word_tokens,
                redirects,
                array_assignments=array_assignments,
            )

            return ParseResult(
                success=True,
                value=cmd,
                position=pos
            )

        return Parser(parse_simple_command)

    @staticmethod
    def _unclosed_expansion_error(tok: Token) -> Optional[str]:
        """Return an error message if the token carries an unclosed expansion.

        The lexer tolerates ``${``, ``$(``, `` ` ``, ``$((``, and ``<(``/``>(``
        without their closer (interactive line-continuation needs the tokens);
        at parse time they are syntax errors. Mirrors the recursive descent
        parser's _check_for_unclosed_expansions.
        """
        for part in tok.parts or ():
            if part.expansion_type and part.expansion_type.endswith('_unclosed'):
                return f"syntax error: unclosed expansion '{part.value}'"
        value = tok.value
        kind = tok.type.name
        if kind == 'VARIABLE' and value.startswith('${') and not value.endswith('}'):
            return f"syntax error: unclosed parameter expansion '{value}'"
        if kind == 'COMMAND_SUB' and not value.endswith(')'):
            return f"syntax error: unclosed command substitution '{value}'"
        if kind == 'COMMAND_SUB_BACKTICK' and value.count('`') == 1:
            return f"syntax error: unclosed backtick substitution '{value}'"
        if kind == 'ARITH_EXPANSION' and not value.endswith('))'):
            return f"syntax error: unclosed arithmetic expansion '{value}'"
        if kind in ('PROCESS_SUB_IN', 'PROCESS_SUB_OUT') and not value.endswith(')'):
            return f"syntax error: unclosed process substitution '{value}'"
        return None

    def _build_simple_command(self, word_tokens: List[Token],
                             redirects: List[Redirect],
                             array_assignments: Optional[List[ArrayAssignment]] = None) -> SimpleCommand:
        """Build a SimpleCommand with proper token type and quote preservation.

        The lexer emits one WORD per shell word (word fusion), so each token is
        a complete word; build its Word AST (SimpleCommand.args derives from
        them).
        """
        cmd = SimpleCommand(
            redirects=redirects,
            array_assignments=array_assignments or [],
        )

        for tok in word_tokens:
            word = self.expansions.build_word_from_token(tok)
            if tok.array_init is not None:
                word.array_init = tok.array_init
            cmd.words.append(word)

        return cmd
