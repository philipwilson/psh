"""Evaluator for shell arithmetic AST nodes, plus the public entry points."""

import re
from typing import Optional, Tuple, Union

from ...core import (
    ArraySubscriptError,
    AssociativeArray,
    ExpansionError,
    IndexedArray,
    NamerefCycleError,
    OptionHandler,
    ReadonlyVariableError,
    TopLevelAbort,
)
from ..operands import DQ_STRING
from .errors import ShellArithmeticError, _to_signed64
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

    # Maximum evaluation (AST-recursion) depth; see :meth:`evaluate`. Bounds
    # the WIDTH of a flat operator chain the parser builds iteratively, the
    # evaluation-side companion to ArithParser.MAX_DEPTH's parse-side NESTING
    # bound.
    MAX_EVAL_DEPTH = 1024

    def __init__(self, shell, arith_source_quotes: bool = True):
        self.shell = shell
        self._eval_depth = 0
        # True for `(( ))`/`$(( ))` (body not shell-processed → apply the extra
        # round-1 dquote pass to a SOURCE substitution-free associative
        # subscript, in _arith_preexpand); False for `let`/`[[`/stored values
        # (already shell-processed). See _arith_source_round1 (W2/CV1 B1/M1).
        self._arith_source_quotes = arith_source_quotes

    def get_variable(self, name: str) -> int:
        """Get variable value, converting to integer.

        Matches bash, which recursively evaluates a variable's value as an
        arithmetic expression: ``a=b; b=42; $((a))`` is 42, ``a="2*3"; $((a))``
        is 6, and base-prefixed values (``0x10``, ``010``, ``2#101``) are
        honoured. A cycle guard / recursion limit prevents infinite loops from
        circular references.
        """
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
            # Double-underscore names are the one exception: they are resolved
            # via the evaluate_arithmetic() fallback below, NOT this direct
            # follow. Probed (r19/D3, 2026-07-11): acyclic chains converge to
            # the same value either way, but a CIRCULAR reference through a
            # ``__`` name is then caught by the arithmetic recursion-depth guard
            # rather than the local ``seen`` guard, which changes the variable
            # name in the "expression recursion level exceeded" message (neither
            # spelling is uniformly bash-correct — bash reports a different token
            # per cycle shape). Kept to preserve current output; a deliberate
            # unification of the two cycle guards is deferred. (Introduced by
            # 48634a99 with no recorded rationale; this note replaces the
            # cryptic ``'_' * 2`` spelling with an explanation.)
            if value.isidentifier() and not value.startswith('__'):
                if value in seen:
                    raise ShellArithmeticError(
                        f"{value}: expression recursion level exceeded")
                seen.add(var)
                var = value
                continue

            # Otherwise evaluate the value as an arithmetic sub-expression.
            # Handles 0x.., 0.. (octal), base#n, and full expressions such as
            # "2*3" or "a+1". Recursion is bounded by evaluate_arithmetic.
            #
            # expand=False: a STORED value reached via variable resolution is
            # NOT re-$-expanded. bash never rescans a substituted value, so a
            # value literally containing a $ (`x='$y'; $((x))`) is a syntax
            # error, not the value of y — the package's own never-rescan
            # invariant (see execute_arithmetic_expansion's docstring). Bare
            # names / expression text ("a+1", "0x10") contain no $ and are
            # unaffected; the name-chain fast path above (isidentifier) is a
            # separate ARITH-VALUE recursion, also unaffected.
            #
            # arith_source_quotes=False: a STORED value re-evaluated as
            # arithmetic is let-like (its quotes/backslashes are literal data,
            # already quote-processed when stored), so an associative subscript
            # inside it gets NO extra (( )) round-1 dquote pass — `y='h[\"q\"]';
            # $(( y ))` keys `"q"` (bash 0), not `q` (CV1 B1 R2).
            return evaluate_arithmetic(value, self.shell, expand=False,
                                       arith_source_quotes=False)

    def set_variable(self, name: str, value: int) -> None:
        """Set variable value"""
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
        # expand=False for the same reason as get_variable: an array element /
        # scalar value reached here is a STORED value, never re-$-expanded
        # (bash: `arr=('$y'); $((arr[0]))` is a syntax error, not $y's value).
        # arith_source_quotes=False: a stored value is let-like, so a subscript
        # inside it gets NO extra round-1 dquote pass (CV1 B1 R2).
        return evaluate_arithmetic(value, self.shell, expand=False,
                                   arith_source_quotes=False)

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
        try:
            return self.shell.state.scope_manager.resolve_nameref_name(name)
        except NamerefCycleError:
            return name

    def _array_key(self, name: str, index_text: str) -> Union[int, str]:
        """Resolve a verbatim subscript to its lookup key — target kind FIRST.

        The subscript arrives RAW (its ``$``-forms held out of the arithmetic
        pre-pass by ``_arith_preexpand``), so the ONE subscript authority
        (``ExpansionManager.subscript``, campaign W2) interprets it with full
        provenance: an associative array keys it under assignment-value
        semantics (the SAME engine ``h[$k]=v`` uses) — source-spelled quotes and
        backslashes are removed, but characters arriving via ``$k`` stay
        LITERAL, matching bash (``k='"q"'; (( h[$k]=1 ))`` keys ``"q"``, and
        ``k='$x'; (( h[$k]=1 ))`` keys the literal ``$x`` — a substituted
        ``$`` is never rescanned). bash's extra round-1 dquote pass for
        ``(( ))``/``$(( ))`` was already applied to a SOURCE, substitution-free
        subscript in the pre-pass (``_arith_preexpand`` / ``_arith_source_round1``;
        W2/CV1 B1/M1), so ``index_text`` arrives round-1'd where applicable and
        the associative key here is the single round-2. An indexed array, scalar,
        or undeclared name expands then arithmetic-evaluates the raw text, so
        ``a[i++]`` side-effects fire exactly once per lvalue resolution.

        Empty-subscript policy is psh's OWN, a DELIBERATE divergence — live bash
        5.2 rejects EVERY empty-key spelling as a "bad array subscript" (both
        ``h[]``/``h[$e]`` AND the source empty-quoted ``h[""]``). psh instead
        treats a literal-empty or substituted-empty subscript as fatal but
        accepts a source empty-quoted key (``h[""]``) as a valid empty key
        (register #3 carry). This is intentional and pinned, not a bash mirror.
        """
        if index_text == '':
            raise ShellArithmeticError(f"{name}[]: bad array subscript")
        var = self.shell.state.scope_manager.get_variable_object(
            self._nameref_target(name))
        subscript = self.shell.expansion_manager.subscript
        if var is not None and isinstance(var.value, AssociativeArray):
            key = subscript.associative_key(index_text)
            # psh's deliberate empty-subscript policy (NOT bash's — see the
            # docstring): an empty key from substitution or literal-empty text is
            # fatal; a source empty-quoted key (h[""]) is accepted as a valid
            # empty key (raw_has_source_quote only re-lexes, so the one keying
            # expansion above is not doubled).
            if key == '' and not subscript.raw_has_source_quote(index_text):
                raise ShellArithmeticError(f"{name}[]: bad array subscript")
            return key
        # Indexed / scalar / undeclared: the $-forms held out of the pre-pass
        # (_arith_preexpand) are substituted here ONCE, then arithmetic-evaluated
        # with expand=False. An empty expansion is bash's "bad array subscript".
        flat = _arith_preexpand(index_text, self.shell, self._arith_source_quotes)
        if flat == '':
            raise ShellArithmeticError(f"{name}[]: bad array subscript")
        return evaluate_arithmetic(flat, self.shell, expand=False,
                                   arith_source_quotes=self._arith_source_quotes)

    def get_array_element(self, name: str, key: Union[int, str]) -> int:
        """Read an array element (or scalar via index 0) as an integer.

        ``key`` is a str for associative arrays and an int for indexed
        arrays / scalars (see :meth:`_array_key`).
        """
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

    # -- LValue read/write (scalar and array element, one path each) ---------

    def _resolve_lvalue(self, lvalue: LValue) -> Tuple[str, Optional[Union[int, str]]]:
        """Resolve an lvalue to a concrete ``(name, key)`` target, evaluating
        any array subscript EXACTLY ONCE. ``key`` is ``None`` for a scalar, an
        int for an indexed-array element / scalar-as-``[0]``, or the literal
        subscript text for an associative array (see :meth:`_array_key`).
        Evaluating the subscript a single time here — not once per read and
        once per write — is what makes ``a[b++] += 1`` increment ``b`` only
        once, matching bash."""
        if lvalue.subscript_text is None:
            return lvalue.name, None
        return lvalue.name, self._array_key(lvalue.name, lvalue.subscript_text)

    def _read_lvalue(self, name: str, key: Optional[Union[int, str]]) -> int:
        """Read the current integer value of a resolved lvalue target."""
        if key is None:
            return self.get_variable(name)
        return self.get_array_element(name, key)

    def _write_lvalue(self, name: str, key: Optional[Union[int, str]],
                      value: int) -> None:
        """Write ``value`` to a resolved lvalue target — the ONE place scalar
        and array-element writes converge, so the store's readonly/nameref
        enforcement applies uniformly to both."""
        if key is None:
            self.set_variable(name, value)
        else:
            self.set_array_element(name, key, value)

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
        """Evaluate an arithmetic AST node, bounding evaluation-recursion depth.

        A WIDE flat operator chain (`0+1+1+...`) is parsed iteratively into a
        deep left-leaning tree, which _dispatch recurses over ~a few Python
        frames per node. MAX_EVAL_DEPTH bounds that recursion so a
        pathologically long chain trips a clean "expression too deeply nested"
        arithmetic error instead of a raw RecursionError. This is the
        evaluation-side companion to ArithParser.MAX_DEPTH (which bounds
        parse-side NESTING and `**` chains); each single recursion path is
        bounded, so a RecursionError from arithmetic ordinarily means the
        SURROUNDING shell exhausted the stack. The guards do NOT bound their
        PRODUCT: a pathological composite value chain (get_variable ->
        evaluate_arithmetic re-entry stacking a fresh per-level evaluation
        depth under each level) can still exhaust the interpreter stack —
        see ArithParser.MAX_DEPTH's caveat and the r19-T9 deferred ledger.
        (bash computes such chains; psh's cap is a documented divergence.)
        """
        self._eval_depth += 1
        try:
            if self._eval_depth > self.MAX_EVAL_DEPTH:
                raise ShellArithmeticError("expression too deeply nested")
            return self._dispatch(node)
        finally:
            self._eval_depth -= 1

    def _dispatch(self, node: ArithNode) -> int:
        """Dispatch a node to its evaluator (the depth-guarded body of
        :meth:`evaluate`)."""
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
        if isinstance(node, IncDecNode):
            return self._eval_incdec(node)
        if isinstance(node, ArrayElementNode):
            key = self._array_key(node.name, node.index_text)
            return self.get_array_element(node.name, key)
        # Cant-happen: the parser only builds the node types dispatched above.
        # RuntimeError (not ValueError) so strict-errors surfaces a genuine
        # internal defect here instead of masking it as a shell arithmetic
        # error. The ValueError catch in _evaluate_arithmetic_inner is reserved
        # for USER-reachable ValueErrors (the huge-int int() parse limit).
        raise RuntimeError(f"internal: unknown arithmetic node type: {type(node)}")

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
        # Cant-happen: the parser only builds these four unary operators.
        # RuntimeError => strict-errors surfaces it as an internal defect.
        raise RuntimeError(f"internal: unknown unary operator: {node.op}")

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
        """Evaluate a scalar or array-element assignment (``=`` or compound)."""
        name, key = self._resolve_lvalue(node.lvalue)

        if node.op == ArithTokenType.ASSIGN:
            value = self.evaluate(node.value)
            self._write_lvalue(name, key, value)
            return value

        # Compound assignment — reuse the base binary operator. Read the LHS's
        # CURRENT value BEFORE evaluating the RHS: bash binds the left operand
        # of `+=`/`-=`/... once at the start, so an embedded post/pre-increment
        # of the same location in the RHS does not feed back into that read
        # (`c=1; $((c+=c++))` is 2, not 3 — c is read as 1, then c++ yields 1,
        # then 1+1=2; `a=(1 2); $((a[1]+=a[1]++))` is 4, not 5). Any array
        # subscript was evaluated once in _resolve_lvalue.
        base_op = self._COMPOUND_TO_BASE.get(node.op)
        if base_op is None:
            # Cant-happen: the parser only emits ASSIGN or a _COMPOUND_TO_BASE
            # key. RuntimeError => strict-errors surfaces it as a defect.
            raise RuntimeError(f"internal: unknown assignment operator: {node.op}")
        current = self._read_lvalue(name, key)
        value = self.evaluate(node.value)
        result = self._apply_binary_op(base_op, current, value)
        self._write_lvalue(name, key, result)
        return result

    def _eval_incdec(self, node: IncDecNode) -> int:
        """Evaluate ``++``/``--`` on a scalar or array element. Returns the NEW
        value for the prefix form (``++x``) and the OLD value for the postfix
        form (``x++``)."""
        name, key = self._resolve_lvalue(node.lvalue)
        current = self._read_lvalue(name, key)
        is_increment = node.op == ArithTokenType.INCREMENT
        new_value = _to_signed64(current + 1 if is_increment else current - 1)
        self._write_lvalue(name, key, new_value)
        return new_value if node.prefix else current

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

        # Cant-happen: every operator the parser emits is handled above.
        # RuntimeError => strict-errors surfaces it as an internal defect.
        raise RuntimeError(f"internal: unknown binary operator: {op}")


def _skip_dollar_form(expr: str, i: int) -> int:
    """Index just past the ``$``-form starting at ``expr[i] == '$'``.

    Quote-blind, delimiter-balanced: ``${...}``/``$(...)``/``$((...))`` skip to
    their matching brace/paren, ``$name``/``$1``/``$?`` skip their operand.
    Used only to keep a ``[`` INSIDE a ``$``-form (``${arr[0]}``, ``$(cmd[…])``)
    from being mistaken for an arithmetic subscript in
    :func:`_mask_arith_subscripts`; imperfect balancing can only over-skip, never
    start a spurious subscript, so the pre-pass stays safe."""
    n = len(expr)
    j = i + 1
    if j >= n:
        return j
    c = expr[j]
    if c in '{(':
        close = '}' if c == '{' else ')'
        depth = 0
        while j < n:
            if expr[j] == c:
                depth += 1
            elif expr[j] == close:
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return j
    if c.isalpha() or c == '_':
        while j < n and (expr[j].isalnum() or expr[j] == '_'):
            j += 1
        return j
    # Single-char special parameter ($1, $?, $@, $#, $*, $!, $$, $-).
    return j + 1


def _bracket_region_end(expr: str, i: int) -> Optional[int]:
    """Index just past the ``]`` closing the ``[`` at ``expr[i]`` (nesting
    counted, quote-blind — exactly like ``ArithTokenizer._read_subscript``), or
    ``None`` if unbalanced (left for the tokenizer to reject like bash)."""
    n = len(expr)
    depth = 0
    while i < n:
        c = expr[i]
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _mask_arith_subscripts(expr: str) -> "Tuple[str, list]":
    """Replace each top-level ``IDENT[...]`` subscript region with a NUL
    placeholder, returning ``(masked_expr, [raw_region, ...])``.

    This is what makes arithmetic associative keys provenance-faithful (W2 /
    CV1): the subscript is held OUT of the ``$``-substitution pre-pass so its
    ``$k`` reaches the subscript authority UNSUBSTITUTED, exactly as a
    non-arithmetic ``h[$k]=v`` does. The authority then keys the RAW text under
    assignment-value semantics — source-spelled quotes/backslashes are removed,
    but characters arriving via ``$k`` stay literal (bash never quote-removes
    substituted subscript text: ``k='"q"'; (( h[$k]=1 ))`` keys ``"q"``).

    Only an ``IDENT`` immediately followed by ``[`` starts a subscript (bash
    adjacency; ``h [k]`` is not one); ``$``-forms are skipped whole so a bracket
    inside ``${...}``/``$(...)`` is never masked."""
    out: 'list[str]' = []
    regions: 'list[str]' = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == '$':
            j = _skip_dollar_form(expr, i)
            out.append(expr[i:j])
            i = j
        elif ch == '`':
            k = expr.find('`', i + 1)
            j = n if k == -1 else k + 1
            out.append(expr[i:j])
            i = j
        elif ch.isalpha() or ch == '_':
            j = i + 1
            while j < n and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            out.append(expr[i:j])
            i = j
            if i < n and expr[i] == '[':
                end = _bracket_region_end(expr, i)
                if end is not None:
                    regions.append(expr[i:end])
                    out.append('\x00%d\x00' % (len(regions) - 1))
                    i = end
        else:
            out.append(ch)
            i += 1
    return ''.join(out), regions


def _arith_source_round1(region: str, shell) -> str:
    """Round 1 of bash's TWO-round ``(( ))``/``$(( ))`` associative keying
    (W2/CV1 B1/M1), applied to a SOURCE ``[...]`` subscript region ONLY when it
    contains NO expansion (M1: a subscript with any ``$``/backtick gets round-2
    ONLY — its round-1 output would be final, so the shared associative-key
    engine handles it directly, keeping ``\\"`` literal beside a substituted
    value). For a substitution-free source subscript with escapes, the arith
    body was not shell-word-processed, so bash applies an extra dquote-context
    escape pass first (``(( h[\\"q\\"] ))`` keys ``q`` — round 1 ``\\"``->``"``,
    round 2 removes it), consistent with ``(( expr )) == let "expr"``."""
    content = region[1:-1]
    if '$' in content or '`' in content or '\\' not in content:
        return region          # has expansion, or no escape → round-2 only
    processed = shell.expansion_manager.expand_string_variables(
        content, quote_ctx=DQ_STRING)
    return '[' + processed + ']'


def _arith_preexpand(expr: str, shell, arith_source_quotes: bool = True) -> str:
    """Run the arithmetic ``$``-substitution pre-pass, holding array-subscript
    regions RAW (see :func:`_mask_arith_subscripts`) so a subscript's ``$k``
    reaches the keying authority with provenance. For a SOURCE subscript in a
    ``(( ))``/``$(( ))`` context (``arith_source_quotes``), the extra round-1
    dquote escape pass is applied here — to source regions only, so a subscript
    that arrives via ``$``-expansion (``$(( $y ))``) is NEVER round-1'd (it is
    let-like; W2/CV1 R2/M1). ``let``/``[[``/stored-value contexts pass
    ``arith_source_quotes=False``. Subscript-free expressions take the
    byte-identical fast path."""
    if '[' not in expr:
        return shell.expansion_manager.expand_string_variables(
            expr, quote_ctx=DQ_STRING)
    masked, regions = _mask_arith_subscripts(expr)
    expanded = shell.expansion_manager.expand_string_variables(
        masked, quote_ctx=DQ_STRING)
    for idx, region in enumerate(regions):
        if arith_source_quotes:
            region = _arith_source_round1(region, shell)
        expanded = expanded.replace('\x00%d\x00' % idx, region)
    return expanded


def evaluate_arithmetic(expr: str, shell, expand: bool = True,
                        arith_source_quotes: bool = True) -> int:
    """Evaluate an arithmetic expression with the given shell context.

    ``expand=False`` skips the $-construct pass for text that is ALREADY
    expanded (e.g. a ``[[ -eq ]]`` operand): a residual literal ``$`` is
    then a syntax error, matching bash, which never rescans expanded text.

    ``arith_source_quotes=True`` is the ``(( ))``/``$(( ))`` default: bash
    applies an extra round-1 dquote pass to a source-spelled associative
    subscript because the body is not shell-word-processed. ``let`` passes
    ``False`` (its argument was already shell-processed). See
    :func:`_arith_source_dquote_round` / ``_array_key`` (W2/CV1 B1).
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
        return _evaluate_arithmetic_inner(expr, shell, expand,
                                          arith_source_quotes)
    finally:
        shell.state._arith_recursion_depth = depth - 1


def _evaluate_arithmetic_inner(expr: str, shell, expand: bool,
                               arith_source_quotes: bool = True) -> int:
    """Tokenize/parse/evaluate one arithmetic expression (no depth guard)."""
    try:
        # First, expand all shell variables and parameter expansions.
        # Arithmetic is a dquote-like context for nested ${x:-word}
        # operands (bash: $(( ${u:-"5"} )) is 5+..., but $(( ${u:-'5'} ))
        # keeps the single quotes and is a syntax error). Array-subscript
        # regions are held RAW through this pass (_arith_preexpand) so an
        # associative key's $k is not substituted-then-quote-removed — the
        # subscript authority keys the raw text with provenance (W2/CV1).
        expanded_expr = (_arith_preexpand(expr, shell, arith_source_quotes)
                         if expand else expr)

        # Tokenize the expanded expression
        tokenizer = ArithTokenizer(expanded_expr)
        tokens = tokenizer.tokenize()

        # Parse. Array subscripts arrive as verbatim SUBSCRIPT tokens (the
        # tokenizer captured them raw); interpretation by target kind happens
        # at evaluation (the W2 subscript authority).
        parser = ArithParser(tokens)
        ast = parser.parse()

        # Evaluate
        evaluator = ArithmeticEvaluator(shell, arith_source_quotes)
        return evaluator.evaluate(ast)

    except (SyntaxError, ShellArithmeticError) as e:
        # A too-deep expression arrives here as an EXPLICIT depth-guard error
        # ("expression too deeply nested"): from ArithParser.MAX_DEPTH (nesting
        # + right-associative `**` chains) or from the evaluator's own
        # MAX_EVAL_DEPTH guard (wide flat chains). A RecursionError, by
        # contrast, is NOT converted here: each single arithmetic recursion
        # path is bounded by those guards, so a RecursionError reaching this
        # point ordinarily means the SURROUNDING shell exhausted the
        # interpreter stack (runaway function recursion whose deepest frame
        # merely happened to be in arithmetic) — it propagates to the
        # function-call boundary, which reports "maximum function nesting
        # level exceeded" (executor/function.py). Known residue: a pathological
        # composite value chain can stack the per-path guards' PRODUCT past the
        # interpreter limit and leak a raw RecursionError from pure arithmetic
        # (see ArithParser.MAX_DEPTH's caveat; r19-T9 deferred ledger).
        raise ShellArithmeticError(str(e)) from e
    except (ValueError, OverflowError, MemoryError) as e:
        # These stay caught because they are USER-reachable, not internal
        # defects: e.g. int() on a literal past CPython's str->int digit limit
        # (`$(( 999…<4300+ digits> ))`) raises ValueError, and an over-large
        # allocation raises MemoryError. The evaluator's own cant-happen
        # branches now raise RuntimeError (which is NOT caught here) so a real
        # defect surfaces under strict-errors instead of being masked.
        raise ShellArithmeticError(str(e)) from e


def arithmetic_expansion_value(arith_expr: str, shell) -> int:
    """Evaluate a BARE arithmetic expression (no ``$(( ))`` wrapper) for the
    expansion pipeline, converting evaluation failures into the user-facing
    errors that stop command execution (like bash).

    The Word-AST ``ExpansionEvaluator`` holds the bare expression already and
    calls here directly; string callers that hold the full ``$((...))`` span go
    through :func:`execute_arithmetic_expansion`, which strips and delegates.

    NOTE: no pre-expansion pass here. evaluate_arithmetic() expands
    $-constructs itself (via expand_string_variables, which delegates
    to the shared _expand_one_dollar scanner), substituting each
    value verbatim exactly once. A second pass here would rescan
    substituted text for further $-expansion, which bash does not do
    (x='$y' makes $(($x)) a syntax error, not the value of y).
    """
    import sys

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


def execute_arithmetic_expansion(expr: str, shell) -> int:
    """Evaluate a ``$((expr))`` arithmetic-expansion string to its value.

    The adapter for callers that hold the full ``$((...))`` source text (e.g.
    the operand scanner slicing a span): strips the ``$((``/``))`` delimiters
    and delegates to :func:`arithmetic_expansion_value`. Text not shaped like
    ``$((...))`` evaluates to 0.
    """
    if expr.startswith('$((') and expr.endswith('))'):
        return arithmetic_expansion_value(expr[3:-2], shell)
    return 0
