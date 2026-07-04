"""Evaluator for shell arithmetic AST nodes, plus the public entry points."""

import re
from typing import Optional, Union

from .errors import ShellArithmeticError, _to_signed64
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
from .parser import ArithParser
from .tokenizer import ArithTokenizer
from .tokens import ArithTokenType

# A plain (optionally signed) decimal integer with no leading-zero octal
# ambiguity. Values matching this are safe to parse with int(); anything else
# (0x.., 0.., base#n, "2*3", ...) is evaluated as an arithmetic sub-expression.
_PLAIN_DECIMAL_RE = re.compile(r'[+-]?(?:0|[1-9][0-9]*)$')


def _trunc_div(left: int, right: int) -> int:
    """C-style integer division: truncate toward zero (Python's ``//``
    floors, and ``int(left/right)`` loses precision beyond 2**53)."""
    quotient = left // right
    if quotient < 0 and quotient * right != left:
        quotient += 1
    return quotient


class ArithmeticEvaluator:
    """Evaluate arithmetic AST nodes"""

    def __init__(self, shell):
        self.shell = shell

    def get_variable(self, name: str) -> int:
        """Get variable value, converting to integer.

        Matches bash, which recursively evaluates a variable's value as an
        arithmetic expression: ``a=b; b=42; $((a))`` is 42, ``a="2*3"; $((a))``
        is 6, and base-prefixed values (``0x10``, ``010``, ``2#101``) are
        honoured. A cycle guard / recursion limit prevents infinite loops from
        circular references.
        """
        from ...core import OptionHandler
        seen: set = set()
        var = name
        while True:
            # set -u: a reference to an unset variable inside arithmetic is an
            # error (bash), not a silent 0 — same as a plain `$var` reference.
            # Applied at each step of the reference chain (`a=b` with b unset).
            OptionHandler.check_unset_variable(self.shell.state, var)
            value = self.shell.state.get_variable(var, '0')

            if not value:
                return 0
            value = value.strip()
            if not value:
                return 0

            # Fast path: a plain signed decimal (no leading-zero octal trap).
            # A literal value wraps to signed 64-bit exactly like an operation
            # result (bash: `x=9223372036854775808; echo $((x))` is negative).
            if _PLAIN_DECIMAL_RE.match(value):
                return _to_signed64(int(value))

            # Bare identifier: follow the reference chain with a cycle guard.
            if value.isidentifier() and not value.startswith('_' * 2):
                if value in seen:
                    raise ShellArithmeticError(
                        f"{value}: expression recursion level exceeded")
                seen.add(var)
                var = value
                continue

            # Otherwise evaluate the value as an arithmetic sub-expression.
            # Handles 0x.., 0.. (octal), base#n, and full expressions such as
            # "2*3" or "a+1". Recursion is bounded by evaluate_arithmetic.
            return evaluate_arithmetic(value, self.shell)

    def set_variable(self, name: str, value: int) -> None:
        """Set variable value"""
        from ...core import NamerefCycleError
        # Use state's set_variable which handles scopes
        # When in a function and assigning to a local variable,
        # this should update the local, not create a new global
        try:
            self.shell.state.set_variable(name, str(value))
        except NamerefCycleError as e:
            # bash: a cyclic-nameref WRITE inside arithmetic only warns and
            # drops the assignment — evaluation continues and the expression
            # keeps its value (`(( na=5 ))` is status 0). A readonly failure,
            # by contrast, propagates and aborts the evaluation (bash:
            # `(( r=9, x=1 ))` leaves x unset).
            self.shell.state.scope_manager.warn_nameref_cycle(e.name)

    def _string_to_int(self, value: Optional[str]) -> int:
        """Convert a stored string value to an integer like get_variable()."""
        value = (value or '').strip()
        if not value:
            return 0
        if _PLAIN_DECIMAL_RE.match(value):
            return _to_signed64(int(value))
        return evaluate_arithmetic(value, self.shell)

    def _array_key(self, name: str, index_node: ArithNode, index_text: str) -> Union[int, str]:
        """Resolve the subscript of an array reference to its lookup key.

        For an associative array the subscript is the LITERAL text used
        directly as the key (bash: bare identifiers are not variable
        references). For everything else (indexed arrays, scalars, or a
        not-yet-created array) the subscript is arithmetic-evaluated to an
        int.
        """
        from ...core import AssociativeArray
        var = self.shell.state.scope_manager.get_variable_object(name)
        if var is not None and isinstance(var.value, AssociativeArray):
            return index_text
        return self.evaluate(index_node)

    def get_array_element(self, name: str, key: Union[int, str]) -> int:
        """Read an array element (or scalar via index 0) as an integer.

        ``key`` is a str for associative arrays and an int for indexed
        arrays / scalars (see :meth:`_array_key`).
        """
        from ...core import AssociativeArray, IndexedArray, OptionHandler
        var = self.shell.state.scope_manager.get_variable_object(name)
        if var is None:
            # set -u: an unset array/scalar referenced here is an error (bash).
            OptionHandler.check_unset_variable(self.shell.state, name)
            return 0
        value = var.value
        if isinstance(value, IndexedArray):
            return self._string_to_int(value.get(int(key)))
        if isinstance(value, AssociativeArray):
            return self._string_to_int(value.get(str(key)))
        # Scalar variable: index 0 refers to the value, any other index is unset.
        return self._string_to_int(str(value)) if key == 0 else 0

    def set_array_element(self, name: str, key: Union[int, str], value: int) -> None:
        """Assign to an array element, creating the array if necessary.

        ``key`` is a str for associative arrays and an int for indexed
        arrays / a freshly created indexed array.
        """
        from ...core import (
            ArraySubscriptError,
            AssociativeArray,
            IndexedArray,
            NamerefCycleError,
            ReadonlyVariableError,
            VarAttributes,
        )
        from .errors import ShellArithmeticError
        var = self.shell.state.scope_manager.get_variable_object(name)
        # A readonly array (or scalar) forbids element writes exactly like
        # the SimpleCommand `a[0]=9` path (executor/array.py): bash reports
        # "a: readonly variable", the evaluation aborts with status 1, and
        # the value is unchanged. Without this, `readonly -a a=(1 2);
        # (( a[0]=9 ))` was a silent write. The nameref/creation fallthrough
        # below is covered too: scope_manager.set_variable re-checks.
        if var is not None and var.is_readonly:
            raise ReadonlyVariableError(name)
        try:
            if var is not None and isinstance(var.value, IndexedArray):
                var.value.set(int(key), str(value))
            elif var is not None and isinstance(var.value, AssociativeArray):
                var.value.set(str(key), str(value))
            else:
                # No array yet (and not a plain scalar to clobber as scalar):
                # create an indexed array, matching `arr[i]=` semantics.
                arr = IndexedArray()
                arr.set(int(key), str(value))
                self.shell.state.scope_manager.set_variable(
                    name, arr, attributes=VarAttributes.ARRAY,
                )
        except ArraySubscriptError as e:
            # Surface as an arithmetic error so `(( ))` reports it like bash
            # ("NAME[SUB]: bad array subscript") rather than as an internal
            # defect under strict-errors.
            raise ShellArithmeticError(f"{name}[{e.subscript}]: {e}") from e
        except NamerefCycleError as e:
            # Cyclic-nameref write through the creation/nameref fallthrough:
            # warn and drop the assignment, like set_variable() above
            # (bash: `(( na[0]=5 ))` warns, status from the value).
            self.shell.state.scope_manager.warn_nameref_cycle(e.name)

    def _eval_array_assignment(self, node: 'ArrayAssignmentNode') -> int:
        key = self._array_key(node.name, node.index, node.index_text)
        value = self.evaluate(node.value)

        if node.op == ArithTokenType.ASSIGN:
            self.set_array_element(node.name, key, value)
            return value

        base_op = self._COMPOUND_TO_BASE.get(node.op)
        if base_op is None:
            raise ValueError(f"Unknown assignment operator: {node.op}")
        current = self.get_array_element(node.name, key)
        result = self._apply_binary_op(base_op, current, value)
        self.set_array_element(node.name, key, result)
        return result

    def _eval_array_pre_increment(self, node: 'ArrayPreIncrementNode') -> int:
        key = self._array_key(node.name, node.index, node.index_text)
        current = self.get_array_element(node.name, key)
        new_value = _to_signed64(current + 1 if node.is_increment else current - 1)
        self.set_array_element(node.name, key, new_value)
        return new_value

    def _eval_array_post_increment(self, node: 'ArrayPostIncrementNode') -> int:
        key = self._array_key(node.name, node.index, node.index_text)
        current = self.get_array_element(node.name, key)
        new_value = _to_signed64(current + 1 if node.is_increment else current - 1)
        self.set_array_element(node.name, key, new_value)
        return current

    # Maps compound assignment tokens to the base binary operator so that
    # compound assignments reuse _apply_binary_op() without duplication.
    _COMPOUND_TO_BASE = {
        ArithTokenType.PLUS_ASSIGN: ArithTokenType.PLUS,
        ArithTokenType.MINUS_ASSIGN: ArithTokenType.MINUS,
        ArithTokenType.MULTIPLY_ASSIGN: ArithTokenType.MULTIPLY,
        ArithTokenType.DIVIDE_ASSIGN: ArithTokenType.DIVIDE,
        ArithTokenType.MODULO_ASSIGN: ArithTokenType.MODULO,
        ArithTokenType.LSHIFT_ASSIGN: ArithTokenType.LSHIFT,
        ArithTokenType.RSHIFT_ASSIGN: ArithTokenType.RSHIFT,
        ArithTokenType.BIT_AND_ASSIGN: ArithTokenType.BIT_AND,
        ArithTokenType.BIT_OR_ASSIGN: ArithTokenType.BIT_OR,
        ArithTokenType.BIT_XOR_ASSIGN: ArithTokenType.BIT_XOR,
    }

    def evaluate(self, node: ArithNode) -> int:
        """Evaluate an arithmetic AST node."""
        if isinstance(node, NumberNode):
            # A literal wraps to signed 64-bit like any operation result, so
            # a bare/compared/subscript literal >= 2**63 matches bash (e.g.
            # $((9223372036854775808)) is -9223372036854775808).
            return _to_signed64(node.value)
        if isinstance(node, VariableNode):
            return self.get_variable(node.name)
        if isinstance(node, UnaryOpNode):
            return self._eval_unary(node)
        if isinstance(node, BinaryOpNode):
            return self._eval_binary(node)
        if isinstance(node, TernaryNode):
            return self._eval_ternary(node)
        if isinstance(node, AssignmentNode):
            return self._eval_assignment(node)
        if isinstance(node, PreIncrementNode):
            return self._eval_pre_increment(node)
        if isinstance(node, PostIncrementNode):
            return self._eval_post_increment(node)
        if isinstance(node, ArrayElementNode):
            key = self._array_key(node.name, node.index, node.index_text)
            return self.get_array_element(node.name, key)
        if isinstance(node, ArrayAssignmentNode):
            return self._eval_array_assignment(node)
        if isinstance(node, ArrayPreIncrementNode):
            return self._eval_array_pre_increment(node)
        if isinstance(node, ArrayPostIncrementNode):
            return self._eval_array_post_increment(node)
        raise ValueError(f"Unknown node type: {type(node)}")

    # -- Node-type evaluators ------------------------------------------------

    def _eval_unary(self, node: UnaryOpNode) -> int:
        operand = self.evaluate(node.operand)
        if node.op == ArithTokenType.PLUS:
            return operand
        if node.op == ArithTokenType.MINUS:
            return _to_signed64(-operand)
        if node.op == ArithTokenType.NOT:
            return 0 if operand else 1
        if node.op == ArithTokenType.BIT_NOT:
            return _to_signed64(~operand)
        raise ValueError(f"Unknown unary operator: {node.op}")

    def _eval_binary(self, node: BinaryOpNode) -> int:
        # Short-circuit operators — right side evaluated conditionally.
        if node.op == ArithTokenType.AND:
            left = self.evaluate(node.left)
            return 0 if not left else (1 if self.evaluate(node.right) else 0)
        if node.op == ArithTokenType.OR:
            left = self.evaluate(node.left)
            return 1 if left else (1 if self.evaluate(node.right) else 0)
        if node.op == ArithTokenType.COMMA:
            self.evaluate(node.left)
            return self.evaluate(node.right)

        # Both operands needed for everything else.
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        return self._apply_binary_op(node.op, left, right)

    def _eval_ternary(self, node: TernaryNode) -> int:
        if self.evaluate(node.condition):
            return self.evaluate(node.true_expr)
        return self.evaluate(node.false_expr)

    def _eval_assignment(self, node: AssignmentNode) -> int:
        value = self.evaluate(node.value)

        if node.op == ArithTokenType.ASSIGN:
            self.set_variable(node.var_name, value)
            return value

        # Compound assignment — reuse the base binary operator.
        base_op = self._COMPOUND_TO_BASE.get(node.op)
        if base_op is None:
            raise ValueError(f"Unknown assignment operator: {node.op}")
        current = self.get_variable(node.var_name)
        result = self._apply_binary_op(base_op, current, value)
        self.set_variable(node.var_name, result)
        return result

    def _eval_pre_increment(self, node: PreIncrementNode) -> int:
        current = self.get_variable(node.var_name)
        new_value = _to_signed64(current + 1 if node.is_increment else current - 1)
        self.set_variable(node.var_name, new_value)
        return new_value

    def _eval_post_increment(self, node: PostIncrementNode) -> int:
        current = self.get_variable(node.var_name)
        new_value = _to_signed64(current + 1 if node.is_increment else current - 1)
        self.set_variable(node.var_name, new_value)
        return current

    # -- Shared arithmetic ---------------------------------------------------

    @staticmethod
    def _apply_binary_op(op: ArithTokenType, left: int, right: int) -> int:
        """Apply a binary arithmetic operator to two integer operands.

        Used by both ``BinaryOpNode`` and compound ``AssignmentNode``
        evaluation, so the validation and 64-bit wrapping logic lives in
        one place.
        """
        if op == ArithTokenType.PLUS:
            return _to_signed64(left + right)
        if op == ArithTokenType.MINUS:
            return _to_signed64(left - right)
        if op == ArithTokenType.MULTIPLY:
            return _to_signed64(left * right)
        if op == ArithTokenType.DIVIDE:
            if right == 0:
                raise ShellArithmeticError("Division by zero")
            return _to_signed64(_trunc_div(left, right))
        if op == ArithTokenType.MODULO:
            if right == 0:
                raise ShellArithmeticError("Division by zero")
            # C-style truncated remainder (sign matches dividend).
            return _to_signed64(left - _trunc_div(left, right) * right)
        if op == ArithTokenType.POWER:
            if right < 0:
                raise ShellArithmeticError("exponent less than 0")
            # Result wraps to signed 64-bit (bash: 2 ** 64 -> 0). Use modular
            # exponentiation so large exponents don't build a huge intermediate.
            base = left & 0xFFFFFFFFFFFFFFFF
            return _to_signed64(pow(base, right, 1 << 64))

        # Comparison operators (result is always 0 or 1).
        if op == ArithTokenType.LT:
            return 1 if left < right else 0
        if op == ArithTokenType.GT:
            return 1 if left > right else 0
        if op == ArithTokenType.LE:
            return 1 if left <= right else 0
        if op == ArithTokenType.GE:
            return 1 if left >= right else 0
        if op == ArithTokenType.EQ:
            return 1 if left == right else 0
        if op == ArithTokenType.NE:
            return 1 if left != right else 0

        # Bitwise operators.
        if op == ArithTokenType.BIT_AND:
            return _to_signed64(left & right)
        if op == ArithTokenType.BIT_OR:
            return _to_signed64(left | right)
        if op == ArithTokenType.BIT_XOR:
            return _to_signed64(left ^ right)
        # bash masks the shift count to 6 bits (C on x86-64): a negative count
        # wraps into 0..63 (`1 << -1` == `1 << 63`), so no negative-count guard
        # is needed — the mask below already produces bash's answer.
        if op == ArithTokenType.LSHIFT:
            return _to_signed64(left << (right & 63))
        if op == ArithTokenType.RSHIFT:
            return _to_signed64(left) >> (right & 63)

        raise ValueError(f"Unknown binary operator: {op}")


def evaluate_arithmetic(expr: str, shell, expand: bool = True) -> int:
    """Evaluate an arithmetic expression with the given shell context.

    ``expand=False`` skips the $-construct pass for text that is ALREADY
    expanded (e.g. a ``[[ -eq ]]`` operand): a residual literal ``$`` is
    then a syntax error, matching bash, which never rescans expanded text.
    """
    try:
        # First, expand all shell variables and parameter expansions
        expanded_expr = (shell.expansion_manager.expand_string_variables(expr)
                         if expand else expr)

        # Tokenize the expanded expression
        tokenizer = ArithTokenizer(expanded_expr)
        tokens = tokenizer.tokenize()

        # Parse. Pass the (already $-expanded) source so the parser can slice
        # the raw subscript text of array references (associative arrays use
        # the literal subscript as their key).
        parser = ArithParser(tokens, expanded_expr)
        ast = parser.parse()

        # Evaluate
        evaluator = ArithmeticEvaluator(shell)
        return evaluator.evaluate(ast)

    except (SyntaxError, ShellArithmeticError) as e:
        raise ShellArithmeticError(str(e))
    except RecursionError:
        raise ShellArithmeticError("expression too deeply nested")
    except (ValueError, OverflowError, MemoryError) as e:
        raise ShellArithmeticError(str(e))


def execute_arithmetic_expansion(expr: str, shell) -> int:
    """Evaluate a ``$((expr))`` arithmetic-expansion string to its value.

    The adapter between expansion-pipeline callers (which hold the full
    ``$((...))`` source text) and :func:`evaluate_arithmetic`: it strips
    the ``$((``/``))`` delimiters and converts evaluation failures into
    :class:`~psh.core.ExpansionError` after printing the user-facing
    message, so command execution stops (like bash). Text not shaped
    like ``$((...))`` evaluates to 0.

    NOTE: no pre-expansion pass here. evaluate_arithmetic() expands
    $-constructs itself (via expand_string_variables, which delegates
    to the shared _expand_one_dollar scanner), substituting each
    value verbatim exactly once. A second pass here would rescan
    substituted text for further $-expansion, which bash does not do
    (x='$y' makes $(($x)) a syntax error, not the value of y).
    """
    import sys

    from ...core import ExpansionError

    # Remove $(( and ))
    if expr.startswith('$((') and expr.endswith('))'):
        arith_expr = expr[3:-2]
    else:
        return 0

    try:
        return evaluate_arithmetic(arith_expr, shell)
    except ShellArithmeticError as e:
        print(f"psh: arithmetic error: {e}", file=sys.stderr)
        # Raise exception to stop command execution (like bash)
        raise ExpansionError(f"arithmetic error: {e}")
    except (ValueError, TypeError) as e:
        print(f"psh: unexpected arithmetic error: {e}", file=sys.stderr)
        # Raise exception to stop command execution (like bash)
        raise ExpansionError(f"unexpected arithmetic error: {e}")
