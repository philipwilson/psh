"""Recursive-descent parser for shell arithmetic expressions."""

from typing import List, Tuple, cast

from .nodes import (
    ArithNode,
    ArrayAssignmentNode,
    ArrayElementNode,
    ArrayPostIncrementNode,
    ArrayPreIncrementNode,
    AssignmentNode,
    BinaryOpNode,
    NumberNode,
    PostIncrementNode,
    PreIncrementNode,
    TernaryNode,
    UnaryOpNode,
    VariableNode,
)
from .tokens import ArithToken, ArithTokenType


class ArithParser:
    """Recursive descent parser for arithmetic expressions"""

    # Simple and compound assignment operators (used for scalars and array
    # elements alike).
    _ASSIGNMENT_OPS = (
        ArithTokenType.ASSIGN, ArithTokenType.PLUS_ASSIGN,
        ArithTokenType.MINUS_ASSIGN, ArithTokenType.MULTIPLY_ASSIGN,
        ArithTokenType.DIVIDE_ASSIGN, ArithTokenType.MODULO_ASSIGN,
        ArithTokenType.LSHIFT_ASSIGN, ArithTokenType.RSHIFT_ASSIGN,
        ArithTokenType.BIT_AND_ASSIGN, ArithTokenType.BIT_OR_ASSIGN,
        ArithTokenType.BIT_XOR_ASSIGN,
    )

    def __init__(self, tokens: List[ArithToken], source: str = ""):
        self.tokens = tokens
        # The (already $-expanded) source expression text. Used to slice the
        # raw subscript of an array reference verbatim, so associative arrays
        # can use the literal subscript text as their key.
        self.source = source
        self.current = 0

    def peek(self) -> ArithToken:
        if self.current < len(self.tokens):
            return self.tokens[self.current]
        return self.tokens[-1]  # Return EOF

    def advance(self) -> ArithToken:
        token = self.peek()
        if self.current < len(self.tokens) - 1:
            self.current += 1
        return token

    def expect(self, token_type: ArithTokenType) -> ArithToken:
        token = self.peek()
        if token.type != token_type:
            raise SyntaxError(f"Expected {token_type.name}, got {token.type.name} at position {token.position}")
        return self.advance()

    def match(self, *token_types: ArithTokenType) -> bool:
        return self.peek().type in token_types

    def parse(self) -> ArithNode:
        """Parse the arithmetic expression"""
        if self.peek().type == ArithTokenType.EOF:
            # Empty expression evaluates to 0
            return NumberNode(0)

        expr = self.parse_comma()
        if self.peek().type != ArithTokenType.EOF:
            raise SyntaxError(f"Unexpected token after expression: {self.peek().value}")
        return expr

    def parse_comma(self) -> ArithNode:
        """Parse comma operator (lowest precedence)"""
        left = self.parse_ternary()

        while self.match(ArithTokenType.COMMA):
            self.advance()
            # In comma expressions, we evaluate left but return right
            right = self.parse_ternary()
            left = BinaryOpNode(ArithTokenType.COMMA, left, right)

        return left

    def parse_ternary(self) -> ArithNode:
        """Parse ternary conditional (?:)"""
        condition = self.parse_logical_or()

        if self.match(ArithTokenType.QUESTION):
            self.advance()
            true_expr = self.parse_ternary()
            self.expect(ArithTokenType.COLON)
            false_expr = self.parse_ternary()
            return TernaryNode(condition, true_expr, false_expr)

        return condition

    def parse_logical_or(self) -> ArithNode:
        """Parse logical OR (||)"""
        left = self.parse_logical_and()

        while self.match(ArithTokenType.OR):
            op = self.advance().type
            right = self.parse_logical_and()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_logical_and(self) -> ArithNode:
        """Parse logical AND (&&)"""
        left = self.parse_bitwise_or()

        while self.match(ArithTokenType.AND):
            op = self.advance().type
            right = self.parse_bitwise_or()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_bitwise_or(self) -> ArithNode:
        """Parse bitwise OR (|)"""
        left = self.parse_bitwise_xor()

        while self.match(ArithTokenType.BIT_OR):
            op = self.advance().type
            right = self.parse_bitwise_xor()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_bitwise_xor(self) -> ArithNode:
        """Parse bitwise XOR (^)"""
        left = self.parse_bitwise_and()

        while self.match(ArithTokenType.BIT_XOR):
            op = self.advance().type
            right = self.parse_bitwise_and()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_bitwise_and(self) -> ArithNode:
        """Parse bitwise AND (&)"""
        left = self.parse_equality()

        while self.match(ArithTokenType.BIT_AND):
            op = self.advance().type
            right = self.parse_equality()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_equality(self) -> ArithNode:
        """Parse equality operators (==, !=)"""
        left = self.parse_relational()

        while self.match(ArithTokenType.EQ, ArithTokenType.NE):
            op = self.advance().type
            right = self.parse_relational()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_relational(self) -> ArithNode:
        """Parse relational operators (<, >, <=, >=)"""
        left = self.parse_shift()

        while self.match(ArithTokenType.LT, ArithTokenType.GT,
                         ArithTokenType.LE, ArithTokenType.GE):
            op = self.advance().type
            right = self.parse_shift()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_shift(self) -> ArithNode:
        """Parse bit shift operators (<<, >>)"""
        left = self.parse_additive()

        while self.match(ArithTokenType.LSHIFT, ArithTokenType.RSHIFT):
            op = self.advance().type
            right = self.parse_additive()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_additive(self) -> ArithNode:
        """Parse addition and subtraction (+, -)"""
        left = self.parse_multiplicative()

        while self.match(ArithTokenType.PLUS, ArithTokenType.MINUS):
            op = self.advance().type
            right = self.parse_multiplicative()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_multiplicative(self) -> ArithNode:
        """Parse multiplication, division, and modulo (*, /, %)"""
        left = self.parse_power()

        while self.match(ArithTokenType.MULTIPLY, ArithTokenType.DIVIDE,
                         ArithTokenType.MODULO):
            op = self.advance().type
            right = self.parse_power()
            left = BinaryOpNode(op, left, right)

        return left

    def parse_power(self) -> ArithNode:
        """Parse exponentiation (**)"""
        left = self.parse_unary()

        # Right associative
        if self.match(ArithTokenType.POWER):
            op = self.advance().type
            right = self.parse_power()  # Right associative recursion
            return BinaryOpNode(op, left, right)

        return left

    def parse_unary(self) -> ArithNode:
        """Parse unary operators"""
        # Unary operators: +, -, !, ~, ++, --
        if self.match(ArithTokenType.PLUS, ArithTokenType.MINUS,
                     ArithTokenType.NOT, ArithTokenType.BIT_NOT):
            op = self.advance().type
            operand = self.parse_unary()
            return UnaryOpNode(op, operand)

        # Pre-increment/decrement
        if self.match(ArithTokenType.INCREMENT, ArithTokenType.DECREMENT):
            inc_op = self.advance()
            if not self.match(ArithTokenType.IDENTIFIER):
                raise SyntaxError(f"Expected identifier after {inc_op.value}")
            var_name = cast(str, self.advance().value)
            is_inc = inc_op.type == ArithTokenType.INCREMENT
            # Array-element lvalue: ++arr[i] / --arr[i]
            if self.match(ArithTokenType.LBRACKET):
                index, index_text = self._parse_subscript()
                return ArrayPreIncrementNode(var_name, index, is_inc, index_text)
            return PreIncrementNode(var_name, is_inc)

        return self.parse_postfix()

    def parse_postfix(self) -> ArithNode:
        """Parse postfix operators"""
        expr = self.parse_primary()

        # Post-increment/decrement
        if self.match(ArithTokenType.INCREMENT, ArithTokenType.DECREMENT):
            if isinstance(expr, VariableNode):
                op = self.advance()
                return PostIncrementNode(expr.name, op.type == ArithTokenType.INCREMENT)
            if isinstance(expr, ArrayElementNode):
                op = self.advance()
                return ArrayPostIncrementNode(
                    expr.name, expr.index,
                    op.type == ArithTokenType.INCREMENT, expr.index_text)

        return expr

    def _parse_subscript(self) -> Tuple[ArithNode, str]:
        """Parse ``[index]`` after an array name.

        Returns the parsed subscript expression (for indexed-array
        arithmetic) and the raw subscript source text (for associative-array
        literal keys). Assumes the next token is ``LBRACKET``.
        """
        lbracket = self.advance()  # consume '['
        index = self.parse_comma()  # Allow full expressions in the index
        rbracket = self.expect(ArithTokenType.RBRACKET)
        index_text = ""
        if self.source:
            index_text = self.source[lbracket.position + 1:rbracket.position].strip()
        return index, index_text

    def parse_primary(self) -> ArithNode:
        """Parse primary expressions"""
        # Numbers
        if self.match(ArithTokenType.NUMBER):
            return NumberNode(cast(int, self.advance().value))

        # Variables (possibly with assignment)
        if self.match(ArithTokenType.IDENTIFIER):
            var_token = self.advance()
            var_name = cast(str, var_token.value)

            # Array subscript: arr[index] (read or assignment target)
            if self.match(ArithTokenType.LBRACKET):
                index, index_text = self._parse_subscript()
                if self.match(*self._ASSIGNMENT_OPS):
                    op = self.advance().type
                    value = self.parse_ternary()
                    return ArrayAssignmentNode(var_name, index, op, value, index_text)
                return ArrayElementNode(var_name, index, index_text)

            # Check for assignment operators
            if self.match(*self._ASSIGNMENT_OPS):
                op = self.advance().type
                value = self.parse_ternary()  # Assignment is right-associative
                return AssignmentNode(var_name, op, value)

            return VariableNode(var_name)

        # Parenthesized expressions
        if self.match(ArithTokenType.LPAREN):
            self.advance()
            expr = self.parse_comma()  # Allow full expressions in parens
            self.expect(ArithTokenType.RPAREN)
            return expr

        raise SyntaxError(f"Unexpected token: {self.peek().value} at position {self.peek().position}")
