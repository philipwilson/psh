"""Drift-locks for the ONE operand scalar projection (remediation slot 3.3).

HIGH-6 was a value operand flattening its ``"$@"`` fields into one
space-joined field. The flatten was possible — and invisible — because the
operand result was a ``str`` SUBCLASS: every consumer accepted it silently, so
the scalar projection re-entered without anyone naming it. The fix makes the
operand result an opaque :class:`psh.expansion.operands.OperandValue` whose
only projection is :meth:`~psh.expansion.operands.OperandValue.as_scalar`.

These guards keep that property from eroding:

1. The retired ``OperandResult`` str-subclass stays deleted — reintroducing a
   str-subclass operand result restores the silent-re-entry hazard wholesale.
2. ``as_scalar()`` is called ONLY from the RULED terminal consumers. A new
   call site is a reviewed edit to :data:`RULED_PROJECTIONS` here, which is
   the campaign's "the set is CLOSED" ruling expressed as a test.
3. ``OperandValue.__str__`` raises ``TypeError`` specifically — not a
   ``PshError`` and not any expected-shell-error type. Under the suite-wide
   ``PSH_STRICT_ERRORS`` policy a stray ``TypeError`` is an INTERNAL DEFECT
   that fails loudly, whereas a shell-error type would be swallowed to exit 1
   and the loudness — the whole point — would be lost.

The scanners are self-tested against synthetic offenders (the tests whose
names end ``_guard_detects_*``) so they cannot rot into no-ops: a guard that
cannot fail is not a guard.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

#: The RULED terminal consumers: (module path relative to psh/, enclosing
#: function name). Each is a context where bash ITSELF requires one string,
#: every one probe-backed against bash 5.2.26 (slot 3.3 Phase A, matrices I/L).
#: Adding a row here is a semantic decision — that a context genuinely cannot
#: carry more than one field — and must come with its bash probe.
RULED_PROJECTIONS = {
    # A pattern / replacement operand is one string, and feeds the FROZEN
    # pattern engine: `v="a b c"; "${v#${x:-"$@"}}"` is ' c' in bash.
    ("expansion/operands.py", "_expand_pattern_operand"),
    ("expansion/operands.py", "_expand_replacement_operand"),
    # ${x:?MSG} / ${x?MSG} render ONE diagnostic message.
    ("expansion/operators.py", "_view_conditional"),
    ("expansion/operators.py", "_qmark_error"),
    # ${x:=W} STORES a scalar: a shell variable holds a string (matrix D).
    ("expansion/operators.py", "_assign_default"),
    # The shared string walker: heredoc bodies, here-strings, $(( )),
    # [[ ]] string operands, redirect targets, array subscripts.
    ("expansion/variable.py", "expand_string_variables"),
    # An assignment VALUE is one string: `v=${x:-"$@"}` assigns 'a b'.
    ("expansion/word_expander.py", "expand_assignment_value_word"),
    # A `case` PATTERN word is one glob pattern.
    ("expansion/manager.py", "expand_word_as_pattern"),
    # [[ ]] operands: `[[ ${x:-"$@"} == "a b" ]]` is true in bash.
    ("executor/enhanced_test_evaluator.py", "_operand_string"),
    ("executor/enhanced_test_evaluator.py", "_rhs_walk"),
}

#: Symbols the 3.3 consolidation deleted. Reappearance = the str-subclass
#: operand result is back, and with it the unnamed scalar re-entry.
RETIRED = ("OperandResult",)


def _sources():
    return [p for p in PSH.rglob("*.py") if "__pycache__" not in p.parts]


def _rel(path):
    return str(path.relative_to(PSH))


def find_as_scalar_calls(source: str):
    """Return {enclosing function name} for every ``.as_scalar()`` call.

    A call at module level (or in a class body) is reported as ``'<module>'``
    so it can never silently pass the ruled-set check.
    """
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "as_scalar"):
            cur = parents.get(node)
            name = "<module>"
            while cur is not None:
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = cur.name
                    break
                cur = parents.get(cur)
            found.add(name)
    return found


def find_retired(source: str):
    tree = ast.parse(source)
    hits = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in RETIRED:
            hits.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in RETIRED:
            hits.add(node.attr)
        elif isinstance(node, ast.ClassDef) and node.name in RETIRED:
            hits.add(node.name)
    return hits


# --------------------------------------------------------------------------
# The guards
# --------------------------------------------------------------------------

def test_retired_operand_result_absent():
    """The str-subclass operand result stays deleted."""
    offenders = {}
    for path in _sources():
        hits = find_retired(path.read_text())
        if hits:
            offenders[_rel(path)] = sorted(hits)
    assert not offenders, (
        "The retired str-subclass operand result reappeared — a str-subclass "
        "result is silently consumable and reopens HIGH-6: " + repr(offenders))


def test_projection_called_only_from_ruled_consumers():
    """``as_scalar()`` is called ONLY from the ruled terminal-consumer set.

    This is the charter's "static guards find no semantic scalar re-entry"
    criterion. A NEW call site means some context started demanding one
    string; that is a semantic decision needing a bash probe, so it is a
    reviewed edit to RULED_PROJECTIONS, not a silent addition.
    """
    actual = set()
    for path in _sources():
        for func in find_as_scalar_calls(path.read_text()):
            actual.add((_rel(path), func))
    unruled = actual - RULED_PROJECTIONS
    assert not unruled, (
        "UNRULED scalar projection(s) — every as_scalar() call must sit in a "
        "ruled terminal consumer backed by a bash probe: " + repr(sorted(unruled)))


def test_every_ruled_projection_still_exists():
    """No ruled row is stale (a row naming a vanished site guards nothing).

    The AGREEMENT-FORM half of the guard above: without this, deleting a
    projection would leave RULED_PROJECTIONS quietly over-permissive.
    """
    actual = set()
    for path in _sources():
        for func in find_as_scalar_calls(path.read_text()):
            actual.add((_rel(path), func))
    stale = RULED_PROJECTIONS - actual
    assert not stale, (
        "RULED_PROJECTIONS names site(s) that no longer project — remove the "
        "row or restore the call: " + repr(sorted(stale)))


def test_operand_value_str_raises_type_error():
    """``str(OperandValue)`` raises TypeError, not a shell-error type.

    TypeError specifically: PSH_STRICT_ERRORS treats an unexpected TypeError
    as an internal defect and fails LOUDLY, while a PshError/OSError/
    ValueError would be swallowed to exit 1 and an unnamed scalar re-entry
    would pass silently — exactly the failure mode this slot removed.
    """
    import pytest

    from psh.core.exceptions import PshError
    from psh.expansion.operands import OperandValue
    from psh.expansion.word_expansion_types import ExpandedField

    value = OperandValue([ExpandedField([])])
    with pytest.raises(TypeError) as exc:
        str(value)
    assert not isinstance(exc.value, PshError)
    # The message must name the remedy, or the loud failure is not actionable.
    assert "as_scalar" in str(exc.value)


def test_operand_value_is_not_a_str():
    """The type cannot be silently consumed as a string."""
    from psh.expansion.operands import OperandValue
    assert not issubclass(OperandValue, str)


# --------------------------------------------------------------------------
# Guard-the-guards: synthetic offenders the scanners MUST catch
# --------------------------------------------------------------------------

def test_guard_detects_unruled_projection():
    assert find_as_scalar_calls(
        "def sneaky():\n    return value.as_scalar()\n") == {"sneaky"}


def test_guard_detects_module_level_projection():
    assert find_as_scalar_calls("X = value.as_scalar()\n") == {"<module>"}


def test_guard_detects_nested_projection():
    """A call buried in a nested def is attributed to the nearest function,
    so wrapping a projection in a helper cannot hide it from the ruled set."""
    src = "def outer():\n    def inner():\n        return v.as_scalar()\n"
    assert find_as_scalar_calls(src) == {"inner"}


def test_guard_ignores_unrelated_calls():
    assert find_as_scalar_calls("def f():\n    return v.as_text()\n") == set()


def test_guard_detects_retired_symbol():
    assert find_retired("class OperandResult(str):\n    pass\n") == {"OperandResult"}
    assert find_retired("x = OperandResult([])\n") == {"OperandResult"}
    assert find_retired("x = OperandValue([])\n") == set()
