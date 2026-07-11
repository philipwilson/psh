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

# bash's EXPR_NEST_MAX. A variable whose value is itself an expression is
# evaluated recursively (get_variable -> evaluate_arithmetic), so a
# self-referential (`x="x+1"`) or too-deeply-chained expression would exhaust
# the interpreter stack. Bounding re-entrancy here trips a clean "expression
# recursion level exceeded" arithmetic error (status 1, the line resumes)
# instead of a Python RecursionError leaking as an internal defect. Tripping at
# ``depth >= EXPR_NEST_MAX`` (not ``>``) lands psh on bash's EXACT observed
# boundary — psh's counter increments once at the outer expression's entry, one
# level ahead of bash's internal expr_depth, so ``>=`` cancels that offset.
# Probe-verified against bash 5.2.26 (tmp/probes-r18t2-arith/
# recursion_boundary.py): an a0=0; a1="a0+1"; ... self-reference chain 1022
# deep evaluates in BOTH shells, 1023 deep trips in BOTH.
_MAX_ARITH_RECURSION = 1024


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

    def _nameref_target(self, name: str) -> str:
        """Resolve a nameref to its target name for array element ops.

        ``declare -n r=h; (( r[foo] += 5 ))`` must act on ``h[foo]`` — and for
        an associative ``h`` the subscript must stay the LITERAL key ``foo``,
        not be arithmetic-evaluated (which wrote element ``[0]``). The write
        path already resolves via ``store.set_element``; the key computation
        and the read need the same resolution so all three agree on the
        target's type and name. A non-nameref name is returned unchanged; a
        cyclic nameref is left as-is (the store's write path emits the warning).
        """
        from ...core import NamerefCycleError
        try:
            return self.shell.state.scope_manager.resolve_nameref_name(name)
        except NamerefCycleError:
            return name

    def _array_key(self, name: str, index_node: ArithNode, index_text: str) -> Union[int, str]:
        """Resolve the subscript of an array reference to its lookup key.

        For an associative array the subscript is the LITERAL text used
        directly as the key (bash: bare identifiers are not variable
        references). For everything else (indexed arrays, scalars, or a
        not-yet-created array) the subscript is arithmetic-evaluated to an
        int.
        """
        from ...core import AssociativeArray
        var = self.shell.state.scope_manager.get_variable_object(
            self._nameref_target(name))
        if var is not None and isinstance(var.value, AssociativeArray):
            return index_text
        return self.evaluate(index_node)

    def get_array_element(self, name: str, key: Union[int, str]) -> int:
        """Read an array element (or scalar via index 0) as an integer.

        ``key`` is a str for associative arrays and an int for indexed
        arrays / scalars (see :meth:`_array_key`).
        """
        from ...core import AssociativeArray, IndexedArray, OptionHandler
        name = self._nameref_target(name)
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
        from ...core import ArraySubscriptError, NamerefCycleError
        from .errors import ShellArithmeticError
        # The store owns the readonly guard (aborts, unchanged, exactly like the
        # SimpleCommand `a[0]=9` path), nameref resolution (so `declare -n r=arr;
        # (( r[0]=9 ))` sets arr[0] IN PLACE instead of replacing arr), negative-
        # index resolution, create-if-absent, and observers — no direct
        # `.value.set` here (core-state C2).
        try:
            self.shell.state.scope_manager.store.set_element(name, key, str(value))
        except ArraySubscriptError as e:
            # Surface as an arithmetic error so `(( ))` reports it like bash
            # ("NAME[SUB]: bad array subscript") rather than as an internal
            # defect under strict-errors.
            raise ShellArithmeticError(f"{name}[{e.subscript}]: {e}") from e
        except NamerefCycleError as e:
            # Cyclic-nameref write: warn and drop the assignment (bash:
            # `(( na[0]=5 ))` warns, status from the value).
            self.shell.state.scope_manager.warn_nameref_cycle(e.name)

    def _eval_array_assignment(self, node: 'ArrayAssignmentNode') -> int:
        key = self._array_key(node.name, node.index, node.index_text)

        if node.op == ArithTokenType.ASSIGN:
            value = self.evaluate(node.value)
            self.set_array_element(node.name, key, value)
            return value

        base_op = self._COMPOUND_TO_BASE.get(node.op)
        if base_op is None:
            raise ValueError(f"Unknown assignment operator: {node.op}")
        # Read the element's CURRENT value BEFORE evaluating the RHS, so an
        # embedded ++/-- on the same element in the RHS does not feed back into
        # the read (bash: a=(1 2); $((a[1]+=a[1]++)) is 4, not 5). See the
        # scalar _eval_assignment for the same ordering rationale.
        current = self.get_array_element(node.name, key)
        value = self.evaluate(node.value)
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
        if node.op == ArithTokenType.ASSIGN:
            value = self.evaluate(node.value)
            self.set_variable(node.var_name, value)
            return value

        # Compound assignment — reuse the base binary operator. Read the LHS's
        # CURRENT value BEFORE evaluating the RHS: bash binds the left operand
        # of `+=`/`-=`/... once at the start, so an embedded post/pre-increment
        # of the same variable in the RHS does not feed back into that read
        # (`c=1; $((c+=c++))` is 2, not 3 — c is read as 1, then c++ yields 1,
        # then 1+1=2).
        base_op = self._COMPOUND_TO_BASE.get(node.op)
        if base_op is None:
            raise ValueError(f"Unknown assignment operator: {node.op}")
        current = self.get_variable(node.var_name)
        value = self.evaluate(node.value)
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
    # Bound re-entrancy so a self-referential/deeply-chained expression trips
    # a clean arithmetic error instead of a RecursionError (see
    # _MAX_ARITH_RECURSION). The counter lives on shell state so it spans the
    # get_variable -> evaluate_arithmetic re-entry, and the finally always
    # unwinds it (including on the exceptions raised below).
    depth = shell.state._arith_recursion_depth + 1
    shell.state._arith_recursion_depth = depth
    try:
        if depth >= _MAX_ARITH_RECURSION:
            raise ShellArithmeticError(
                f"{expr.strip()}: expression recursion level exceeded")
        return _evaluate_arithmetic_inner(expr, shell, expand)
    finally:
        shell.state._arith_recursion_depth = depth - 1


def _evaluate_arithmetic_inner(expr: str, shell, expand: bool) -> int:
    """Tokenize/parse/evaluate one arithmetic expression (no depth guard)."""
    try:
        # First, expand all shell variables and parameter expansions.
        # Arithmetic is a dquote-like context for nested ${x:-word}
        # operands (bash: $(( ${u:-"5"} )) is 5+..., but $(( ${u:-'5'} ))
        # keeps the single quotes and is a syntax error).
        from ..operands import DQ_STRING
        expanded_expr = (shell.expansion_manager.expand_string_variables(
                             expr, quote_ctx=DQ_STRING)
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
        # A genuinely too-deep expression arrives here as ArithParser's
        # explicit depth-guard SyntaxError ("expression too deeply nested").
        # A RecursionError, by contrast, means the SURROUNDING shell
        # exhausted the interpreter stack (runaway function recursion whose
        # deepest frame merely happened to be in arithmetic) — it must NOT
        # be relabeled as an arithmetic error; it propagates to the
        # function-call boundary, which reports "maximum function nesting
        # level exceeded".
        raise ShellArithmeticError(str(e)) from e
    except (ValueError, OverflowError, MemoryError) as e:
        raise ShellArithmeticError(str(e)) from e


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

    from ...core import ExpansionError, ReadonlyVariableError, TopLevelAbort

    # Remove $(( and ))
    if expr.startswith('$((') and expr.endswith('))'):
        arith_expr = expr[3:-2]
    else:
        return 0

    try:
        return evaluate_arithmetic(arith_expr, shell)
    except ReadonlyVariableError as e:
        # Assigning to a readonly variable inside $(( )) word expansion.
        # bash prints the error and DISCARDS the rest of the current line
        # (the same-line `;` tail, `&&`/`||` tail, ...), resuming at the next
        # line — the readonly-assignment discard, which (unlike the
        # $((1/0))/bad-subscript expansion errors) is NOT immune to `set -e`:
        # under errexit a non-interactive shell exits. Mirror the plain
        # assignment path (executor/command_assignments.py) exactly: print,
        # then raise the errexit-eligible, eval/source-contained TopLevelAbort.
        print(f"{shell.state.error_location_prefix()}{e.name}: readonly variable", file=sys.stderr)
        raise TopLevelAbort(1) from None
    except ShellArithmeticError as e:
        print(f"psh: arithmetic error: {e}", file=sys.stderr)
        # Raise exception to stop command execution (like bash)
        raise ExpansionError(f"arithmetic error: {e}") from e
    except (ValueError, TypeError) as e:
        print(f"psh: unexpected arithmetic error: {e}", file=sys.stderr)
        # Raise exception to stop command execution (like bash)
        raise ExpansionError(f"unexpected arithmetic error: {e}") from e
