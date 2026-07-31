"""Triad guards for the substitution-origin CONSUMER (slot 2.4, ruling R5-D).

The producer side is guarded by ``test_syntax_template_guards.py``; this is the
consumer half. Three protected facts, each with a synthetic offender that is
actually RUN here, so every guard is proven to BITE rather than merely to pass:

1. ONE RAISE SITE — ``SubstitutionSyntaxAbort`` is constructed only inside the
   consumer helper ``SourceProcessor._substitution_syntax_abort``. A second
   raise site would bypass the interactive gate and the ``nested`` computation.
2. ONLY THE SANCTIONED NON-FORK CATCHERS — the top-level CONSUMER
   (``SourceProcessor.execute_as_main``) and the TEARDOWN SWALLOW
   (``TrapManager.execute_exit_trap``). The second of those went 0 -> 1 *inside
   this slot* and was caught by a verification BOUNCE rather than by any
   executable check; this guard is the check that should have caught it. A
   THIRD catcher would silently re-contain the fatality in a frame bash does
   not.
3. NO RE-DERIVED STATUS MAPPING — the abort's status constants live only in the
   two policy functions in ``core/internal_errors.py``. A frame that compares
   or re-derives them is how the channel rule drifts out of one place.
"""

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

# The single sanctioned raise site, and the sanctioned catchers WITH THEIR
# ROLES. The two catchers are different in kind and both are load-bearing:
#   * execute_as_main CONSUMES the abort into the process status (the ordinary
#     path). Removing it would let the abort reach the interpreter.
#   * execute_exit_trap SWALLOWS it at teardown, where there is nothing left to
#     abort. This one went 0 -> 1 inside slot 2.4 and was caught by a
#     verification BOUNCE rather than by any executable check.
# A THIRD catcher is the thing to prevent: it would silently re-contain the
# fatality in a frame bash does not.
RAISE_SITE = ("psh/scripting/source_processor.py", "_substitution_syntax_abort")
CATCH_SITES = {
    ("psh/scripting/source_processor.py", "execute_as_main"): "consumer",
    ("psh/core/trap_manager.py", "execute_exit_trap"): "teardown swallow",
}


def _py_files():
    return sorted(p for p in PSH.rglob("*.py") if "__pycache__" not in str(p))


def _enclosing_func(tree, lineno):
    """Name of the innermost function containing ``lineno`` (or None)."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:
                    best = node
    return best.name if best else None


def _find_raise_sites(source, tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            call = node.exc
            name = None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                name = call.func.id
            elif isinstance(call, ast.Name):
                name = call.id
            if name == "SubstitutionSyntaxAbort":
                out.append((node.lineno, _enclosing_func(tree, node.lineno)))
    return out


def _find_catch_sites(source, tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            names = []
            t = node.type
            for sub in (t.elts if isinstance(t, ast.Tuple) else [t]):
                if isinstance(sub, ast.Name):
                    names.append(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.append(sub.attr)
            if "SubstitutionSyntaxAbort" in names:
                out.append((node.lineno, _enclosing_func(tree, node.lineno)))
    return out


# ---------------------------------------------------------------- guard 1

def test_only_one_raise_site_for_the_abort():
    found = []
    for path in _py_files():
        src = path.read_text()
        if "SubstitutionSyntaxAbort" not in src:
            continue
        for lineno, func in _find_raise_sites(src, ast.parse(src)):
            found.append((str(path.relative_to(ROOT)), func, lineno))
    assert len(found) == 1, found
    rel, func, _ = found[0]
    assert (rel, func) == RAISE_SITE, found


def test_guard1_bites_on_a_synthetic_second_raise_site():
    offender = (
        "from psh.core.exceptions import SubstitutionSyntaxAbort\n"
        "def sneaky():\n"
        "    raise SubstitutionSyntaxAbort(nested=True)\n"
    )
    tree = ast.parse(offender)
    found = _find_raise_sites(offender, tree)
    assert found == [(3, "sneaky")], found      # the detector SEES it


# ---------------------------------------------------------------- guard 2

def test_only_the_sanctioned_non_fork_catchers_exist():
    found = {}
    for path in _py_files():
        src = path.read_text()
        if "SubstitutionSyntaxAbort" not in src:
            continue
        for lineno, func in _find_catch_sites(src, ast.parse(src)):
            found[(str(path.relative_to(ROOT)), func)] = lineno
    assert set(found) == set(CATCH_SITES), (sorted(found), sorted(CATCH_SITES))


def test_guard2_bites_on_a_synthetic_second_catcher():
    offender = (
        "from psh.core.exceptions import SubstitutionSyntaxAbort\n"
        "def swallow():\n"
        "    try:\n"
        "        pass\n"
        "    except SubstitutionSyntaxAbort:\n"
        "        pass\n"
    )
    found = _find_catch_sites(offender, ast.parse(offender))
    assert found == [(5, "swallow")], found     # the detector SEES it
    # ...and a tuple-form catcher is caught too, which is how it would most
    # plausibly be smuggled in beside an existing handler.
    tup = (
        "from psh.core.exceptions import SubstitutionSyntaxAbort\n"
        "def swallow2():\n"
        "    try:\n"
        "        pass\n"
        "    except (ValueError, SubstitutionSyntaxAbort):\n"
        "        pass\n"
    )
    assert _find_catch_sites(tup, ast.parse(tup)) == [(5, "swallow2")]


# ---------------------------------------------------------------- guard 3

# The abort's status constants may appear ONLY in the two policy functions.
_POLICY_FUNCS = {"substitution_abort_status", "substitution_child_abort_status"}
_POLICY_FILE = "psh/core/internal_errors.py"
# A frame re-deriving the mapping looks like a comparison against the abort's
# own statuses next to the outcome's name.
_REDERIVE = re.compile(r"SubstitutionSyntaxAbort[^\n]*\b(127|== ?2|== ?1)\b")


def test_status_mapping_is_not_re_derived_at_frames():
    offenders = []
    for path in _py_files():
        rel = str(path.relative_to(ROOT))
        src = path.read_text()
        if "SubstitutionSyntaxAbort" not in src:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if _REDERIVE.search(line):
                offenders.append((rel, i, line.strip()))
    assert not offenders, offenders
    # ...and the SUBSTITUTION-abort policy really is where the guard says.
    # (Scoped to these two functions on purpose: internal_errors.py also holds
    # unrelated policies with their own 127 — e.g. fatal_expansion_status —
    # and a guard that claimed every 127 in the file belongs to this family
    # would fire on legitimate neighbours, which is a mis-specified guard
    # rather than a finding.)
    pol = (ROOT / _POLICY_FILE).read_text()
    tree = ast.parse(pol)
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in (1, 2, 127):
            fn = _enclosing_func(tree, node.lineno)
            if fn in _POLICY_FUNCS:
                seen.add(node.value)
    assert {1, 2, 127} <= seen, seen


def test_guard3_bites_on_a_synthetic_re_derivation():
    offender = "    if isinstance(e, SubstitutionSyntaxAbort): return 127\n"
    assert _REDERIVE.search(offender), offender


@pytest.mark.parametrize("name,expected", [
    ("substitution_abort_status", True),
    ("substitution_child_abort_status", True),
])
def test_policy_functions_exist_where_the_guard_expects_them(name, expected):
    pol = (ROOT / _POLICY_FILE).read_text()
    assert ("def %s(" % name in pol) is expected
