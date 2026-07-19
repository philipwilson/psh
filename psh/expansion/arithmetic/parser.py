"""Recursive-descent parser for shell arithmetic expressions."""

from typing import List, Optional, cast

from .nodes import (
    ArithNode,
    ArrayElementNode,
    AssignmentNode,
    BinaryOpNode,
    IncDecNode,
    LValue,
    NumberNode,
    TernaryNode,
    UnaryOpNode,
    VariableNode,
)
from .tokens import ArithToken, ArithTokenType


class ArithParser:
    """Recursive descent parser for arithmetic expressions"""

    # Maximum expression-NESTING depth. An EXPLICIT guard so a too-deep
    # expression fails deterministically with "expression too deeply nested".
    # It is carried by exactly the grammar rules that recurse DIRECTLY (not via
    # the iterative while-loop precedence levels): parse_ternary (parentheses
    # re-enter through parse_comma, and ternary arms), parse_unary (unary-
    # operator chains), and parse_power (right-associative `**` chains). Those
    # are the parse-side stack-growth paths; a flat operator chain like
    # `0+1+1+...` is instead built ITERATIVELY here (no parser recursion) and
    # its EVALUATION-side depth is bounded separately by
    # ArithmeticEvaluator.MAX_EVAL_DEPTH.
    #
    # Each SINGLE arithmetic recursion path — parse nesting, `**` chains,
    # evaluation width, and the get_variable -> evaluate_arithmetic re-entry
    # count (evaluator._MAX_ARITH_RECURSION) — is bounded by one of these
    # guards, so a RecursionError from arithmetic ordinarily means the
    # SURROUNDING shell exhausted the interpreter stack (e.g. runaway function
    # recursion whose deepest frame merely happened to be in arithmetic); it
    # is NOT relabeled as an arithmetic error and propagates to the
    # function-call boundary, which reports "maximum function nesting level
    # exceeded" (executor/function.py). Caveat: the guards bound each path
    # SEPARATELY, not their PRODUCT — a pathological composite value chain
    # (each variable in a long chain holding a wide expression that references
    # the next, stacking a per-level evaluation depth under every re-entry
    # level) can still exhaust the interpreter stack from pure arithmetic
    # (probe: 60-level chain x ~600-term values; r19-T9 deferred ledger).
    # 1024 levels * ~15 frames per level stays comfortably inside the
    # interpreter limit raised by psh.shell.RECURSION_LIMIT (40,000).
    MAX_DEPTH = 1024

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

    def __init__(self, tokens: List[ArithToken]):
        self.tokens = tokens
        self.current = 0
        # Current expression-nesting depth; see MAX_DEPTH.
        self._depth = 0

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
        """Parse ternary conditional (?:)

        The MIDDLE operand is a full comma-level expression, as in C and
        bash (``$((1?2,3:4))`` is 3, ``$((1?(a=1),(b=2):3))`` runs both
        assignments): between ``?`` and ``:`` there is no ambiguity, so
        the grammar there restarts at the lowest precedence. The FALSE
        operand stays at ternary level — a following comma belongs to the
        enclosing expression (``$((0?1:2,3))`` is ``(0?1:2),3`` = 3).

        Carries the nesting-depth guard: every nested descent of the
        grammar except unary-operator chains re-enters here (parenthesized
        sub-expressions via parse_comma, ternary arms). parse_unary guards
        its own self-recursion with the same counter.
        """
        self._depth += 1
        try:
            if self._depth > self.MAX_DEPTH:
                raise SyntaxError("expression too deeply nested")

            condition = self.parse_logical_or()

            if self.match(ArithTokenType.QUESTION):
                self.advance()
                true_expr = self.parse_comma()
                self.expect(ArithTokenType.COLON)
                false_expr = self.parse_ternary()
                return TernaryNode(condition, true_expr, false_expr)

            return condition
        finally:
            self._depth -= 1

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

        # Right associative. A `**` chain recurses here directly (like the
        # unary chain in parse_unary), bypassing parse_ternary, so it carries
        # its own copy of the depth guard — otherwise a long `1**1**...` chain
        # would overflow the Python stack with a raw RecursionError.
        if self.match(ArithTokenType.POWER):
            op = self.advance().type
            self._depth += 1
            try:
                if self._depth > self.MAX_DEPTH:
                    raise SyntaxError("expression too deeply nested")
                right = self.parse_power()  # Right-associative recursion
            finally:
                self._depth -= 1
            return BinaryOpNode(op, left, right)

        return left

    def parse_unary(self) -> ArithNode:
        """Parse unary operators"""
        # Unary operators: +, -, !, ~, ++, --
        # A chain (`----x`, `!!!!x`) recurses here directly without passing
        # parse_ternary, so it needs its own depth guard.
        if self.match(ArithTokenType.PLUS, ArithTokenType.MINUS,
                     ArithTokenType.NOT, ArithTokenType.BIT_NOT):
            op = self.advance().type
            self._depth += 1
            try:
                if self._depth > self.MAX_DEPTH:
                    raise SyntaxError("expression too deeply nested")
                operand = self.parse_unary()
            finally:
                self._depth -= 1
            return UnaryOpNode(op, operand)

        # Pre-increment/decrement of an lvalue (++x, --x, ++a[i], --a[i]).
        if self.match(ArithTokenType.INCREMENT, ArithTokenType.DECREMENT):
            inc_op = self.advance()
            if not self.match(ArithTokenType.IDENTIFIER):
                raise SyntaxError(f"Expected identifier after {inc_op.value}")
            lvalue = self._parse_lvalue(cast(str, self.advance().value))
            return IncDecNode(lvalue, inc_op.type, prefix=True)

        return self.parse_postfix()

    def parse_postfix(self) -> ArithNode:
        """Parse postfix operators"""
        expr = self.parse_primary()

        # Post-increment/decrement of an lvalue (x++, x--, a[i]++, a[i]--).
        if self.match(ArithTokenType.INCREMENT, ArithTokenType.DECREMENT):
            lvalue = self._read_as_lvalue(expr)
            if lvalue is not None:
                op = self.advance()
                return IncDecNode(lvalue, op.type, prefix=False)

        return expr

    @staticmethod
    def _read_as_lvalue(node: ArithNode) -> Optional[LValue]:
        """The lvalue a read node denotes (for a following postfix ++/--), or
        ``None`` if the node is not an assignable scalar/array-element."""
        if isinstance(node, VariableNode):
            return LValue(node.name)
        if isinstance(node, ArrayElementNode):
            return LValue(node.name, node.index_text)
        return None

    def _parse_lvalue(self, name: str) -> LValue:
        """Build the lvalue for ``name`` after its IDENTIFIER is consumed,
        taking an optional SUBSCRIPT token (scalar vs array element).

        The tokenizer captured the subscript VERBATIM (``_read_subscript``);
        it is never parsed as arithmetic here. Interpretation happens at
        evaluation, by target kind (the W2 subscript authority) — which is
        what lets ``$((h[a b]))`` key ``a b`` for an associative ``h`` and
        keeps indexed subscript arithmetic lazy.
        """
        if self.match(ArithTokenType.SUBSCRIPT):
            token = self.advance()
            return LValue(name, cast(str, token.value))
        return LValue(name)

    def parse_primary(self) -> ArithNode:
        """Parse primary expressions"""
        # Numbers
        if self.match(ArithTokenType.NUMBER):
            return NumberNode(cast(int, self.advance().value))

        # Variables: a read (scalar or array element) or an assignment target.
        # One lvalue captures the scalar-vs-array distinction; the assignment
        # check and the read fall out of it without a per-shape fork.
        if self.match(ArithTokenType.IDENTIFIER):
            lvalue = self._parse_lvalue(cast(str, self.advance().value))

            if self.match(*self._ASSIGNMENT_OPS):
                op = self.advance().type
                value = self.parse_ternary()  # Assignment is right-associative
                return AssignmentNode(lvalue, op, value)

            # Plain read.
            if lvalue.subscript_text is None:
                return VariableNode(lvalue.name)
            return ArrayElementNode(lvalue.name, lvalue.subscript_text)

        # Parenthesized expressions
        if self.match(ArithTokenType.LPAREN):
            self.advance()
            expr = self.parse_comma()  # Allow full expressions in parens
            self.expect(ArithTokenType.RPAREN)
            return expr

        raise SyntaxError(f"Unexpected token: {self.peek().value} at position {self.peek().position}")
