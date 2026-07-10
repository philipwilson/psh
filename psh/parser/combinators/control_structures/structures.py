"""Structure parsers for the shell parser combinator.

This module provides mixin parsers for function definitions, subshell
groups, and brace groups.
"""

from typing import TYPE_CHECKING, List, Optional, Tuple

from ....ast_nodes import (
    BraceGroup,
    FunctionDef,
    StatementList,
    SubshellGroup,
)
from ....core.assignment_utils import ASSIGNMENT_WORD_RE
from ....lexer.constants import KEYWORDS
from ....lexer.keyword_defs import matches_keyword
from ....lexer.token_types import Token
from ...recursive_descent.helpers import ParseError
from ..core import Parser, ParseResult, many
from ..diagnostics import (
    error_context_for_token,
    is_missing_nested_terminator,
    raise_committed_error,
)

if TYPE_CHECKING:
    from ._protocols import ControlStructureProtocol
    _Base = ControlStructureProtocol
else:
    _Base = object


# Token types that can serve as (part of) a function name in the POSIX
# ``name()`` form. bash is permissive: any word that is not a reserved word
# and not an assignment works (``my-func``, ``.dot``, ``f.g``, ``foo+bar``,
# ``9``, even ``[`` and ``]``). Mirrors the recursive descent parser's
# ``FunctionParser.NAME_TOKENS``.
_NAME_TOKEN_TYPES = frozenset({'WORD', 'LBRACKET', 'RBRACKET'})


def _peek_function_name(tokens: List[Token], pos: int) -> Optional[Tuple[str, int]]:
    """Peek a (possibly multi-token) function name at ``pos``.

    Mirrors the recursive descent parser's ``FunctionParser._peek_name_tokens``:
    word fusion already merged an adjacent name run (``foo+bar``, ``[foo]``) into
    one WORD. A name carrying an expansion or quoted piece (``foo$x``,
    ``foo"bar"``) has those as parts and is rejected (psh does not expand
    function names). Returns ``(name, token_count)`` or None.
    """
    if pos >= len(tokens) or tokens[pos].type.name not in _NAME_TOKEN_TYPES:
        return None
    token = tokens[pos]
    if any(p.is_expansion or p.quote_type is not None for p in token.parts):
        return None
    return token.value, 1


class StructureParserMixin(_Base):
    """Mixin providing structure parsers for ControlStructureParsers."""

    # Keywords that may open a non-brace function body (bash accepts any
    # compound command as the body; mirrors the recursive descent parser's
    # parse_compound_command).
    _COMPOUND_BODY_KEYWORDS = ('if', 'while', 'until', 'for', 'case', 'select')

    def _collect_definition_redirects(self, tokens: List[Token], pos: int):
        """Collect redirections trailing a function body.

        Redirections on the definition (``f() { ...; } > file``) belong to
        the function and are applied at each call (bash) — same semantics
        as the recursive descent parser's ``parse_function_def``.

        Returns:
            Tuple of (redirects list, new position)
        """
        # Zero or more redirections trailing the body — a plain ``many``: it
        # applies ``redirection`` until it stops matching and returns the list
        # gathered (never failing, so an empty list is a valid parse).
        result = many(self.commands.redirection).parse(tokens, pos)
        return list(result.value or []), result.position

    def _build_function_name(self) -> Parser[str]:
        """Parse a function name (possibly spanning several adjacent tokens).

        bash is permissive about ``name()`` names — ``9``, ``a.b``, ``foo+bar``,
        ``[x``, ``]`` are all valid — so this consumes any composite of
        name-able tokens without imposing an identifier shape. The POSIX-form
        gate in :meth:`_build_function_def` is where assignment words and
        reserved words are rejected (bash rejects those only in the POSIX form;
        the ``function`` keyword form accepts ``function a=b { ...; }``).
        Mirrors the recursive descent parser's ``_consume_name_tokens``.
        """
        def parse_function_name(tokens: List[Token], pos: int) -> ParseResult[str]:
            candidate = _peek_function_name(tokens, pos)
            if candidate is None:
                return ParseResult(success=False, error="Expected function name", position=pos)
            name, count = candidate
            return ParseResult(success=True, value=name, position=pos + count)

        return Parser(parse_function_name)

    def _parse_function_body(self, tokens: List[Token], pos: int) -> ParseResult[StatementList]:
        """Parse a function body: a brace group or any other compound command.

        A brace-group body is parsed by recursion on the real token stream —
        the same engine the compound bodies and brace groups use — rather
        than slicing the tokens between matching braces.
        ``build_statement_list`` stops at the ``RBRACE`` token (without
        consuming it); nested brace groups consume their own ``}``, so the
        recursion is the nesting tracker and no manual brace-counting is
        needed. A missing nested terminator (e.g. an ``if`` without ``fi``)
        raises a committed ``ParseError`` from the inner parser, which
        propagates out unchanged.

        Any other compound command (subshell, control structure, ``(( ))``)
        is also a valid body (bash); it is wrapped in a one-statement list —
        mirroring the recursive descent parser's parse_compound_command.
        """
        if pos < len(tokens) and tokens[pos].value != '{':
            tok = tokens[pos]
            if (tok.type.name in ('LPAREN', 'DOUBLE_LPAREN', 'DOUBLE_LBRACKET')
                    or any(matches_keyword(tok, kw)
                           for kw in self._COMPOUND_BODY_KEYWORDS)):
                body_result = self._compound_body.parse(tokens, pos)
                if not body_result.success:
                    return ParseResult(
                        success=False,
                        error=f"Invalid function body: {body_result.error}",
                        position=body_result.position,
                    )
                assert body_result.value is not None
                return ParseResult(
                    success=True,
                    value=StatementList(statements=[body_result.value]),
                    position=body_result.position,
                )

        # Expect {
        if pos >= len(tokens) or tokens[pos].value != '{':
            return ParseResult(success=False, error="Expected '{' to start function body", position=pos)
        pos += 1  # Skip '{'

        # A compound inside the body that misses its own terminator (an `if`
        # without `fi`, a loop without `done`) raises a committed ParseError
        # tagged with `missing_terminator`. The recursive descent parser reports
        # such a body error at end-of-input, so re-raise it there to keep
        # diagnostic parity.
        try:
            body_result = self.commands.build_statement_list().parse(tokens, pos)
        except ParseError as error:
            if is_missing_nested_terminator(error):
                raise_committed_error(tokens, len(tokens) - 1, error.summary)
            raise
        if not body_result.success:
            return ParseResult(success=False,
                               error=f"Invalid function body: {body_result.error}",
                               position=body_result.position)
        assert body_result.value is not None

        pos = body_result.position
        if pos >= len(tokens) or tokens[pos].type.name != 'RBRACE':
            return ParseResult(success=False, error="Unclosed function body", position=pos)
        pos += 1  # Skip '}'

        return ParseResult(
            success=True,
            value=body_result.value,
            position=pos,
        )

    def _build_posix_function(self) -> Parser[FunctionDef]:
        """Parse POSIX-style function: name() { body }"""
        def parse_posix_function(tokens: List[Token], pos: int) -> ParseResult[FunctionDef]:
            """Parse POSIX function."""
            # Parse name
            name_result = self._build_function_name().parse(tokens, pos)
            if not name_result.success:
                return ParseResult(success=False, error=name_result.error, position=pos)

            assert name_result.value is not None
            name = name_result.value
            pos = name_result.position

            # Expect ()
            if pos + 1 >= len(tokens) or tokens[pos].value != '(' or tokens[pos + 1].value != ')':
                return ParseResult(success=False, error="Expected () after function name", position=pos)
            pos += 2

            # Skip optional whitespace/newlines
            while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE']:
                pos += 1

            # Parse body
            body_result = self._parse_function_body(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error, position=body_result.position)

            assert body_result.value is not None
            redirects, end_pos = self._collect_definition_redirects(
                tokens, body_result.position)
            return ParseResult(
                success=True,
                value=FunctionDef(name=name, body=body_result.value,
                                  redirects=redirects),
                position=end_pos
            )

        return Parser(parse_posix_function)

    def _build_function_keyword_style(self) -> Parser[FunctionDef]:
        """Parse function keyword style: function name { body }"""
        def parse_function_keyword(tokens: List[Token], pos: int) -> ParseResult[FunctionDef]:
            """Parse function with keyword."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'function'):
                return ParseResult(success=False, error="Expected 'function' keyword", position=pos)
            pos += 1

            # Parse name
            name_result = self._build_function_name().parse(tokens, pos)
            if not name_result.success:
                return ParseResult(success=False, error="Expected function name after 'function'", position=name_result.position)

            assert name_result.value is not None
            name = name_result.value
            pos = name_result.position

            # Skip optional whitespace/newlines
            while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE']:
                pos += 1

            # Parse body
            body_result = self._parse_function_body(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error, position=body_result.position)

            assert body_result.value is not None
            redirects, end_pos = self._collect_definition_redirects(
                tokens, body_result.position)
            return ParseResult(
                success=True,
                value=FunctionDef(name=name, body=body_result.value,
                                  redirects=redirects),
                position=end_pos
            )

        return Parser(parse_function_keyword)

    def _build_function_keyword_with_parens(self) -> Parser[FunctionDef]:
        """Parse function keyword with parentheses: function name() { body }"""
        def parse_function_with_parens(tokens: List[Token], pos: int) -> ParseResult[FunctionDef]:
            """Parse function with keyword and parentheses."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'function'):
                return ParseResult(success=False, error="Expected 'function' keyword", position=pos)
            pos += 1

            # Parse name
            name_result = self._build_function_name().parse(tokens, pos)
            if not name_result.success:
                return ParseResult(success=False, error="Expected function name after 'function'", position=name_result.position)

            assert name_result.value is not None
            name = name_result.value
            pos = name_result.position

            # Expect ()
            if pos + 1 >= len(tokens) or tokens[pos].value != '(' or tokens[pos + 1].value != ')':
                return ParseResult(success=False, error="Expected () after function name", position=pos)
            pos += 2

            # Skip optional whitespace/newlines
            while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE']:
                pos += 1

            # Parse body
            body_result = self._parse_function_body(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error, position=body_result.position)

            assert body_result.value is not None
            redirects, end_pos = self._collect_definition_redirects(
                tokens, body_result.position)
            return ParseResult(
                success=True,
                value=FunctionDef(name=name, body=body_result.value,
                                  redirects=redirects),
                position=end_pos
            )

        return Parser(parse_function_with_parens)

    def _build_function_def(self) -> Parser[FunctionDef]:
        """Build parser for function definitions.

        Uses a wrapper that commits to function parsing when ``WORD (`` is
        detected, preventing fallthrough to simple-command parsing when
        the function name is invalid (e.g. ``123func() { ... }``).
        """
        posix_fn = self._build_posix_function()
        keyword_parens_fn = self._build_function_keyword_with_parens()
        keyword_fn = self._build_function_keyword_style()

        def parse_function_def(tokens: List[Token], pos: int) -> ParseResult[FunctionDef]:
            # Try keyword forms first (they start with 'function' keyword)
            result = keyword_parens_fn.parse(tokens, pos)
            if result.success:
                return result
            result = keyword_fn.parse(tokens, pos)
            if result.success:
                return result
            if pos < len(tokens) and matches_keyword(tokens[pos], 'function'):
                raise_committed_error(
                    tokens,
                    result.position,
                    result.error or "Invalid function definition",
                )

            # POSIX form: a (possibly multi-token) name immediately followed
            # by '(' ')' commits to function parsing — this keeps a bad body
            # (``9func() { }``) from falling through to simple-command parsing.
            # An assignment word (``arr=()``, ``a=b()``) is never a function
            # name (bash: array init or syntax error), and neither is a
            # reserved word; both are excluded so they route to the command
            # path. Mirrors the recursive descent parser's is_function_def.
            candidate = _peek_function_name(tokens, pos)
            if (candidate is not None
                    and not ASSIGNMENT_WORD_RE.match(candidate[0])
                    and candidate[0] not in KEYWORDS):
                count = candidate[1]
                if (pos + count + 1 < len(tokens)
                        and tokens[pos + count].type.name == 'LPAREN'
                        and tokens[pos + count + 1].type.name == 'RPAREN'):
                    # Committed — must be a function definition
                    result = posix_fn.parse(tokens, pos)
                    if not result.success:
                        # Hard error — raise ParseError to prevent fallthrough
                        raise_committed_error(
                            tokens,
                            result.position,
                            result.error or "Invalid function definition",
                        )
                    return result

            return ParseResult(success=False, error="Not a function definition", position=pos)

        return Parser(parse_function_def)

    def _build_subshell_group(self) -> Parser[SubshellGroup]:
        """Build parser for subshell group (...) syntax."""
        def parse_subshell_group(tokens: List[Token], pos: int) -> ParseResult[SubshellGroup]:
            # Expect '('
            lparen_result = self.tokens.lparen.parse(tokens, pos)
            if not lparen_result.success:
                return ParseResult(success=False, error="Expected '('", position=pos)
            pos = lparen_result.position

            # Parse body
            body_result = self.commands.statement_list.parse(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error, position=pos)
            assert body_result.value is not None
            if not body_result.value.statements:
                raise ParseError(error_context_for_token(
                    tokens[pos],
                    f"syntax error near unexpected token '{tokens[pos].value}'",
                ))
            pos = body_result.position

            # Expect ')'
            rparen_result = self.tokens.rparen.parse(tokens, pos)
            if not rparen_result.success:
                raise_committed_error(tokens, pos, "Expected ')'")
            pos = rparen_result.position

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=SubshellGroup(
                    statements=body_result.value,
                    redirects=redirects,
                ),
                position=pos,
            )

        return Parser(parse_subshell_group)

    def _build_brace_group(self) -> Parser[BraceGroup]:
        """Build parser for brace group {...} syntax."""
        def parse_brace_group(tokens: List[Token], pos: int) -> ParseResult[BraceGroup]:
            # Expect '{'
            lbrace_result = self.tokens.lbrace.parse(tokens, pos)
            if not lbrace_result.success:
                return ParseResult(success=False, error="Expected '{'", position=pos)
            pos = lbrace_result.position

            # Parse body
            body_result = self.commands.statement_list.parse(tokens, pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error, position=pos)
            assert body_result.value is not None
            if not body_result.value.statements:
                raise ParseError(error_context_for_token(
                    tokens[pos],
                    f"syntax error near unexpected token '{tokens[pos].value}'",
                ))
            pos = body_result.position

            # Expect '}'
            rbrace_result = self.tokens.rbrace.parse(tokens, pos)
            if not rbrace_result.success:
                raise_committed_error(tokens, pos, "Expected '}'")
            pos = rbrace_result.position

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=BraceGroup(
                    statements=body_result.value,
                    redirects=redirects,
                ),
                position=pos,
            )

        return Parser(parse_brace_group)
