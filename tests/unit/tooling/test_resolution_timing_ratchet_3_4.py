"""Static ratchet: the prefix transaction seals BEFORE resolution (HIGH-3).

Sibling of ``test_command_resolution_ratchet_r3.py``, which guards a different
property. That ratchet pins WHERE a dispatch decision may be read (only
``resolve_command``, never a raw registry read). This one pins WHEN: the
prefix-assignment transaction must expand its values before the command
resolves, and must route them after.

The HIGH-3 defect was an ORDER, not a stray read. ``resolve_command`` ran
before the prefix values were expanded, so a side effect performed by a
value's expansion — ``A=$((POSIXLY_CORRECT=1)) eval …`` enabling POSIX mode —
landed after the dispatch decision it should have governed. The R3 ratchet
could not see this: every read was already going through the resolver.

Three properties, each with its OWN synthetic offender so the scanner cannot
rot into a no-op:

1. SINGLE RESOLUTION — exactly one ``resolve_command`` invocation on the
   dispatch path (a second one could observe different state).
2. REORDER — the expansion phase precedes it, i.e. no resolution before the
   transaction seals. This is the HIGH-3 property itself.
3. NO RE-EXPANSION — nothing expands after resolution. A second expansion is
   a second run of every value's side effects, which is observable
   (``RANDOM=1 b=$RANDOM c=$RANDOM`` would give ``c != b``).

The behavioural counterpart lives in test land and fails for its own reason:
``tests/conformance/bash/test_resolution_timing_conformance.py`` goes red on a
reordered executor. This file is the STATIC half — it fails on the shape even
if someone were to weaken the behavioural rows.

Only the DISPATCH path is scanned (``CommandExecutor._run_command``, the
method that owns the prefix/resolve/dispatch sequence). The introspection
callers of ``CommandResolver.resolve`` (``type`` and ``command`` builtins,
``command_resolver.py``) are QUERY paths, not dispatch, and are outside this
method by construction.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
COMMAND_PY = ROOT / "psh" / "executor" / "command.py"

# The transaction's three calls, by attribute name.
EXPAND = "expand_prefix"
RESOLVE = "resolve_command"
COMMIT = "commit_prefix"
# The one-shot composition: expanding again after resolution.
APPLY = "apply_prefix"

# The method that owns the prefix/resolve/dispatch sequence.
DISPATCH_METHOD = "_run_command"


def _dispatch_method(source: str) -> ast.FunctionDef:
    """The ``CommandExecutor._run_command`` FunctionDef node."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CommandExecutor":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name == DISPATCH_METHOD):
                    return item
    raise AssertionError(
        f"CommandExecutor.{DISPATCH_METHOD} not found — the dispatch method "
        "was renamed; re-point this ratchet rather than deleting it")


def transaction_calls(source: str) -> dict:
    """Map each transaction call name to the line numbers it is CALLED on.

    AST-based: a comment or docstring merely naming ``resolve_command`` does
    not count, and neither does the ``def resolve_command`` method itself —
    only ``ast.Call`` nodes whose callee attribute matches.
    """
    method = _dispatch_method(source)
    found: dict = {EXPAND: [], RESOLVE: [], COMMIT: [], APPLY: []}
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in found:
                found[node.func.attr].append(node.lineno)
    return found


def order_violations(source: str):
    """Return [(rule, detail)] for every transaction-order property broken."""
    calls = transaction_calls(source)
    problems = []

    if len(calls[RESOLVE]) != 1:
        problems.append((
            "single-resolution",
            f"expected exactly 1 {RESOLVE} call on the dispatch path, "
            f"found {len(calls[RESOLVE])} at {calls[RESOLVE]}"))
    if len(calls[EXPAND]) != 1:
        problems.append((
            "single-expansion",
            f"expected exactly 1 {EXPAND} call, found {len(calls[EXPAND])} "
            f"at {calls[EXPAND]}"))
    if len(calls[COMMIT]) != 1:
        problems.append((
            "single-commit",
            f"expected exactly 1 {COMMIT} call, found {len(calls[COMMIT])} "
            f"at {calls[COMMIT]}"))

    # Ordering rules need one of each to compare.
    if len(calls[RESOLVE]) == 1 and len(calls[EXPAND]) == 1:
        if calls[EXPAND][0] > calls[RESOLVE][0]:
            problems.append((
                "reorder",
                f"{RESOLVE} (line {calls[RESOLVE][0]}) runs BEFORE {EXPAND} "
                f"(line {calls[EXPAND][0]}) — resolution would read state "
                "from before the prefix values were expanded (HIGH-3)"))
    if len(calls[RESOLVE]) == 1 and len(calls[COMMIT]) == 1:
        if calls[COMMIT][0] < calls[RESOLVE][0]:
            problems.append((
                "commit-before-resolve",
                f"{COMMIT} (line {calls[COMMIT][0]}) runs BEFORE {RESOLVE} "
                f"(line {calls[RESOLVE][0]}) — the route cannot be chosen "
                "before the dispatch answer exists"))

    if calls[APPLY]:
        problems.append((
            "re-expansion",
            f"{APPLY} called on the dispatch path at {calls[APPLY]} — it "
            "expands, so the values' side effects would run a second time"))

    return problems


# --------------------------------------------------------------------------
# The ratchet itself
# --------------------------------------------------------------------------

def test_dispatch_path_transaction_order_is_intact():
    violations = order_violations(COMMAND_PY.read_text())
    assert violations == [], (
        "psh/executor/command.py broke the prefix-transaction order:\n"
        + "\n".join(f"  [{rule}] {detail}" for rule, detail in violations))


def test_the_three_transaction_calls_are_present_exactly_once():
    """The properties above are vacuous if the calls vanish entirely."""
    calls = transaction_calls(COMMAND_PY.read_text())
    assert len(calls[EXPAND]) == 1, calls
    assert len(calls[RESOLVE]) == 1, calls
    assert len(calls[COMMIT]) == 1, calls
    assert calls[EXPAND][0] < calls[RESOLVE][0] < calls[COMMIT][0], calls


def test_the_one_shot_composition_is_absent_from_the_dispatch_path():
    """``apply_prefix`` is RETAINED as the one-shot composition of the two
    phases, for callers that need no resolution in between — but it must never
    appear on the dispatch path, where it would expand a second time.

    Stated as its own assertion rather than left implicit in the
    ``re-expansion`` rule above, so the retention decision stays visibly
    conditional on this property holding.
    """
    calls = transaction_calls(COMMAND_PY.read_text())
    assert calls[APPLY] == [], (
        f"{APPLY} reappeared on the dispatch path at {calls[APPLY]} — the "
        "composition expands, so every value's side effects would run twice")


# --------------------------------------------------------------------------
# Forcing tests — one synthetic offender per rule, each tripping ONLY its own
# --------------------------------------------------------------------------

def _synthetic(body: str) -> str:
    return (
        "class CommandExecutor:\n"
        f"    def {DISPATCH_METHOD}(self, node, context):\n"
        + body
    )


GOOD_BODY = (
    "        staged = self.assignments.expand_prefix(raw)\n"
    "        resolved = self.resolve_command(normalized, overlay, context)\n"
    "        prefix = self.assignments.commit_prefix(staged, False)\n"
)


def _rules(source):
    return {rule for rule, _ in order_violations(source)}


def test_the_good_shape_has_no_violations():
    """The forcing tests are only meaningful against a clean baseline."""
    assert order_violations(_synthetic(GOOD_BODY)) == []


def test_ratchet_flags_a_REORDER_offender():
    """Resolution reachable before the transaction seals — the HIGH-3 shape."""
    offender = _synthetic(
        "        resolved = self.resolve_command(normalized, overlay, context)\n"
        "        staged = self.assignments.expand_prefix(raw)\n"
        "        prefix = self.assignments.commit_prefix(staged, False)\n"
    )
    assert _rules(offender) == {"reorder"}


def test_ratchet_flags_a_SECOND_RESOLUTION_offender():
    """Two dispatch decisions could observe different state."""
    offender = _synthetic(
        GOOD_BODY
        + "        again = self.resolve_command(normalized, overlay, context)\n"
    )
    assert _rules(offender) == {"single-resolution"}


def test_ratchet_flags_a_RE_EXPANSION_offender():
    """``apply_prefix`` expands; calling it here re-runs the side effects."""
    offender = _synthetic(
        GOOD_BODY
        + "        again = self.assignments.apply_prefix(raw, False)\n"
    )
    assert _rules(offender) == {"re-expansion"}


def test_ratchet_flags_a_COMMIT_BEFORE_RESOLVE_offender():
    """The route cannot be chosen before the dispatch answer exists."""
    offender = _synthetic(
        "        staged = self.assignments.expand_prefix(raw)\n"
        "        prefix = self.assignments.commit_prefix(staged, False)\n"
        "        resolved = self.resolve_command(normalized, overlay, context)\n"
    )
    assert _rules(offender) == {"commit-before-resolve"}


def test_ratchet_flags_a_DOUBLE_EXPANSION_offender():
    offender = _synthetic(
        "        staged = self.assignments.expand_prefix(raw)\n"
        "        staged2 = self.assignments.expand_prefix(raw)\n"
        "        resolved = self.resolve_command(normalized, overlay, context)\n"
        "        prefix = self.assignments.commit_prefix(staged, False)\n"
    )
    assert _rules(offender) == {"single-expansion"}


def test_ratchet_ignores_comments_and_docstrings():
    """Prose naming the calls must not trip the scan (AST, not text)."""
    prose = _synthetic(
        '        """Mentions resolve_command and expand_prefix in prose."""\n'
        "        # resolve_command(...) then expand_prefix(...) — a comment\n"
        + GOOD_BODY
    )
    assert order_violations(prose) == []


def test_scanner_raises_when_the_dispatch_method_disappears():
    """A rename must fail loudly rather than silently scanning nothing."""
    with pytest.raises(AssertionError):
        transaction_calls("class CommandExecutor:\n    pass\n")
