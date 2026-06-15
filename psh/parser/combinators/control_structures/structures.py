"""Structure parsers for the shell parser combinator.

This module provides mixin parsers for function definitions, subshell
groups, and brace groups.
"""

from typing import TYPE_CHECKING, List

from ....ast_nodes import (
    BraceGroup,
    FunctionDef,
    StatementList,
    SubshellGroup,
)
from ....lexer.keyword_defs import matches_keyword
from ....lexer.token_types import Token
from ...recursive_descent.helpers import ParseError
from ..core import Parser, ParseResult
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


class StructureParserMixin(_Base):
    """Mixin providing structure parsers for ControlStructureParsers."""

    def _collect_definition_redirects(self, tokens: List[Token], pos: int):
        """Collect redirections trailing a function body.

        Redirections on the definition (``f() { ...; } > file``) belong to
        the function and are applied at each call (bash) — same semantics
        as the recursive descent parser's ``parse_function_def``.

        Returns:
            Tuple of (redirects list, new position)
        """
        redirects = []
        while pos < len(tokens):
            redir_result = self.commands.redirection.parse(tokens, pos)
            if not redir_result.success:
                break
            redirects.append(redir_result.value)
            pos = redir_result.position
        return redirects, pos

    def _build_function_name(self) -> Parser[str]:
        """Parse a valid function name."""
        def parse_function_name(tokens: List[Token], pos: int) -> ParseResult[str]:
            """Parse and validate function name."""
            if pos >= len(tokens):
                return ParseResult(success=False, error="Expected function name", position=pos)

            token = tokens[pos]
            if token.type.name != 'WORD':
                return ParseResult(success=False, error="Expected function name", position=pos)

            # Validate function name (must start with letter or underscore)
            name = token.value
            if not name:
                return ParseResult(success=False, error="Empty function name", position=pos)

            # First character must be letter or underscore
            if not (name[0].isalpha() or name[0] == '_'):
                return ParseResult(success=False,
                                 error=f"Invalid function name: {name} (must start with letter or underscore)",
                                 position=pos)

            # Rest must be alphanumeric, underscore, or hyphen
            for char in name[1:]:
                if not (char.isalnum() or char in '_-'):
                    return ParseResult(success=False,
                                     error=f"Invalid function name: {name} (contains invalid character '{char}')",
                                     position=pos)

            # Check it's not a reserved word
            reserved = {'if', 'then', 'else', 'elif', 'fi', 'while', 'do', 'done',
                       'for', 'case', 'esac', 'function', 'in', 'select'}
            if name in reserved:
                return ParseResult(success=False,
                                 error=f"Reserved word cannot be function name: {name}",
                                 position=pos)

            return ParseResult(success=True, value=name, position=pos + 1)

        return Parser(parse_function_name)

    def _parse_function_body(self, tokens: List[Token], pos: int) -> ParseResult[StatementList]:
        """Parse function body between { }."""
        # Expect {
        if pos >= len(tokens) or tokens[pos].value != '{':
            return ParseResult(success=False, error="Expected '{' to start function body", position=pos)
        outer_pos = pos + 1  # Track position in outer token stream

        # Skip optional newline after {
        if outer_pos < len(tokens) and tokens[outer_pos].type.name == 'NEWLINE':
            outer_pos += 1

        # Collect tokens until }
        body_tokens = []
        brace_count = 1

        while outer_pos < len(tokens) and brace_count > 0:
            token = tokens[outer_pos]
            if token.value == '{':
                brace_count += 1
            elif token.value == '}':
                brace_count -= 1
                if brace_count == 0:
                    break
            body_tokens.append(token)
            outer_pos += 1

        if brace_count > 0:
            return ParseResult(success=False, error="Unclosed function body", position=outer_pos)

        # Parse the body as a statement list
        if body_tokens:
            # For function bodies, we need stricter parsing
            statements = []
            inner_pos = 0  # Position within body_tokens

            # Skip leading separators
            while inner_pos < len(body_tokens) and body_tokens[inner_pos].type.name in ['SEMICOLON', 'NEWLINE']:
                inner_pos += 1

            # Parse statements
            while inner_pos < len(body_tokens):
                # Try to parse a statement
                try:
                    stmt_result = self.commands.statement.parse(body_tokens, inner_pos)
                except ParseError as error:
                    if is_missing_nested_terminator(error):
                        raise_committed_error(tokens, len(tokens) - 1, error.message)
                    raise
                if not stmt_result.success:
                    # Check if this is a real error or just end of statements
                    if inner_pos < len(body_tokens):
                        body_error = stmt_result.error
                        if "expected 'fi'" in body_error.lower():
                            body_error = "Syntax error in function body: missing 'fi' to close if statement"
                        elif "expected 'done'" in body_error.lower():
                            body_error = "Syntax error in function body: missing 'done' to close loop"
                        elif "expected 'esac'" in body_error.lower():
                            body_error = "Syntax error in function body: missing 'esac' to close case statement"
                        elif "expected 'then'" in body_error.lower():
                            body_error = "Syntax error in function body: missing 'then' in if statement"
                        else:
                            body_error = f"Invalid function body: {body_error}"
                        return ParseResult(success=False, error=body_error, position=outer_pos)
                    break

                statements.append(stmt_result.value)
                inner_pos = stmt_result.position

                # Skip separators
                while inner_pos < len(body_tokens) and body_tokens[inner_pos].type.name in ['SEMICOLON', 'NEWLINE']:
                    inner_pos += 1

            body_result = ParseResult(success=True, value=StatementList(statements=statements), position=inner_pos)
        else:
            # Empty body
            body_result = ParseResult(success=True, value=StatementList(statements=[]), position=0)

        outer_pos += 1  # Skip closing }

        return ParseResult(
            success=True,
            value=body_result.value,
            position=outer_pos
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

            # For POSIX form: if we see WORD followed by '(' ')', commit to
            # function parsing.  This prevents ``123func()`` from falling
            # through to simple-command parsing.
            # Exclude words containing '=' (assignments like ``arr=()``).
            if (pos < len(tokens) and tokens[pos].type.name == 'WORD'
                    and '=' not in tokens[pos].value
                    and pos + 1 < len(tokens) and tokens[pos + 1].value == '('
                    and pos + 2 < len(tokens) and tokens[pos + 2].value == ')'):
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

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=SubshellGroup(
                    statements=body_result.value,
                    redirects=redirects,
                    background=background,
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

            # Parse trailing redirections and background
            redirects, background, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=BraceGroup(
                    statements=body_result.value,
                    redirects=redirects,
                    background=background,
                ),
                position=pos,
            )

        return Parser(parse_brace_group)
