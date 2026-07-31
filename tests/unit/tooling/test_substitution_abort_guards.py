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
   not. Named catchers only, bare and attribute-qualified: a bare ``except:``
   swallowing everything is a broader defect with its own ratchets
   (``test_broad_valueerror_catch_q2.py``, ``test_subscript_no_broad_except.py``)
   and is deliberately not this guard's business.
3. NO RE-DERIVED STATUS MAPPING — the abort's status constants live only in the
   two policy functions in ``core/internal_errors.py``. A frame that compares
   or re-derives them is how the channel rule drifts out of one place. Detected
   structurally (see ``_find_rederive_sites``); the line-shaped regex this
   replaced missed the two-line spelling of its own offender.
"""

import ast
import pathlib

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


ABORT = "SubstitutionSyntaxAbort"


def _local_aliases(tree):
    """The local names a module STATICALLY binds to the abort.

    Two rebinding forms are resolved, both found by verifiers against earlier
    versions of these guards:

    * an IMPORT alias — ``from psh.core.exceptions import
      SubstitutionSyntaxAbort as SSA`` (round-6 finding: every guard stayed
      green);
    * an ASSIGNMENT alias — ``SSA = SubstitutionSyntaxAbort`` (round-7
      finding: same). Chains resolve too, since each pass over the tree feeds
      the next.

    KNOWN LIMIT, stated rather than implied — this is deliberately NOT "every
    local name that refers to the abort", which is the universal the round-7
    verifier falsified in one line. A binding the reader cannot see WITHOUT
    executing the module is out of reach here: a name held in a list/dict/
    tuple, one produced by ``getattr``, one bound inside a function that runs
    at import, or a runtime ``importlib`` lookup. Those belong to the
    broad-catch ratchets and to review, not to a static name resolver.
    """
    names = {ABORT}
    for _ in range(3):                     # resolve short alias CHAINS
        before = len(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == ABORT and alias.asname:
                        names.add(alias.asname)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith("." + ABORT) and alias.asname:
                        names.add(alias.asname)
            elif isinstance(node, ast.Assign):
                if _exc_name(node.value) in names:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            names.add(target.id)
        if len(names) == before:
            break
    return names


def _exc_name(node):
    """The exception NAME a raise/type expression denotes, bare or qualified.

    Both spellings must be seen: ``SubstitutionSyntaxAbort`` and
    ``exceptions.SubstitutionSyntaxAbort`` (the attribute-qualified form is
    how a second raise site would most plausibly appear — reaching for the
    module to dodge an import cycle). An IMPORT ALIAS is resolved separately,
    by ``_local_aliases``, because the alias is invisible at the use site.
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _find_raise_sites(source, tree):
    out = []
    names = _local_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            if _exc_name(node.exc) in names:
                out.append((node.lineno, _enclosing_func(tree, node.lineno)))
    return out


def _find_catch_sites(source, tree):
    out = []
    aliases = _local_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            t = node.type
            names = [_exc_name(sub)
                     for sub in (t.elts if isinstance(t, ast.Tuple) else [t])]
            if aliases.intersection(names):
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
_STATUS_CONSTANTS = frozenset((1, 2, 127))


def _mentions_abort(node, aliases=frozenset({ABORT})):
    """True if the expression names the abort, under any of its local names."""
    return any(_exc_name(sub) in aliases
               for sub in ast.walk(node)
               if isinstance(sub, (ast.Name, ast.Attribute)))


def _find_rederive_sites(tree):
    """Branches KEYED ON the abort that produce a status constant themselves.

    Structural, not textual: an ``if``/``elif`` whose test names the abort, or
    an ``except`` clause catching it, whose body then returns or assigns one of
    the abort's own statuses. The predecessor of this detector was a
    single-line regex, so the most natural offender —

        if isinstance(e, SubstitutionSyntaxAbort):
            return 127

    — evaded it purely by being two lines (round-5 verifier finding). Reading
    the tree removes the line-shape dependence entirely.

    KNOWN LIMIT, stated rather than implied: a constant laundered through a
    value computed elsewhere (``return _STATUS[kind]``) is not re-derivation
    this guard can see. It detects the mapping written AT the frame, which is
    the drift this slot actually suffered.
    """
    out = []
    aliases = _local_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            keyed = _mentions_abort(node.test, aliases)
        elif isinstance(node, ast.ExceptHandler) and node.type is not None:
            keyed = _mentions_abort(node.type, aliases)
        else:
            continue
        if not keyed:
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Return, ast.Assign, ast.AnnAssign)):
                    value = sub.value
                    if (isinstance(value, ast.Constant)
                            and value.value in _STATUS_CONSTANTS):
                        out.append((sub.lineno, value.value))
    return out


def test_status_mapping_is_not_re_derived_at_frames():
    offenders = []
    for path in _py_files():
        rel = str(path.relative_to(ROOT))
        src = path.read_text()
        if "SubstitutionSyntaxAbort" not in src:
            continue
        for lineno, value in _find_rederive_sites(ast.parse(src)):
            offenders.append((rel, lineno, value))
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


@pytest.mark.parametrize("label,offender", [
    ("one line",
     "def frame(e):\n"
     "    if isinstance(e, SubstitutionSyntaxAbort): return 127\n"),
    # The round-5 verifier's evasion shape: identical meaning, two lines. The
    # regex this detector replaced could not see it.
    ("two lines",
     "def frame(e):\n"
     "    if isinstance(e, SubstitutionSyntaxAbort):\n"
     "        return 127\n"),
    ("attribute-qualified",
     "def frame(e):\n"
     "    if isinstance(e, exceptions.SubstitutionSyntaxAbort):\n"
     "        return 127\n"),
    ("through a local",
     "def frame(e):\n"
     "    try:\n"
     "        run()\n"
     "    except SubstitutionSyntaxAbort:\n"
     "        status = 2\n"
     "        return status\n"),
])
def test_guard3_bites_on_a_synthetic_re_derivation(label, offender):
    assert _find_rederive_sites(ast.parse(offender)), (label, offender)


@pytest.mark.parametrize("label,offender,detector", [
    ("aliased raise",
     "from psh.core.exceptions import SubstitutionSyntaxAbort as SSA\n"
     "def sneaky():\n"
     "    raise SSA(nested=True)\n",
     "raise"),
    ("aliased catch",
     "from psh.core.exceptions import SubstitutionSyntaxAbort as SSA\n"
     "def swallow():\n"
     "    try:\n"
     "        pass\n"
     "    except SSA:\n"
     "        pass\n",
     "catch"),
    ("assignment-aliased raise",
     "from psh.core.exceptions import SubstitutionSyntaxAbort\n"
     "SSA = SubstitutionSyntaxAbort\n"
     "def sneaky():\n"
     "    raise SSA(nested=True)\n",
     "raise"),
    ("aliased re-derivation",
     "from psh.core.exceptions import SubstitutionSyntaxAbort as SSA\n"
     "def frame(e):\n"
     "    if isinstance(e, SSA):\n"
     "        return 127\n",
     "rederive"),
])
def test_guards_resolve_import_aliases(label, offender, detector):
    """An import alias rebinds the class to a name the use site never spells.

    A round-6 verifier inserted `from … import SubstitutionSyntaxAbort as SSA`
    under psh/ and ALL twelve guards stayed green — the detectors matched
    Name and Attribute but never consulted the module's import bindings.
    Each detector now resolves aliases per module, and each is held to it
    here."""
    tree = ast.parse(offender)
    found = {"raise": _find_raise_sites(offender, tree),
             "catch": _find_catch_sites(offender, tree),
             "rederive": _find_rederive_sites(tree)}[detector]
    assert found, (label, detector, offender)


def test_guard1_bites_on_an_attribute_qualified_raise_site():
    """The raise detector must be symmetric with the catch detector.

    ``raise exceptions.SubstitutionSyntaxAbort(...)`` — the spelling a second
    raise site would most plausibly wear, since reaching for the module is how
    one dodges an import cycle — was invisible to the bare-Name-only detector
    (round-5 verifier finding).
    """
    offender = (
        "from psh.core import exceptions\n"
        "def sneaky():\n"
        "    raise exceptions.SubstitutionSyntaxAbort(nested=True)\n"
    )
    assert _find_raise_sites(offender, ast.parse(offender)) == [(3, "sneaky")]


@pytest.mark.parametrize("name,expected", [
    ("substitution_abort_status", True),
    ("substitution_child_abort_status", True),
])
def test_policy_functions_exist_where_the_guard_expects_them(name, expected):
    pol = (ROOT / _POLICY_FILE).read_text()
    assert ("def %s(" % name in pol) is expected
