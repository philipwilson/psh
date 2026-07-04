"""Special command parsers for the shell parser combinator.

This module provides parsers for specialized shell syntax including
arithmetic commands, enhanced test expressions, and process
substitutions. (Array assignment/initialization parsing lives in
``arrays.py`` / ``ArrayParsers``, used by the live command path.)
"""

from typing import List, Optional

from ...ast_nodes import (
    # Special commands
    ArithmeticEvaluation,
    BinaryTestExpression,
    EnhancedTestStatement,
    NegatedTestExpression,
    ProcessSubstitution,
    Redirect,
    # Test expressions
    TestExpression,
    UnaryTestExpression,
    Word,
)
from ...lexer.token_stream import TokenStream
from ...lexer.token_types import Token
from ..config import ParserConfig
from .commands import CommandParsers
from .core import Parser, ParseResult
from .diagnostics import raise_committed_error
from .tokens import TokenParsers


class SpecialCommandParsers:
    """Parsers for special shell syntax.

    This class provides parsers for specialized command forms:
    - Arithmetic commands ((expression))
    - Enhanced test expressions [[ condition ]]
    - Process substitution <(cmd) and >(cmd)

    (Array assignment/initialization parsing lives in ``ArrayParsers``.)

    Educational-scope boundary (intentional, not a defect): ``(( ))`` and
    ``[[ ]]`` are recognised structurally but their *inner* grammars are shallow
    — the arithmetic expression is captured as a token string for the runtime
    evaluator rather than parsed into an AST, and the ``[[ ]]`` parser handles
    negation and simple unary/binary/single-operand tests but not boolean
    compounds (``&&``/``||``), parenthesised grouping, per-operand quote context,
    or trailing redirections. The recursive descent parser
    (``recursive_descent/parsers/arithmetic.py`` and ``tests.py``) is the full
    implementation; this parser deliberately stops at the level the differential
    parity corpus exercises. See the individual ``_build_*`` methods for the
    per-construct limits.
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 token_parsers: Optional[TokenParsers] = None,
                 command_parsers: Optional[CommandParsers] = None):
        """Initialize special command parsers.

        Args:
            config: Parser configuration
            token_parsers: Token parsers to use
            command_parsers: Command parsers for nested commands
        """
        self.config = config or ParserConfig()
        self.tokens = token_parsers or TokenParsers()
        self.commands = command_parsers  # May be None initially

        # Word AST builder for array initializer elements (shares the same
        # token→Word logic command arguments use).
        from .expansions import create_expansion_parsers
        self.expansions = create_expansion_parsers(self.config)

        self._initialize_parsers()

    def set_command_parsers(self, command_parsers: CommandParsers):
        """Set command parsers after initialization.

        This breaks the circular dependency between command and special parsers.

        Args:
            command_parsers: Command parsers to use
        """
        self.commands = command_parsers

    def _initialize_parsers(self):
        """Initialize all special command parsers."""
        # Arithmetic command parser
        self.arithmetic_command = self._build_arithmetic_command()

        # Enhanced test expression parser
        self.enhanced_test_statement = self._build_enhanced_test_statement()

        # Process substitution parser
        self.process_substitution = self._build_process_substitution()

        # Combined special command parser
        self.special_command = (
            self.arithmetic_command
            .or_else(self.enhanced_test_statement)
            .or_else(self.process_substitution)
        )

    def _build_arithmetic_command(self) -> Parser[ArithmeticEvaluation]:
        """Build parser for arithmetic command ((expression)) syntax.

        Educational-scope boundary: the expression between ``((`` and ``))`` is
        captured as a normalized token string and handed to the arithmetic
        evaluator at run time (the combinator does not build an arithmetic AST),
        and trailing redirections (``((i++)) >log``, valid but rare) are NOT
        parsed — see :meth:`parse_arithmetic_command`. The recursive descent
        parser (``recursive_descent/parsers/arithmetic.py``) is the full
        implementation; this parser deliberately stops at the level the parity
        corpus exercises.
        """
        def parse_arithmetic_command(tokens: List[Token], pos: int) -> ParseResult[ArithmeticEvaluation]:
            """Parse arithmetic command."""
            # Check for opening ((
            if pos >= len(tokens):
                return ParseResult(success=False, error="Expected '((' for arithmetic command", position=pos)

            token = tokens[pos]
            if token.type.name != 'DOUBLE_LPAREN':
                return ParseResult(success=False, error=f"Expected '((', got {token.type.name}", position=pos)

            pos += 1  # Skip ((

            # Collect the expression through the shared depth-tracked collector
            # (``psh/lexer/token_stream.py``) — the same routine the recursive
            # descent parser uses (``_parse_arithmetic_expression_until_double_rparen``),
            # so both parsers normalize identically and handle nested/fused parens
            # (``(( ((1+2)) == 3 ))``) the same way.
            stream = TokenStream(tokens, pos)
            _t, expression = stream.collect_arithmetic_expression(
                stop_at_semicolon=False, transform_redirects=False)
            pos = stream.pos

            # Consume the closing )) (a single DOUBLE_RPAREN, or two RPARENs left
            # when a straddling )) was split by the collector).
            if pos < len(tokens) and tokens[pos].type.name == 'DOUBLE_RPAREN':
                pos += 1
            elif (pos + 1 < len(tokens) and tokens[pos].type.name == 'RPAREN'
                  and tokens[pos + 1].type.name == 'RPAREN'):
                pos += 2
            else:
                return ParseResult(success=False,
                                 error="Unterminated arithmetic command: expected '))'",
                                 position=pos)

            # Educational-scope boundary: trailing redirections on an arithmetic
            # command (``((i++)) >log`` — valid but rare) are intentionally not
            # parsed here. The recursive descent parser handles them; this stays
            # at the level the parity corpus covers.
            redirects: List[Redirect] = []

            return ParseResult(
                success=True,
                value=ArithmeticEvaluation(
                    expression=expression,
                    redirects=redirects,
                    background=False
                ),
                position=pos
            )

        return Parser(parse_arithmetic_command)

    def _build_enhanced_test_statement(self) -> Parser[EnhancedTestStatement]:
        """Build parser for enhanced test statement ``[[ expression ]]`` syntax.

        Educational-scope boundary: the tokens between ``[[`` and ``]]`` are
        collected and handed to :meth:`_parse_test_expression`, which recognises
        negation and simple unary/binary/single-operand tests but does NOT model
        the full ``[[ ]]`` grammar — boolean compounds (``&&``/``||``),
        parenthesised grouping, multi-token ``=~`` regexes, and per-operand
        quote context are not built (see :meth:`_parse_test_expression`). Those
        unmodelled forms are REJECTED with a committed parse error (exit 2)
        rather than flattened into a silently-wrong test. The recursive descent
        parser (``recursive_descent/parsers/tests.py``) is the full
        implementation; this parser deliberately stops at the level the parity
        corpus exercises. Trailing redirections after ``]]`` are likewise not
        parsed.
        """
        def parse_enhanced_test(tokens: List[Token], pos: int) -> ParseResult[EnhancedTestStatement]:
            """Parse enhanced test expression."""
            # Check for opening [[
            if pos >= len(tokens):
                return ParseResult(success=False, error="Expected '[[' for enhanced test", position=pos)

            token = tokens[pos]
            if token.type.name != 'DOUBLE_LBRACKET':
                return ParseResult(success=False, error=f"Expected '[[', got {token.type.name}", position=pos)

            pos += 1  # Skip [[

            # Collect test expression tokens until ]]
            expr_tokens = []
            bracket_depth = 0

            while pos < len(tokens):
                token = tokens[pos]
                if token.type.name == 'DOUBLE_RBRACKET' and bracket_depth == 0:
                    break
                elif token.type.name == 'DOUBLE_LBRACKET':
                    bracket_depth += 1
                elif token.type.name == 'DOUBLE_RBRACKET':
                    bracket_depth -= 1

                expr_tokens.append(token)
                pos += 1

            # Check for closing ]]
            if pos >= len(tokens) or tokens[pos].type.name != 'DOUBLE_RBRACKET':
                raise_committed_error(tokens, pos, "Expected ']]' to close enhanced test")

            closing_pos = pos
            pos += 1  # Skip ]]

            # Parse the test expression from collected tokens. Compound/grouping/
            # regex-parens forms return None here and are rejected cleanly (a
            # committed parse error → exit 2), never flattened into a wrong test.
            test_expr = self._parse_test_expression(expr_tokens)
            if test_expr is None:
                raise_committed_error(
                    tokens, closing_pos,
                    "[[ ]] expression not supported by the combinator parser "
                    "(boolean compounds '&&'/'||', grouping, or =~ regex with "
                    "parens are educational-scope gaps; use the recursive "
                    "descent parser)",
                )

            return ParseResult(
                success=True,
                value=EnhancedTestStatement(expression=test_expr, redirects=[]),
                position=pos
            )

        return Parser(parse_enhanced_test)

    def _parse_test_expression(self, tokens: List[Token]) -> Optional[TestExpression]:
        """Parse test expression from a list of tokens.

        Args:
            tokens: List of tokens representing the test expression

        Returns:
            Parsed TestExpression or None if invalid
        """
        if not tokens:
            return None

        # Handle negation
        if tokens[0].value == '!':
            expr = self._parse_test_expression(tokens[1:])
            if expr:
                return NegatedTestExpression(expression=expr)
            return None

        # Handle simple binary operations: operand operator operand
        if len(tokens) == 3:
            operator = tokens[1].value

            # Support basic operators
            if operator in ['==', '!=', '=', '<', '>', '=~',
                          '-eq', '-ne', '-lt', '-le', '-gt', '-ge']:
                return BinaryTestExpression(
                    left_word=self._operand_word_from_token(tokens[0]),
                    operator=operator,
                    right_word=self._operand_word_from_token(tokens[2]),
                )

        # Handle unary operations: operator operand
        if len(tokens) == 2:
            operator = tokens[0].value

            # Support file test operators and string test operators
            if operator.startswith('-') and len(operator) == 2:
                return UnaryTestExpression(
                    operator=operator,
                    operand_word=self._operand_word_from_token(tokens[1]))

        # Handle single operand (string test)
        if len(tokens) == 1:
            # Treat single operand as -n test (non-empty string test)
            return UnaryTestExpression(
                operator='-n',
                operand_word=self._operand_word_from_token(tokens[0]))

        # Educational-scope boundary: anything longer/more complex than the
        # forms above — boolean compounds (``a == b && c == d``, ``||``),
        # parenthesised grouping (``( ... )``), and multi-token ``=~`` regexes
        # (``(a|b)c``) — is NOT modelled by this parser. Return None so the
        # caller rejects the whole ``[[ ]]`` with a committed parse error
        # (exit 2) rather than flattening it into a loose, silently-wrong binary
        # test. The recursive descent parser
        # (``recursive_descent/parsers/tests.py``) builds the real compound AST.
        return None

    def _operand_word_from_token(self, token: Token) -> Word:
        """Build a test operand Word from its source token."""
        return self.expansions.build_word_from_token(token)

    def _build_process_substitution(self) -> Parser[ProcessSubstitution]:
        """Build parser for process substitution <(cmd) and >(cmd) syntax."""
        def parse_process_substitution(tokens: List[Token], pos: int) -> ParseResult[ProcessSubstitution]:
            """Parse process substitution."""
            if pos >= len(tokens):
                return ParseResult(success=False, error="Expected process substitution", position=pos)

            token = tokens[pos]
            if token.type.name == 'PROCESS_SUB_IN':
                direction = 'in'
            elif token.type.name == 'PROCESS_SUB_OUT':
                direction = 'out'
            else:
                return ParseResult(success=False,
                                 error=f"Expected process substitution, got {token.type.name}",
                                 position=pos)

            # Extract command from token value
            # Token value format: "<(command)" or ">(command)"
            token_value = token.value
            if len(token_value) >= 3 and token_value.startswith(('<(', '>(')):
                if token_value.endswith(')'):
                    # Complete process substitution
                    command = token_value[2:-1]  # Remove <( or >( and trailing )
                else:
                    # Incomplete process substitution (missing closing paren)
                    command = token_value[2:]  # Remove <( or >(
            else:
                return ParseResult(success=False,
                                 error=f"Invalid process substitution format: {token_value}",
                                 position=pos)

            return ParseResult(
                success=True,
                value=ProcessSubstitution(direction=direction, command=command),
                position=pos + 1
            )

        return Parser(parse_process_substitution)



# Convenience functions

def create_special_command_parsers(config: Optional[ParserConfig] = None,
                                  token_parsers: Optional[TokenParsers] = None,
                                  command_parsers: Optional[CommandParsers] = None) -> SpecialCommandParsers:
    """Create and return a SpecialCommandParsers instance.

    Args:
        config: Optional parser configuration
        token_parsers: Optional token parsers
        command_parsers: Optional command parsers

    Returns:
        Initialized SpecialCommandParsers object
    """
    return SpecialCommandParsers(config, token_parsers, command_parsers)
