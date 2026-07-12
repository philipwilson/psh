"""
Function parsing for PSH shell.

This module handles parsing of function definitions.
"""

from typing import List, Optional, Tuple, cast

from ....ast_nodes import BraceGroup, FunctionDef, Redirect, Statement, StatementList
from ....core.assignment_utils import ASSIGNMENT_WORD_RE
from ....lexer.token_types import TokenType
from .base import ParserSubcomponent

# A word bash's lexer reads as an ASSIGNMENT (valid identifier, optional
# subscript, then `=` or `+=`). An assignment word followed by `()` is a
# SYNTAX ERROR in bash (`a=b() { :; }`, `a[0]=b() { :; }`), never a
# function definition — while a NON-assignment word containing `=` is a
# legal function name (`2=b()`, `a.b=c()` both define functions). The
# assignment-word shape is the shared ASSIGNMENT_WORD_RE.


class FunctionParser(ParserSubcomponent):
    """Parser for function constructs."""


    # Token types that can serve as (part of) a function name in the POSIX
    # `name()` form. bash is permissive: any word that is not a reserved
    # word and not an assignment works (`my-func`, `.dot`, `f.g`, `foo+bar`,
    # even `[` and `]`).
    NAME_TOKENS = (TokenType.WORD, TokenType.LBRACKET, TokenType.RBRACKET)

    def _peek_name_token(self) -> Optional[str]:
        """Peek the function-name word at the current position, or None.

        Word fusion already merged an adjacent name run — `foo+bar`, `2=b`,
        `[foo]` — into ONE WORD by the time the parser sees it, so a function
        name is always a single token. A name that carries an expansion or a
        quoted part (`foo$x`, `foo"bar"`) is rejected (psh does not expand
        function names; bash errors on them at execution time).
        """
        if not self.parser.match(*self.NAME_TOKENS):
            return None
        token = self.parser.peek()
        if any(p.is_expansion or p.quote_type is not None for p in token.parts):
            return None
        return token.value

    def is_function_def(self) -> bool:
        """Check if current position starts a function definition."""
        if self.parser.match(TokenType.FUNCTION):
            return True

        # Check for name() pattern
        name = self._peek_name_token()
        if name is None:
            return False

        # An assignment word is never a function name (bash: `a=b()` is a
        # syntax error near '('; `arr=(...)` is an array initialization).
        # Returning False routes both to the command path, where the array
        # parser or the statement-boundary check produces the right result.
        if ASSIGNMENT_WORD_RE.match(name):
            return False
        # A reserved word is never a `name()` function name (bash:
        # syntax error). `in` is the one keyword that lexes as a plain
        # WORD at command position; the rest already carry keyword
        # token types and fail the NAME_TOKENS match above.
        from ....lexer.constants import KEYWORDS
        if name in KEYWORDS:
            return False

        return (self.parser.peek(1).type == TokenType.LPAREN and
                self.parser.peek(2).type == TokenType.RPAREN)

    def _consume_name_token(self) -> str:
        """Consume the single function-name token, returning its text."""
        name = self._peek_name_token()
        if name is None:
            raise self.parser.error("Expected function name")
        self.parser.advance()
        return name

    def parse_function_def(self) -> FunctionDef:
        """Parse function definition."""
        name = None
        keyword_form = False

        if self.parser.match(TokenType.FUNCTION):
            self.parser.advance()
            self.parser.ctx.push_construct('function')
            keyword_form = True
            # The keyword form takes any word — including names the POSIX
            # form rejects (`function a=b { :; }` is valid bash).
            if not self.parser.match(*self.NAME_TOKENS):
                self.parser.expect(TokenType.WORD)  # raise the usual error
            name = self._consume_name_token()

            # Optional EMPTY parentheses `()` after the name. Only an immediate
            # `( )` is the marker; a `(` with content is a subshell BODY
            # (`function f ( echo x )`), left for parse_compound_command below.
            if (self.parser.match(TokenType.LPAREN) and
                    self.parser.peek(1).type == TokenType.RPAREN):
                self.parser.advance()  # (
                self.parser.advance()  # )
        else:
            # POSIX style: name()
            name = self._consume_name_token()
            self.parser.expect(TokenType.LPAREN)
            self.parser.expect(TokenType.RPAREN)

        self.parser.skip_newlines()
        body, body_redirects = self.parse_compound_command()
        if keyword_form:
            self.parser.ctx.pop_construct()

        # Redirections on the definition (f() { ...; } > file) belong to
        # the function and are applied at each call (bash). A brace body's
        # trailing redirects were consumed by the shared compound-command
        # parser and handed back as body_redirects, so they land on the
        # FunctionDef exactly as before; a subshell/control-structure body
        # keeps its own on its node, leaving nothing here.
        redirects = body_redirects + self.parser.redirections.parse_redirects()

        return FunctionDef(name, body, redirects=redirects)

    def parse_compound_command(self) -> Tuple[StatementList, List[Redirect]]:
        """Parse a function body through the shared compound-command chokepoint.

        Function bodies dispatch through the SAME
        ``CommandParser._parse_compound_component`` as pipeline components, so
        the ``MAX_NESTING_DEPTH`` guard accumulates inside function bodies too:
        a chain of 1,000 nested function definitions now raises a clean
        ParseError instead of a Python RecursionError (H12).

        Returns ``(body, redirects)`` in the shapes callers already expect:

        - ``{ ...; }`` — unwrapped to its bare ``StatementList`` (the historical
          function-body shape, NOT a wrapping ``BraceGroup``), and its trailing
          redirects (``f() { ...; } > log``) are handed back so they attach to
          the ``FunctionDef`` and apply at each call (bash).
        - ``( ...; )`` — kept as a ``SubshellGroup`` statement so each call forks
          (``f() (cd /; ...)`` must not change the caller's state — bash).
        - a control structure — kept as its own ``CompoundCommand`` statement.

          A subshell/control body owns its own trailing redirects on its node
          (matching the pre-existing AST), so nothing is handed back here.
        """
        # in_function_body=True suppresses the `\$(` argument-shape check:
        # here the token before a `(` body is the function NAME, and a name
        # ending in an escaped dollar (`function f\$ (echo hi)`) is legal at
        # parse time (bash) — see _parse_compound_component's docstring.
        component = self.parser.commands._parse_compound_component(
            in_function_body=True)
        if component is None:
            # Missing function body ({, (, or a compound keyword required).
            raise self.parser.error("Expected '{' for function body")

        if isinstance(component, BraceGroup):
            # bash rejects an empty function body `f() { }` — parse_brace_group
            # raised that already. Unwrap to the bare statement list; the
            # definition owns the brace's trailing redirects.
            return component.statements, component.redirects

        # A subshell group / control structure is both a CompoundCommand and a
        # Statement at runtime; mypy can't see the intersection here.
        cmd_list = StatementList()
        cmd_list.statements.append(cast(Statement, component))
        return cmd_list, []
