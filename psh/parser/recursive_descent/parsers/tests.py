"""
Test expression parsing for PSH shell.

This module handles parsing of enhanced test expressions ([[ ... ]]).
"""

from typing import List

from ....ast_nodes import (
    BinaryTestExpression,
    CompoundTestExpression,
    EnhancedTestStatement,
    ExpansionPart,
    LiteralPart,
    NegatedTestExpression,
    TestExpression,
    UnaryTestExpression,
    Word,
    WordPart,
)
from ....lexer.token_types import TokenType
from ..helpers import TokenGroups
from ..support.word_builder import WordBuilder
from .base import ParserSubcomponent

#: Token types that are an embedded expansion rather than literal text.
#: In a [[ ]] operand each becomes its own ExpansionPart so the evaluator
#: can expand it and apply that part's quote context (an unquoted $x is a
#: live glob/regex, a quoted "$x" is literal).
_EXPANSION_TOKENS = frozenset({
    TokenType.VARIABLE,
    TokenType.PARAM_EXPANSION,
    TokenType.COMMAND_SUB,
    TokenType.COMMAND_SUB_BACKTICK,
    TokenType.ARITH_EXPANSION,
})


class TestParser(ParserSubcomponent):
    """Parser for test expression constructs."""


    def parse_enhanced_test_statement(self) -> EnhancedTestStatement:
        """Parse [[ ... ]] enhanced test statement."""
        self.parser.expect(TokenType.DOUBLE_LBRACKET)
        self.parser.ctx.push_construct('test')
        self.parser.skip_newlines()

        expression = self.parse_test_expression()

        self.parser.skip_newlines()
        self.parser.expect(TokenType.DOUBLE_RBRACKET)
        self.parser.ctx.pop_construct()

        redirects = self.parser.redirections.parse_redirects()

        return EnhancedTestStatement(expression, redirects)

    def parse_test_expression(self) -> TestExpression:
        """Parse a test expression with proper precedence."""
        return self.parse_test_or_expression()

    def parse_test_or_expression(self) -> TestExpression:
        """Parse test expression with || operator."""
        left = self.parse_test_and_expression()

        while self.parser.match(TokenType.OR_OR):
            self.parser.advance()
            self.parser.skip_newlines()
            right = self.parse_test_and_expression()
            left = CompoundTestExpression(left, '||', right)

        return left

    def parse_test_and_expression(self) -> TestExpression:
        """Parse test expression with && operator."""
        left = self.parse_test_unary_expression()

        while self.parser.match(TokenType.AND_AND):
            self.parser.advance()
            self.parser.skip_newlines()
            right = self.parse_test_unary_expression()
            left = CompoundTestExpression(left, '&&', right)

        return left

    def parse_test_unary_expression(self) -> TestExpression:
        """Parse unary test expression (possibly negated)."""
        if (self.parser.match(TokenType.EXCLAMATION) or
                (self.parser.match(TokenType.WORD) and self.parser.peek().value == '!')):
            self.parser.advance()
            self.parser.skip_newlines()
            expr = self.parse_test_unary_expression()
            return NegatedTestExpression(expr)

        return self.parse_test_primary_expression()

    def parse_test_primary_expression(self) -> TestExpression:
        """Parse primary test expression."""
        self.parser.skip_newlines()

        # Empty test
        if self.parser.match(TokenType.DOUBLE_RBRACKET):
            return UnaryTestExpression('-n', Word(parts=[]))

        # Parenthesized expression
        if self.parser.match(TokenType.LPAREN):
            self.parser.advance()
            expr = self.parse_test_expression()
            self.parser.expect(TokenType.RPAREN)
            return expr

        # Check for unary operators
        if self.parser.match(TokenType.WORD) and self._is_unary_test_operator(self.parser.peek().value):
            operator = self.parser.advance().value
            self.parser.skip_newlines()
            operand = self._parse_test_operand()
            return UnaryTestExpression(operator, operand)

        # Binary expression or single value
        left_word = self._parse_test_operand()
        self.parser.skip_newlines()

        # Check for binary operators
        if self.parser.match(TokenType.WORD, TokenType.REGEX_MATCH, TokenType.EQUAL, TokenType.NOT_EQUAL):
            token = self.parser.peek()
            if (token.type == TokenType.REGEX_MATCH or
                token.type == TokenType.EQUAL or
                token.type == TokenType.NOT_EQUAL or
                self._is_binary_test_operator(token.value)):

                # Map token types to operator strings
                if token.type == TokenType.EQUAL:
                    operator = '=='
                elif token.type == TokenType.NOT_EQUAL:
                    operator = '!='
                else:
                    operator = token.value

                self.parser.advance()
                self.parser.skip_newlines()

                # Special handling for regex patterns: the RHS is a single regex
                # word that may contain (, ), |, ?, etc., which the lexer split
                # into operator tokens. Reconstruct it from the adjacent run.
                if operator == '=~':
                    right_word = self._parse_regex_operand()
                else:
                    right_word = self._parse_test_operand()

                return BinaryTestExpression(
                    left_word=left_word,
                    operator=operator,
                    right_word=right_word,
                )

        # Single value test
        return UnaryTestExpression('-n', left_word)

    @staticmethod
    def _token_part(token) -> WordPart:
        """Build one WordPart from a [[ ]] operand token, preserving its
        own per-part quote context.

        An expansion token (``$x``, ``${...}``, ``$(...)``, ``$((...))``,
        `` `...` ``) becomes an ``ExpansionPart`` carrying the expansion AST
        node, so the evaluator's per-part pattern/regex builder can expand it
        and apply this part's quoting (an unquoted ``$x`` is a live glob/regex,
        a quoted ``"$x"`` is literal). Every other token becomes a
        ``LiteralPart`` with its own ``quoted``/``quote_char``. This is what
        lets ``ab"?"`` know the ``?`` is a quoted literal while ``ab`` is
        unquoted — a single flattened part could not."""
        quoted = bool(
            token.type == TokenType.STRING
            and getattr(token, 'quote_type', None))
        quote_char = token.quote_type if quoted else None
        if token.type in _EXPANSION_TOKENS:
            return ExpansionPart(
                WordBuilder.parse_expansion_token(token),
                quoted=quoted, quote_char=quote_char)
        return LiteralPart(token.value, quoted=quoted, quote_char=quote_char)

    def _parse_test_operand(self) -> Word:
        """Parse a test operand into a multi-part :class:`Word`.

        Each adjacent (glued) token becomes its own WordPart carrying its
        own quote context, so per-part quoting survives to the evaluator
        (``ab"?"`` -> unquoted ``ab`` + quoted ``?``). Bash's
        pattern-vs-literal decision is per-part, which a single quote-type
        sentinel could not represent.
        """
        if not self.parser.match_any(TokenGroups.WORD_LIKE):
            raise self.parser.error("Expected test operand")

        parts: List[WordPart] = [self._token_part(self.parser.advance())]

        # Concatenate immediately-adjacent word-like tokens (no whitespace),
        # stopping at operators / boundaries.
        while (self.parser.current < len(self.parser.tokens) and
               self.parser.match_any(TokenGroups.WORD_LIKE)):

            next_token = self.parser.peek()

            # Only concatenate truly adjacent tokens (no whitespace between them)
            if not getattr(next_token, 'adjacent_to_previous', False):
                break

            # Stop if next token is a binary test operator
            if (next_token.type == TokenType.WORD and
                self._is_binary_test_operator(next_token.value)) or \
               next_token.type in (TokenType.EQUAL, TokenType.NOT_EQUAL, TokenType.REGEX_MATCH):
                break

            # Stop at logical operators or closing brackets
            if next_token.type in (TokenType.AND_AND, TokenType.OR_OR,
                                 TokenType.DOUBLE_RBRACKET, TokenType.RPAREN):
                break

            parts.append(self._token_part(self.parser.advance()))

        return Word(parts=parts)

    def _parse_regex_operand(self) -> Word:
        """Collect the right-hand operand of `=~` as a multi-part Word.

        A regex is a single (whitespace-delimited) word, but it may contain
        characters the lexer tokenizes as operators — `(`, `)`, `|`, `?`, `[`,
        `]`, etc. Reconstruct it from the maximal run of adjacent tokens,
        stopping at unquoted whitespace (non-adjacent token) or a boundary
        (`]]`, `&&`, `||`). Each token keeps its own quote context so the
        evaluator can match a quoted sub-part literally (``a"."`` -> the
        ``.`` is a literal dot, bash).
        """
        if not self.parser.match_any(TokenGroups.WORD_LIKE) and \
                self.parser.peek().type in (TokenType.DOUBLE_RBRACKET,
                                            TokenType.AND_AND, TokenType.OR_OR):
            raise self.parser.error("Expected regex after =~")

        parts: List[WordPart] = []
        first = True
        stop = (TokenType.DOUBLE_RBRACKET, TokenType.AND_AND,
                TokenType.OR_OR, TokenType.EOF, TokenType.NEWLINE)
        while self.parser.current < len(self.parser.tokens):
            tok = self.parser.peek()
            if tok.type in stop:
                break
            # After the first token, only keep going while glued (no whitespace).
            if not first and not getattr(tok, 'adjacent_to_previous', False):
                break
            self.parser.advance()
            parts.append(self._token_part(tok))
            first = False

        return Word(parts=parts)

    def _is_unary_test_operator(self, value: str) -> bool:
        """Check if a word is a unary test operator."""
        return value in {
            '-a', '-b', '-c', '-d', '-e', '-f', '-g', '-h', '-k', '-p',
            '-r', '-s', '-t', '-u', '-w', '-x', '-G', '-L', '-N', '-O',
            '-S', '-z', '-n', '-o', '-v'
        }

    def _is_binary_test_operator(self, value: str) -> bool:
        """Check if a word is a binary test operator."""
        return value in {
            '=', '==', '!=', '<', '>', '-eq', '-ne', '-lt', '-le', '-gt', '-ge',
            '-nt', '-ot', '-ef'
        }
