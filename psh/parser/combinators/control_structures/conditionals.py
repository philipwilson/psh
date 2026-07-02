"""Conditional parsers for the shell parser combinator.

This module provides mixin parsers for if/elif/else and case statements.
"""

from typing import TYPE_CHECKING, List, Tuple

from ....ast_nodes import (
    CaseConditional,
    CaseItem,
    CasePattern,
    CommandList,
    IfConditional,
)
from ....lexer.keyword_defs import matches_keyword
from ....lexer.token_types import Token, TokenType
from ..core import Parser, ParseResult
from ..diagnostics import raise_committed_error
from ..utils import format_token_value

if TYPE_CHECKING:
    from ._protocols import ControlStructureProtocol
    _Base = ControlStructureProtocol
else:
    _Base = object

CASE_TERMINATOR_TOKENS = {
    TokenType.DOUBLE_SEMICOLON: ';;',
    TokenType.SEMICOLON_AMP: ';&',
    TokenType.AMP_SEMICOLON: ';;&',
}

# Token-type names that end a case-item command body (the ;; / ;& / ;;&
# terminators), for build_statement_list's terminator_types.
_CASE_BODY_TERMINATOR_TYPES = frozenset(t.name for t in CASE_TERMINATOR_TOKENS)


def _parse_case_pattern_value(tokens, pos, pattern_types):
    """Parse a single case pattern value.

    Returns:
        (pattern_string, token, new_pos) or (None, None, pos) if no
        pattern found. The token lets the caller build a Word carrying
        quote context (quoted pattern text matches literally).
    """
    if pos >= len(tokens):
        return None, None, pos

    tok = tokens[pos]

    if tok.type.name in pattern_types:
        return format_token_value(tok), tok, pos + 1

    return None, None, pos


class ConditionalParserMixin(_Base):
    """Mixin providing conditional parsers for ControlStructureParsers."""

    def _make_case_pattern(self, pattern_str, pattern_tok):
        """Build a CasePattern carrying per-part quote context.

        The Word lets the executor distinguish quoted (literal) from
        unquoted (glob-active) pattern text — same semantics as the
        recursive descent parser's ``_parse_case_pattern``.
        """
        try:
            word = self.commands.expansions.build_word_from_token(pattern_tok)
        except ValueError:
            word = None  # fall back to the flattened-string path
        return CasePattern(pattern_str, word=word)

    def _build_if_statement(self) -> Parser[IfConditional]:
        """Build parser for if/then/elif/else/fi statements."""
        def parse_condition_then(tokens: List[Token], pos: int) -> ParseResult[Tuple[CommandList, CommandList]]:
            """Parse a condition-then pair."""
            # Parse the condition by recursion: a statement list up to (but not
            # consuming) the command-position 'then'. Parsing on the real token
            # stream — rather than slicing to the first 'then' — means a 'then'
            # that is merely an argument ('if echo then; then ...') is consumed
            # as a word, matching bash and the recursive-descent parser.
            condition_result = self.commands.build_statement_list(
                frozenset({'then'})).parse(tokens, pos)
            if not condition_result.success:
                return ParseResult(success=False, error=condition_result.error,
                                   position=condition_result.position)
            assert condition_result.value is not None
            current_pos = condition_result.position

            if current_pos >= len(tokens) or not matches_keyword(tokens[current_pos], 'then'):
                return ParseResult(success=False,
                                 error="Expected 'then' in if statement",
                                 position=current_pos)

            current_pos += 1  # Skip 'then'

            # Skip optional separator after 'then'
            empty_body_error_pos = current_pos
            if current_pos < len(tokens) and tokens[current_pos].type.name in ['SEMICOLON', 'NEWLINE']:
                empty_body_error_pos = current_pos
                current_pos += 1

            # Parse the body by recursion up to (not consuming) elif/else/fi.
            # Nested if statements consume their own 'fi', so the keyword seen
            # here ends *this* body. A foreign terminator (e.g. a 'done' when
            # the matching 'fi' is missing) makes self.statement fail with
            # "Expected command" at that token — matching recursive descent.
            body_result = self.commands.build_statement_list(
                frozenset({'elif', 'else', 'fi'})).parse(tokens, current_pos)
            if not body_result.success:
                return ParseResult(success=False, error=body_result.error,
                                   position=body_result.position)
            assert body_result.value is not None  # success implies a body
            current_pos = body_result.position
            if not body_result.value.statements:
                return ParseResult(success=False,
                                 error="Expected command in then body",
                                 position=empty_body_error_pos)

            return ParseResult(
                success=True,
                value=(condition_result.value, body_result.value),
                position=current_pos
            )

        # Main if statement parser
        def parse_if_statement(tokens: List[Token], pos: int) -> ParseResult[IfConditional]:
            """Parse complete if statement."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'if'):
                return ParseResult(success=False, error="Expected 'if'", position=pos)

            pos += 1  # Skip 'if'

            # Parse main condition and then part
            main_result = parse_condition_then(tokens, pos)
            if not main_result.success:
                raise_committed_error(
                    tokens,
                    main_result.position,
                    main_result.error or "Invalid if statement",
                )

            assert main_result.value is not None
            condition, then_part = main_result.value
            pos = main_result.position

            # Parse elif parts
            elif_parts: List[Tuple[CommandList, CommandList]] = []
            while pos < len(tokens) and matches_keyword(tokens[pos], 'elif'):
                pos += 1  # Skip 'elif'
                elif_result = parse_condition_then(tokens, pos)
                if not elif_result.success:
                    raise_committed_error(
                        tokens,
                        elif_result.position,
                        elif_result.error or "Invalid elif clause",
                    )
                assert elif_result.value is not None
                elif_parts.append(elif_result.value)
                pos = elif_result.position

            # Parse optional else part
            else_part = None
            if pos < len(tokens) and matches_keyword(tokens[pos], 'else'):
                pos += 1  # Skip 'else'

                # Skip optional separator after 'else'
                if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                    pos += 1

                # Parse else body by recursion up to (not consuming) 'fi'.
                else_result = self.commands.build_statement_list(
                    frozenset({'fi'})).parse(tokens, pos)
                if not else_result.success:
                    raise_committed_error(
                        tokens,
                        else_result.position,
                        else_result.error or "Failed to parse else body",
                    )
                pos = else_result.position
                else_part = else_result.value

            # Expect 'fi'
            if pos >= len(tokens):
                raise_committed_error(
                    tokens,
                    pos,
                    "Unexpected end of input: expected 'fi' to close if statement",
                    terminator='fi',
                )
            if not matches_keyword(tokens[pos], 'fi'):
                raise_committed_error(
                    tokens,
                    pos,
                    f"Expected 'fi' to close if statement, got '{tokens[pos].value}'",
                    terminator='fi',
                )

            pos += 1  # Skip 'fi'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=IfConditional(
                    condition=condition,
                    then_part=then_part,
                    elif_parts=elif_parts,
                    else_part=else_part,
                    redirects=redirects,
                ),
                position=pos
            )

        return Parser(parse_if_statement)

    def _build_case_statement(self) -> Parser[CaseConditional]:
        """Build parser for case/esac statements."""
        def parse_case_statement(tokens: List[Token], pos: int) -> ParseResult[CaseConditional]:
            """Parse case statement."""
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'case'):
                return ParseResult(success=False, error="Expected 'case'", position=pos)

            pos += 1  # Skip 'case'

            # Parse expression (usually a variable or word)
            _CASE_EXPR_TYPES = {
                'WORD', 'VARIABLE', 'STRING', 'COMMAND_SUB',
                'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION', 'PARAM_EXPANSION',
            }
            if pos >= len(tokens) or tokens[pos].type.name not in _CASE_EXPR_TYPES:
                raise_committed_error(tokens, pos, "Expected expression after 'case'")

            # Format the expression appropriately
            expr = format_token_value(tokens[pos])
            pos += 1

            # bash allows newlines between the subject and `in`
            while pos < len(tokens) and tokens[pos].type.name == 'NEWLINE':
                pos += 1

            # Expect 'in' (exactly one subject word before it; a second word
            # here fails the parse, matching bash's rejection of `case a b in`)
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'in'):
                raise_committed_error(tokens, pos, "Expected 'in' after case expression")

            pos += 1  # Skip 'in'

            # bash allows newlines (but not `;`) between `in` and the first
            # pattern or `esac`.  A `;` here is a syntax error
            # (`case x in ; esac`), but an empty case (`case x in esac`,
            # optionally with blank/comment lines) is valid.
            if pos < len(tokens) and tokens[pos].type.name == 'SEMICOLON':
                raise_committed_error(tokens, pos, "Expected pattern or 'esac' after 'in'")
            while pos < len(tokens) and tokens[pos].type.name == 'NEWLINE':
                pos += 1

            # Parse case items until 'esac'
            _CASE_PATTERN_TYPES = {
                'WORD', 'STRING', 'VARIABLE', 'PARAM_EXPANSION',
                'COMMAND_SUB', 'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION',
            }
            items = []
            while pos < len(tokens) and not matches_keyword(tokens[pos], 'esac'):
                # Parse pattern(s)
                patterns = []

                # Consume optional leading '('
                if pos < len(tokens) and tokens[pos].value == '(':
                    pos += 1

                # Parse first pattern
                pattern_str, pattern_tok, pos = _parse_case_pattern_value(tokens, pos, _CASE_PATTERN_TYPES)
                if pattern_str is None:
                    break

                patterns.append(self._make_case_pattern(pattern_str, pattern_tok))

                # Parse additional patterns separated by '|'
                while pos < len(tokens) and tokens[pos].value == '|':
                    pos += 1  # Skip '|'
                    pattern_str, pattern_tok, pos = _parse_case_pattern_value(tokens, pos, _CASE_PATTERN_TYPES)
                    if pattern_str is None:
                        raise_committed_error(tokens, pos, "Expected pattern after '|'")
                    patterns.append(self._make_case_pattern(pattern_str, pattern_tok))

                # Expect ')'
                if pos >= len(tokens) or tokens[pos].value != ')':
                    raise_committed_error(tokens, pos, "Expected ')' after case pattern(s)")

                pos += 1  # Skip ')'

                # Skip optional separator
                if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                    pos += 1

                # Parse commands by recursion up to (not consuming) a case
                # terminator (;; ;& ;;&) or 'esac'. A nested case statement is
                # parsed whole by self.statement and consumes its own 'esac', so
                # no manual nesting_depth bookkeeping is needed. An empty body
                # (e.g. ``a) ;;``) is allowed — build_statement_list returns an
                # empty list.
                body_result = self.commands.build_statement_list(
                    frozenset({'esac'}), _CASE_BODY_TERMINATOR_TYPES,
                ).parse(tokens, pos)
                if not body_result.success:
                    raise_committed_error(
                        tokens,
                        body_result.position,
                        body_result.error or "Failed to parse case commands",
                    )
                assert body_result.value is not None  # success implies a body
                commands = body_result.value
                pos = body_result.position

                # Get terminator
                terminator = ';;'  # Default
                if pos < len(tokens):
                    token_type = tokens[pos].type
                    token_terminator = CASE_TERMINATOR_TOKENS.get(token_type)
                    if token_terminator:
                        terminator = token_terminator
                        pos += 1

                # Skip optional separator after terminator
                if pos < len(tokens) and tokens[pos].type.name in ['SEMICOLON', 'NEWLINE']:
                    pos += 1

                # Create case item
                items.append(CaseItem(
                    patterns=patterns,
                    commands=commands,
                    terminator=terminator
                ))

            # Expect 'esac' (an empty case — `case x in esac` — is valid bash)
            if pos >= len(tokens) or not matches_keyword(tokens[pos], 'esac'):
                raise_committed_error(tokens, pos, "Expected 'esac' to close case statement",
                                      terminator='esac')

            pos += 1  # Skip 'esac'

            # Parse trailing redirections ('&' is handled at and-or level)
            redirects, pos = self._parse_trailing_redirects(tokens, pos)

            return ParseResult(
                success=True,
                value=CaseConditional(
                    expr=expr,
                    items=items,
                    redirects=redirects,
                ),
                position=pos
            )

        return Parser(parse_case_statement)
