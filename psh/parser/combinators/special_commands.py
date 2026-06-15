"""Special command parsers for the shell parser combinator.

This module provides parsers for specialized shell syntax including
arithmetic commands, enhanced test expressions, array operations,
and process substitutions.
"""

from typing import List, Optional, Union, cast

from ...ast_nodes import (
    # Special commands
    ArithmeticEvaluation,
    ArrayElementAssignment,
    ArrayInitialization,
    BinaryTestExpression,
    EnhancedTestStatement,
    LiteralPart,
    NegatedTestExpression,
    ProcessSubstitution,
    Redirect,
    # Test expressions
    TestExpression,
    UnaryTestExpression,
    Word,
    WordPart,
)
from ...lexer.token_types import Token
from ..config import ParserConfig
from .commands import CommandParsers
from .core import Parser, ParseResult
from .diagnostics import raise_committed_error
from .tokens import TokenParsers
from .utils import format_token_value


class SpecialCommandParsers:
    """Parsers for special shell syntax.

    This class provides parsers for specialized command forms:
    - Arithmetic commands ((expression))
    - Enhanced test expressions [[ condition ]]
    - Array initialization and assignment
    - Process substitution <(cmd) and >(cmd)
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

        # Array parsers
        self.array_initialization = self._build_array_initialization()
        self.array_element_assignment = self._build_array_element_assignment()
        self.array_assignment = self._build_array_assignment()

        # Process substitution parser
        self.process_substitution = self._build_process_substitution()

        # Combined special command parser
        self.special_command = (
            self.arithmetic_command
            .or_else(self.enhanced_test_statement)
            .or_else(self.process_substitution)
        )

    def _build_arithmetic_command(self) -> Parser[ArithmeticEvaluation]:
        """Build parser for arithmetic command ((expression)) syntax."""
        def parse_arithmetic_command(tokens: List[Token], pos: int) -> ParseResult[ArithmeticEvaluation]:
            """Parse arithmetic command."""
            # Check for opening ((
            if pos >= len(tokens):
                return ParseResult(success=False, error="Expected '((' for arithmetic command", position=pos)

            token = tokens[pos]
            if token.type.name != 'DOUBLE_LPAREN':
                return ParseResult(success=False, error=f"Expected '((', got {token.type.name}", position=pos)

            pos += 1  # Skip ((

            # Collect arithmetic expression until ))
            expr_tokens = []
            paren_depth = 0

            while pos < len(tokens):
                token = tokens[pos]

                # Check for closing ))
                if token.type.name == 'DOUBLE_RPAREN' and paren_depth == 0:
                    break
                elif token.type.name == 'LPAREN':
                    paren_depth += 1
                elif token.type.name == 'RPAREN':
                    paren_depth -= 1
                    if paren_depth < 0:
                        # Handle case of separate ) ) tokens
                        if (pos + 1 < len(tokens) and
                            tokens[pos + 1].type.name == 'RPAREN'):
                            # Found ) ) pattern, this ends the arithmetic command
                            pos += 1  # Skip second )
                            break
                        else:
                            return ParseResult(success=False,
                                             error="Unbalanced parentheses in arithmetic command",
                                             position=pos)

                expr_tokens.append(token)
                pos += 1

            if pos >= len(tokens):
                return ParseResult(success=False,
                                 error="Unterminated arithmetic command: expected '))'",
                                 position=pos)

            # Skip the closing )) token if we found DOUBLE_RPAREN
            if pos < len(tokens) and tokens[pos].type.name == 'DOUBLE_RPAREN':
                pos += 1

            # Build expression string from tokens, preserving variable syntax
            expression_parts = []
            for token in expr_tokens:
                if token.type.name == 'VARIABLE':
                    # Add $ prefix for variables
                    expression_parts.append(f'${token.value}')
                else:
                    expression_parts.append(token.value)

            # Join with spaces and clean up extra whitespace
            expression = ' '.join(expression_parts)
            # Normalize multiple spaces to single spaces
            import re
            expression = re.sub(r'\s+', ' ', expression).strip()

            # Parse optional redirections (not common but valid)
            redirects: List[Redirect] = []
            # For now, skip redirection parsing to keep it simple

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
        """Build parser for enhanced test statement [[ expression ]] syntax."""
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

            # Parse the test expression from collected tokens
            test_expr = self._parse_test_expression(expr_tokens)
            if test_expr is None:
                raise_committed_error(tokens, closing_pos, "Invalid test expression")

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
            operand = self._format_test_operand(tokens[1])

            # Support file test operators and string test operators
            if operator.startswith('-') and len(operator) == 2:
                return UnaryTestExpression(operator=operator, operand=operand)

        # Handle single operand (string test)
        if len(tokens) == 1:
            operand = self._format_test_operand(tokens[0])
            # Treat single operand as -n test (non-empty string test)
            return UnaryTestExpression(operator='-n', operand=operand)

        # For more complex expressions, return a simple binary test
        # This is simplified - full implementation would parse compound expressions
        if len(tokens) >= 3:
            left = self._format_test_operand(tokens[0])
            operator = tokens[1].value if len(tokens) > 1 else '=='
            right = ' '.join(self._format_test_operand(t) for t in tokens[2:])

            return BinaryTestExpression(
                left_word=self._operand_word(left),
                operator=operator,
                right_word=self._operand_word(right),
            )

        return None

    @staticmethod
    def _operand_word(text: str) -> Word:
        """Wrap a combinator test operand string in an unquoted Word.

        The combinator (educational-only parser) does not track operand
        quote context, so every operand is an unquoted single LiteralPart
        (``is_quoted`` is False) — combinator-built test operands are always
        treated as unquoted (glob/regex-active) patterns."""
        return Word(parts=[LiteralPart(text, quoted=False, quote_char=None)])

    def _operand_word_from_token(self, token: Token) -> Word:
        """Build a test operand Word from its source token."""
        return self.expansions.build_word_from_token(token)

    def _format_test_operand(self, token: Token) -> str:
        """Format a test operand token for proper shell representation.

        Args:
            token: Token to format

        Returns:
            Formatted string representation
        """
        if token.type.name == 'VARIABLE':
            # Add $ prefix back for variables
            return f'${token.value}'
        elif token.type.name == 'STRING':
            # For strings, use the content as-is
            return token.value
        else:
            # For other token types, use the value as-is
            return token.value

    def _build_array_initialization(self) -> Parser[ArrayInitialization]:
        """Build parser for array initialization: arr=(element1 element2) syntax."""
        def parse_array_initialization(tokens: List[Token], pos: int) -> ParseResult[ArrayInitialization]:
            """Parse array initialization."""
            # We expect to be called when we've already identified an array pattern
            # Pattern: WORD = ( elements ) or arr=( elements )

            if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
                return ParseResult(success=False, error="Expected array name", position=pos)

            word_token = tokens[pos]
            pos += 1

            # Handle case where arr= is combined in one token
            if word_token.value.endswith('=') or word_token.value.endswith('+='):
                is_append = word_token.value.endswith('+=')
                array_name = word_token.value[:-2] if is_append else word_token.value[:-1]
            else:
                # Handle separate tokens: arr = (
                array_name = word_token.value

                # Check for = or +=
                if pos >= len(tokens):
                    return ParseResult(success=False, error="Expected '=' after array name", position=pos)

                is_append = False
                if tokens[pos].type.name == 'WORD' and tokens[pos].value == '+=':
                    is_append = True
                    pos += 1
                elif tokens[pos].type.name == 'WORD' and tokens[pos].value == '=':
                    pos += 1
                else:
                    return ParseResult(success=False, error="Expected '=' or '+=' after array name", position=pos)

            # Check for opening parenthesis
            if pos >= len(tokens) or tokens[pos].type.name != 'LPAREN':
                return ParseResult(success=False, error="Expected '(' for array initialization", position=pos)

            pos += 1  # Skip (

            # Collect elements until closing parenthesis
            elements = []
            words = []

            while pos < len(tokens):
                token = tokens[pos]

                # Check for closing parenthesis
                if token.type.name == 'RPAREN':
                    break

                # Skip whitespace tokens
                if token.type.name in ['WHITESPACE', 'NEWLINE']:
                    pos += 1
                    continue

                # Collect element
                if token.type.name in ['WORD', 'STRING', 'VARIABLE', 'COMMAND_SUB',
                                      'COMMAND_SUB_BACKTICK', 'PARAM_EXPANSION',
                                      'ARITH_EXPANSION']:
                    # Format the element value
                    element_value = format_token_value(token)

                    elements.append(element_value)

                    # Build the Word AST node so the executor expands the
                    # element through the same pipeline as command arguments.
                    words.append(self.expansions.build_word_from_token(token))

                    pos += 1
                else:
                    return ParseResult(success=False,
                                     error=f"Unexpected token in array: {token.type.name}",
                                     position=pos)

            # Check that we found the closing parenthesis
            if pos >= len(tokens) or tokens[pos].type.name != 'RPAREN':
                return ParseResult(success=False,
                                 error="Expected ')' to close array initialization",
                                 position=pos)

            pos += 1  # Skip )

            return ParseResult(
                success=True,
                value=ArrayInitialization(
                    name=array_name,
                    elements=elements,
                    is_append=is_append,
                    words=words
                ),
                position=pos
            )

        return Parser(parse_array_initialization)

    #: Token types that can contribute parts to an element-assignment value
    _VALUE_WORD_TOKENS = frozenset({
        'WORD', 'STRING', 'VARIABLE', 'COMMAND_SUB', 'COMMAND_SUB_BACKTICK',
        'PARAM_EXPANSION', 'ARITH_EXPANSION'})

    def _collect_element_value_word(self, tokens: List[Token], pos: int,
                                    tail: str, consume_first: bool = False):
        """Collect an array element-assignment value as a Word.

        ``tail`` is literal value text from the same token as ``name[idx]=``.
        The lexer splits expansions and quoted segments into *adjacent*
        tokens; those are merged here into a single value Word. When
        ``consume_first`` is True the first word-like token is consumed
        even if not adjacent (``arr[0]=`` followed by a separate value).

        Returns (value_word, legacy_value, new_pos).
        """
        parts: List[WordPart] = []
        if tail:
            parts.append(LiteralPart(tail))
        allow_nonadjacent = not tail and consume_first
        while pos < len(tokens):
            token = tokens[pos]
            if token.type.name not in self._VALUE_WORD_TOKENS:
                break
            if not (allow_nonadjacent
                    or getattr(token, 'adjacent_to_previous', False)):
                break
            allow_nonadjacent = False
            parts.extend(self.expansions.build_word_from_token(token).parts)
            pos += 1
        word = Word(parts=parts)
        value = word.display_text()
        return word, value, pos

    def _build_array_element_assignment(self) -> Parser[ArrayElementAssignment]:
        """Build parser for array element assignment: arr[index]=value syntax."""
        def parse_array_element_assignment(tokens: List[Token], pos: int) -> ParseResult[ArrayElementAssignment]:
            """Parse array element assignment."""
            # Handle different patterns:
            # 1. All in one token: "arr[0]=value" or "arr[index]+=value"
            # 2. Separate tokens: "arr" "[" "0" "]" "=" "value"

            if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
                return ParseResult(success=False, error="Expected array name", position=pos)

            word_token = tokens[pos]
            pos += 1

            # Case 1: All in one token "arr[index]=value" (must have value after =)
            if ('[' in word_token.value and ']' in word_token.value and
                '=' in word_token.value and
                not (word_token.value.endswith('=') or word_token.value.endswith('+='))):
                # Parse the combined token
                value = word_token.value

                # Find the brackets
                lbracket_pos = value.index('[')
                rbracket_pos = value.index(']')

                # Find the equals (could be += or =)
                equals_pos = value.index('+=') if '+=' in value else value.index('=')
                is_append = '+=' in value

                # Extract parts
                array_name = value[:lbracket_pos]
                index_str = value[lbracket_pos + 1:rbracket_pos]
                if is_append:
                    tail = value[equals_pos + 2:]
                else:
                    tail = value[equals_pos + 1:]

                # Merge any adjacent continuation tokens into the value
                value_word, assigned_value, pos = \
                    self._collect_element_value_word(tokens, pos, tail)

                return ParseResult(
                    success=True,
                    value=ArrayElementAssignment(
                        name=array_name,
                        index=index_str,
                        value=assigned_value,
                        is_append=is_append,
                        value_word=value_word
                    ),
                    position=pos
                )

            # Case 1b: Pattern "arr[index]=" followed by separate value token
            elif ('[' in word_token.value and ']' in word_token.value and
                  (word_token.value.endswith('=') or word_token.value.endswith('+='))):
                # Parse the assignment token
                value = word_token.value

                # Find the brackets
                lbracket_pos = value.index('[')
                rbracket_pos = value.index(']')

                # Check for append assignment
                is_append = value.endswith('+=')

                # Extract parts
                array_name = value[:lbracket_pos]
                index_str = value[lbracket_pos + 1:rbracket_pos]

                # Get the value from the next token(s)
                if pos >= len(tokens):
                    return ParseResult(success=False, error="Expected value after array assignment", position=pos)

                value_word, assigned_value, pos = \
                    self._collect_element_value_word(tokens, pos, '',
                                                     consume_first=True)

                return ParseResult(
                    success=True,
                    value=ArrayElementAssignment(
                        name=array_name,
                        index=index_str,
                        value=assigned_value,
                        is_append=is_append,
                        value_word=value_word
                    ),
                    position=pos
                )

            # Case 2: Separate tokens
            else:
                array_name = word_token.value

                # Check for opening bracket
                if pos >= len(tokens) or tokens[pos].type.name != 'LBRACKET':
                    return ParseResult(success=False, error="Expected '[' for array index", position=pos)

                pos += 1  # Skip [

                # Collect index tokens until closing bracket
                index_tokens = []
                bracket_depth = 0

                while pos < len(tokens):
                    token = tokens[pos]

                    # Handle nested brackets
                    if token.type.name == 'LBRACKET':
                        bracket_depth += 1
                    elif token.type.name == 'RBRACKET':
                        if bracket_depth == 0:
                            break
                        else:
                            bracket_depth -= 1

                    index_tokens.append(token)
                    pos += 1

                # Check that we found the closing bracket
                if pos >= len(tokens) or tokens[pos].type.name != 'RBRACKET':
                    return ParseResult(success=False, error="Expected ']' to close array index", position=pos)

                pos += 1  # Skip ]

                # Build index string from tokens
                index_parts = []
                for token in index_tokens:
                    if token.type.name == 'VARIABLE':
                        index_parts.append(f'${token.value}')
                    else:
                        index_parts.append(token.value)

                index_str = ''.join(index_parts)

                # Check for = or +=
                if pos >= len(tokens):
                    return ParseResult(success=False, error="Expected '=' after array index", position=pos)

                is_append = False
                if tokens[pos].type.name == 'WORD' and tokens[pos].value == '+=':
                    is_append = True
                    pos += 1
                elif tokens[pos].type.name == 'WORD' and tokens[pos].value == '=':
                    pos += 1
                else:
                    return ParseResult(success=False, error="Expected '=' or '+=' after array index", position=pos)

                # Get the value
                if pos >= len(tokens):
                    return ParseResult(success=False, error="Expected value after '='", position=pos)

                value_word, value, pos = \
                    self._collect_element_value_word(tokens, pos, '',
                                                     consume_first=True)

                return ParseResult(
                    success=True,
                    value=ArrayElementAssignment(
                        name=array_name,
                        index=index_str,
                        value=value,
                        is_append=is_append,
                        value_word=value_word
                    ),
                    position=pos
                )

        return Parser(parse_array_element_assignment)

    def _detect_array_pattern(self, tokens: List[Token], pos: int) -> str:
        """Detect what type of array pattern we have at the current position.

        Args:
            tokens: List of tokens
            pos: Current position

        Returns:
            'initialization' for arr=(elements)
            'element_assignment' for arr[index]=value
            'none' if no array pattern detected
        """
        if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
            return 'none'

        word_token = tokens[pos]

        # Check for array element assignment patterns
        if '[' in word_token.value and ']' in word_token.value:
            # Check if this is all in one token: "arr[0]=value" or "arr[0]+=value"
            if '=' in word_token.value:
                equals_pos = word_token.value.index('+=') if '+=' in word_token.value else word_token.value.index('=')
                if word_token.value.index('[') < equals_pos:
                    return 'element_assignment'
            # Check for pattern: "arr[0]=" followed by value token
            elif word_token.value.endswith('=') or word_token.value.endswith('+='):
                if pos + 1 < len(tokens):  # Check if there's a value token after
                    return 'element_assignment'
            # Check for pattern: "arr[0]" followed by "=value"
            elif pos + 1 < len(tokens) and tokens[pos + 1].type.name == 'WORD':
                next_token = tokens[pos + 1]
                if next_token.value.startswith('=') or next_token.value.startswith('+='):
                    return 'element_assignment'

        # Check for array initialization patterns
        # Pattern 1: "arr=" followed by "("
        if (word_token.value.endswith('=') or word_token.value.endswith('+=')):
            if pos + 1 < len(tokens) and tokens[pos + 1].type.name == 'LPAREN':
                return 'initialization'

        # Pattern 2: "arr" followed by "=" followed by "("
        elif pos + 2 < len(tokens):
            if (tokens[pos + 1].type.name == 'WORD' and tokens[pos + 1].value in ['=', '+='] and
                tokens[pos + 2].type.name == 'LPAREN'):
                return 'initialization'

        # Check for standalone array element assignment: "arr" followed by "["
        if pos + 1 < len(tokens) and tokens[pos + 1].type.name == 'LBRACKET':
            return 'element_assignment'

        return 'none'

    def _build_array_assignment(self) -> Parser[Union[ArrayInitialization, ArrayElementAssignment]]:
        """Build parser for any array assignment pattern."""
        def parse_array_assignment(tokens: List[Token], pos: int) -> ParseResult[Union[ArrayInitialization, ArrayElementAssignment]]:
            """Parse array assignment."""
            # Detect which pattern we have
            pattern = self._detect_array_pattern(tokens, pos)

            ArrayResult = ParseResult[Union[ArrayInitialization, ArrayElementAssignment]]
            if pattern == 'initialization':
                return cast(ArrayResult, self._build_array_initialization().parse(tokens, pos))
            elif pattern == 'element_assignment':
                return cast(ArrayResult, self._build_array_element_assignment().parse(tokens, pos))
            else:
                return ParseResult(success=False, error="No array pattern detected", position=pos)

        return Parser(parse_array_assignment)

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
