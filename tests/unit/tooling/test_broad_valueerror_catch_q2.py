"""Ratchet: no NEW broad ValueError/TypeError catch used as control flow
(campaign Q2, §13, "broad ValueError/TypeError catches used as expected control
flow").

Under suite-wide ``strict-errors``, a ``ValueError``/``TypeError`` is an INTERNAL
DEFECT unless deliberately driven. The anti-pattern #20 named is a BROAD
``except ValueError``/``except (ValueError, TypeError, ...)`` — one that does NOT
re-raise — wrapping a MULTI-operation try body, so a defect deep in the body is
silently swallowed as expected control flow. A NARROW catch (a single
``int()``/``float()`` conversion, or a documented-signal stdlib primitive like
``signal.signal``/``os.fstat``/``strcoll``/``evaluate_arithmetic``) is legitimate.

**Detector line.** A candidate is a ``Try`` with a handler that CATCHES VT, does
NOT re-raise (no ``raise`` anywhere in the handler — a bare re-raise and a
translate-and-raise both surface the error), and whose try body is BROAD
(``> 1`` statement OR ``>= 5`` distinct call targets — the second disjunct
catches the single-compound-statement masker whose one ``if/elif`` hides many
calls). Every candidate is classified here as BROAD_MASKING (the known debt) or
NARROW_SAFE; a NEW candidate fails ``test_no_unclassified_vt_catch`` (triage it).
BROAD_MASKING is SHRINK-ONLY — narrowing a site (tighten the try body or the
exception type) removes its entry; the narrowings themselves are a deferred
behavioral-campaign carry (they change what a genuine internal defect does, so
they are NOT in Q2's zero-behavior-change scope).

Q2 nit-1 hardening: the QUALIFIED-except shape (``except mod.ValueError``) is now
caught (``_exc_name`` reads the Attribute attr). Declared OUT OF SCOPE (no live
instance): an exception caught under an IMPORT ALIAS (``from x import ValueError
as VE; except VE``) — the name no longer reads ``ValueError``; and a
NESTED-swallow re-raise (a ``raise`` inside an inner ``try`` in the handler that
does not actually re-raise the outer error) — the ``raise``-anywhere check treats
it conservatively as re-raising.

THIRD shape, now CLOSED (D-5C.1-s1, remediation 5C.2): a catch of an in-tree
SUBCLASS of ``ValueError``/``TypeError``. ``_catches_vt`` matched literal NAMES,
so ``psh/utils/ast_debug.py``'s ``except UnknownASTFormat`` — where
``UnknownASTFormat(ValueError)`` — was invisible even though its try body is
broad by the ``>= 5`` call-target disjunct. 5C.1 created that first live
instance and RECORDED the shape rather than widening the detector in the same
slot, because a guard widened by the author of its first evasion gets tuned to
accept what that author just wrote.

The detector now builds the TRANSITIVE closure of in-tree classes deriving from
``ValueError``/``TypeError`` (tree-wide, since a subclass is usually defined in
one module and caught in another) and treats a catch of any of them as a VT
catch. The full-tree re-run surfaced exactly ONE new candidate — the ast_debug
site above — which is classified NARROW_SAFE: the caught type is this module's
own, raised at one site inside the body for one condition, so a formatter defect
cannot present as it. The widening is deliberately SPECIFIC and has controls
saying so: a subclass of a NON-VT exception is not flagged, and the subclass
edge does not bypass the BROAD test.

Still OUT OF SCOPE (no live instance): the IMPORT ALIAS shape above, and a
subclass whose base is itself reached only through an alias.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"


def _exc_name(node):
    """The bare exception name for a handler-type element: ``ValueError`` for a
    Name, ``ValueError`` for the qualified ``mod.ValueError`` Attribute (Q2 nit-1
    — the qualified-except evasion). None otherwise."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _exc_names(handler):
    t = handler.type
    if isinstance(t, ast.Tuple):
        return tuple(n for n in (_exc_name(e) for e in t.elts) if n is not None)
    n = _exc_name(t)
    return (n,) if n is not None else ()


VT_ROOTS = ("ValueError", "TypeError")


def _class_bases(tree):
    """{class name: [base names]} for every ClassDef in one parsed module."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            out[n.name] = [b for b in (_exc_name(b) for b in n.bases)
                           if b is not None]
    return out


def _vt_subclass_closure(bases_by_name, seed=()):
    """Names deriving TRANSITIVELY from ValueError/TypeError.

    Transitive rather than direct because a two-hop subclass hides the shape
    just as well as a one-hop one. Fixpoint rather than recursion so a cyclic
    or forward-referencing definition cannot spin.
    """
    known = set(VT_ROOTS) | set(seed)
    closure = set(seed)
    changed = True
    while changed:
        changed = False
        for name, bases in bases_by_name.items():
            if name not in closure and any(b in known or b in closure
                                           for b in bases):
                closure.add(name)
                known.add(name)
                changed = True
    return frozenset(closure)


def _tree_vt_subclasses():
    """Every in-tree class deriving from ValueError/TypeError, whole of psh/.

    Tree-wide because a subclass is typically defined in one module and caught
    in another; a per-module closure would miss exactly that split.
    """
    bases = {}
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        bases.update(_class_bases(ast.parse(path.read_text())))
    return _vt_subclass_closure(bases)


def _catches_vt(handler, vt_names=frozenset(VT_ROOTS)):
    names = _exc_names(handler)
    return any(n in vt_names for n in names)


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (
        f.id if isinstance(f, ast.Name) else "?")


def broad_vt_candidates(src, relpath, vt_names=()):
    """Return [(relpath, exc_names, call_names)] for every broad,
    non-re-raising VT catch (the candidate signature, line-independent).

    ``vt_names`` supplies subclass names known from OUTSIDE this source (the
    tree-wide set for a live scan). Classes defined in ``src`` itself are
    folded in here, so a module that defines its own ``ValueError`` subclass
    and catches it is seen without the caller having to pre-compute anything.
    """
    tree = ast.parse(src)
    vt = _vt_subclass_closure(_class_bases(tree), seed=vt_names)
    vt = frozenset(vt | set(VT_ROOTS))
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Try):
            continue
        calls = sorted({_call_name(c) for st in n.body for c in ast.walk(st)
                        if isinstance(c, ast.Call)})
        broad = len(n.body) > 1 or len(calls) >= 5
        for h in n.handlers:
            if not _catches_vt(h, vt):
                continue
            if any(isinstance(x, ast.Raise) for x in ast.walk(h)):
                continue
            if broad:
                out.append((relpath, _exc_names(h), tuple(calls)))
    return out


def _live_candidates():
    vt = _tree_vt_subclasses()
    found = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        found.extend(broad_vt_candidates(path.read_text(), rel, vt_names=vt))
    return set(found)


# --- The known broad maskers (DEBT — shrink-only). Each: what the try wraps. --
BROAD_MASKING = {
    # SHRUNK by remediation 5C.1 (MEDIUM-12, ruling (b)): the popd, `dirs -N`
    # and disown entries are GONE. Each try body now wraps ONLY its int()
    # conversion — the shape the sibling `_popd_no_cd` already used — so none
    # of the three is a candidate any more, and
    # test_classification_has_no_stale_entries is what forces the entries out
    # rather than leaving them as decoration.
    #
    # Two-axis proven: 32 non-defect cells (valid AND invalid INPUT — invalid
    # input is not a defect) byte-identical base vs tip; and a seeded defect in
    # each former try body (DirectoryStack.pop / DirectoryStack.size /
    # get_job_by_pid), which base reported to the user as "invalid index
    # argument" / "not a valid job specification or process id", now SURFACES.
    #
    # Also SHRUNK by 5C.1: the parse_tree.py VT/AttributeError pipeline net and
    # the read_builtin.py whole-record-engine VE net. Both were FORCED and
    # measured DEFECT-ONLY before removal — 124 parse-tree cells (4 formats x
    # 31 inputs) and 19 hostile `read` cells (7 malformed-UTF-8 shapes x the
    # -N/-n/-d/-r/-a/IFS option axis) never reached either handler body, while
    # a SEEDED defect did, so the zero is a property of the production path
    # rather than of an inert probe. parse_tree keeps its `except ParseError`
    # leg (the real user-input class) and read_builtin keeps its
    # `except OSError` leg (the real `read error:` diagnostic).
    #
    # SHRUNK by remediation 3.5 (MEDIUM-12b, ruling (b)): the `[[ ]]` entry
    # ("psh/executor/core.py", ("ValueError","TypeError","OSError"),
    #  ("TestExpressionEvaluator","evaluate")) is gone. Its reason read "it
    # should catch a narrow evaluator error type, not raw VT" — it now does:
    # the handler is `except (TestExpressionError, OSError)`, the evaluator's
    # invalid-regex raiser is typed, and its three can't-happen branches raise
    # RuntimeError. The site is no longer a candidate at all, which is why the
    # entry had to go: test_classification_has_no_stale_entries forces it.
    # JUSTIFIED-KEEP with a CORRECTED reason (remediation 5C.1, ruling (b)).
    # The previous reason pleaded the combinator parser's quality bar, which is
    # true of the module but is not why this catch is acceptable — it reads as
    # an excuse for debt. The honest reason is the method's contract, and it is
    # measured: `can_parse` has ZERO production callers (the shell entry points
    # call only `parse`/`parse_with_heredocs`; the only callers in the tree are
    # tests/unit/parser/combinators/test_parser_integration.py and
    # tests/regression/test_parser_review_fixes.py). It is a test-facing
    # can-this-parse PROBE whose whole contract is to answer False rather than
    # raise, so a catch-and-return-False IS the correct implementation of what
    # it promises, not a masked defect on a production path.
    ("psh/parser/combinators/parser.py",
     ("AttributeError", "IndexError", "TypeError", "ParseError"),
     ("_prepare_tokens", "len", "parse")):
        "can_parse is a TEST-FACING probe with zero production callers, whose "
        "documented contract is to return False rather than raise — the broad "
        "catch IS that contract, not a masked defect. Verified by grep: the "
        "shell entry points call only parse/parse_with_heredocs. If a "
        "production caller ever appears, this entry must be re-triaged.",
    # SHRUNK by remediation 5C.1: the utils/ast_debug.py formatter-selection
    # net. Its VE leg was NOT dead — it was the module's OWN
    # `raise ValueError("unknown AST format ...")`, reachable via
    # PSH_AST_FORMAT=bogus — so the fix was to TYPE the raise
    # (`UnknownASTFormat`) and catch only that, rather than delete the handler.
    # Two-axis proven: the user-reachable unknown-format warning + fallback is
    # byte-identical base vs tip, and a seeded TypeError inside
    # ASTPrettyPrinter.visit that base downgraded to that same warning now
    # SURFACES.
}

# --- Candidates that are actually NARROW/safe (single conversion or one -------
#     documented-signal primitive whose VT IS its contract). ------------------
NARROW_SAFE = {
    # First candidate visible only because the detector now follows in-tree
    # ValueError-subclass edges (D-5C.1-s1). The body IS broad by the
    # call-target disjunct, but the caught type is this module's OWN, raised
    # at exactly one site inside that body for exactly one condition (an
    # out-of-vocabulary PSH_AST_FORMAT). No formatter defect can present as
    # this type, which is the whole point of 5C.1 having typed the raise.
    ("psh/utils/ast_debug.py", ("UnknownASTFormat",),
     ("ASTDotGenerator", "ASTPrettyPrinter", "UnknownASTFormat", "print",
      "render", "to_dot", "visit")):
        "module's own typed raise, one site in the body, one condition "
        "(unknown PSH_AST_FORMAT) — a formatter defect cannot present as it",
    ("psh/builtins/input_reader.py", ("OSError", "AttributeError", "ValueError"),
     ("InputCursor", "fstat")):
        "os.fstat's OSError/ValueError is its documented signal (fd validity)",
    ("psh/builtins/read_builtin.py", ("OSError", "AttributeError", "ValueError"),
     ("fstat",)):
        "os.fstat documented-signal probe",
    ("psh/builtins/read_builtin.py", ("OSError", "ValueError", "AttributeError"),
     ("_should_use_sys_stdin", "bool", "getattr", "isatty")):
        "stdin-detection probe: isatty/getattr on a possibly-detached stream",
    ("psh/builtins/test_command.py", ("ValueError", "OSError"),
     ("int", "isatty")):
        "int() conversion + isatty probe (documented signals)",
    ("psh/core/internal_errors.py", ("OSError", "ValueError"),
     ("error_location_prefix", "get", "print", "print_exc")):
        "defensive around ERROR-REPORTING output (print to a possibly-broken "
        "stream) — this IS the internal-defect reporter; it must not itself "
        "raise a new defect",
    ("psh/core/locale_service.py", ("ValueError", "Error"), ("strcoll",)):
        "_locale.strcoll's ValueError/locale.Error is its documented signal "
        "(locale collate); the qualified locale.Error is now seen (nit-1)",
    ("psh/core/trap_manager.py", ("OSError", "ValueError"),
     ("getsignal", "signal")):
        "signal.signal/getsignal documented signal (invalid/uncatchable signal)",
    ("psh/executor/child_policy.py", ("OSError", "ValueError"),
     ("getpid", "kill", "signal")):
        "os.kill/signal.signal documented signal",
    # SHRUNK by remediation 3.5 (MEDIUM-12b, ruling (a)): the two
    # `evaluate_arithmetic` entries — control_flow.py's four-name tuple (the
    # for(( )) init/condition/update legs) and core.py's ("ValueError",
    # "ArithmeticError") — are gone. Their reason claimed "evaluate_arithmetic's
    # VE is a user-reachable arithmetic error"; that was FALSE. A bare
    # ValueError cannot escape evaluate_arithmetic at all: its inner converter
    # (expansion/arithmetic/evaluator.py) turns every user-reachable VE into
    # ShellArithmeticError, so the VE legs could only ever catch an internal
    # defect. Evidence: a 200-cell user-reachable corpus under strict-errors
    # produced zero hits, and per-leg forcing on the real path showed the legs
    # firing only for an injected VE. The VE names are dropped from all four
    # handlers; what remains catches ArithmeticError (and the typed assignment
    # errors), so none of them is a VT candidate any more.
    ("psh/executor/core.py", ("OSError", "ValueError"), ("flush", "write")):
        "stream flush/write documented signal (closed/broken stream)",
    ("psh/executor/subshell.py", ("OSError", "ValueError"), ("flush",)):
        "stream flush documented signal",
    ("psh/expansion/brace_expansion.py", ("ValueError",), ("int",)):
        "int() sequence-bound conversion",
    ("psh/interactive/signal_manager.py", ("OSError", "ValueError"),
     ("getsignal", "signal")):
        "signal.signal/getsignal documented signal",
    ("psh/utils/printf_formatter.py", ("ValueError", "OverflowError"),
     ("float", "fromhex", "match")):
        "float()/float.fromhex() numeric conversion in the printf %-engine",
}


def test_no_unclassified_vt_catch():
    """Every broad, non-re-raising VT catch is classified (BROAD_MASKING or
    NARROW_SAFE). A NEW one must be triaged — narrow it, or classify it here."""
    live = _live_candidates()
    classified = set(BROAD_MASKING) | set(NARROW_SAFE)
    new = sorted(live - classified)
    assert not new, (
        "NEW broad ValueError/TypeError catch. If the body could raise VT from "
        "a nested call bug, NARROW it (tighten the try body / exception type). "
        "If it is genuinely narrow, add it to NARROW_SAFE with the reason:\n  "
        + "\n  ".join(map(str, new)))


def test_classification_has_no_stale_entries():
    """Shrink-only bookkeeping: every classified signature still exists live."""
    live = _live_candidates()
    stale = sorted((set(BROAD_MASKING) | set(NARROW_SAFE)) - live)
    assert not stale, (
        "classified VT-catch signatures with no live counterpart (narrowed / "
        f"moved) — prune them:\n  " + "\n  ".join(map(str, stale)))


def test_broad_masking_only_shrinks():
    """The known-masker set may only shrink (a narrowing removes its entry).
    A candidate that migrated from NARROW into a BROAD shape would surface via
    test_no_unclassified_vt_catch, never by silently growing this set."""
    live = _live_candidates()
    assert set(BROAD_MASKING) <= live, (
        "a BROAD_MASKING entry vanished from the tree without its ledger entry "
        "being pruned — reconcile.")


def test_every_broad_entry_has_specific_reason():
    for key, reason in BROAD_MASKING.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 40, (
            f"BROAD_MASKING {key} needs a specific reason (what it wraps)")


def test_detector_is_not_vacuous():
    assert _live_candidates(), "detector found no candidates — it cannot bite"


# --- synthetic offenders -----------------------------------------------------

def test_offender_broad_multistatement_catch_is_flagged():
    src = (
        "def f(a):\n"
        "    try:\n"
        "        n = int(a)\n"
        "        do_something(n)\n"          # 2nd statement -> broad
        "        commit(n)\n"
        "    except ValueError:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert cands and cands[0][1] == ("ValueError",)


def test_offender_compound_single_statement_masker_is_flagged():
    """The 1-statement if/elif with many calls (the ast_debug.py shape)."""
    src = (
        "def f(x):\n"
        "    try:\n"
        "        return a(x) if p(x) else b(x) if q(x) else c(x) if r(x) else d(x)\n"
        "    except (ValueError, TypeError):\n"
        "        return None\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert cands, "the >=5-distinct-call disjunct must catch the compound masker"


def test_offender_qualified_except_is_flagged():
    """Q2 nit-1: `except mod.ValueError` (qualified) with a broad body is caught
    (it evaded the Name-only exception matcher)."""
    src = (
        "import builtins\n"
        "def f(a):\n"
        "    try:\n"
        "        x = s1(a)\n"
        "        s2(x)\n"
        "        s3(x)\n"
        "    except builtins.ValueError:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert cands, "qualified except mod.ValueError must be caught"


def test_offender_in_tree_subclass_except_is_flagged():
    """D-5C.1-s1: `except MyErr` where `MyErr(ValueError)` is now caught.

    The evasion the name-based matcher could not see: a broad body behind a
    subclass-typed catch. 5C.1 created the first live instance and recorded
    the shape rather than widening the detector in the slot that created it.
    """
    src = (
        "class MyErr(ValueError):\n"
        "    pass\n"
        "def f(a):\n"
        "    try:\n"
        "        x = s1(a)\n"
        "        s2(x)\n"
        "        s3(x)\n"
        "    except MyErr:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert cands, "a catch of an in-tree ValueError subclass must be caught"


def test_offender_transitive_subclass_except_is_flagged():
    """Two hops hide the shape as well as one, so the closure is transitive."""
    src = (
        "class Mid(ValueError):\n"
        "    pass\n"
        "class Leaf(Mid):\n"
        "    pass\n"
        "def f(a):\n"
        "    try:\n"
        "        x = s1(a)\n"
        "        s2(x)\n"
        "        s3(x)\n"
        "    except Leaf:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert cands, "a two-hop ValueError subclass must be caught"


def test_control_non_vt_subclass_except_is_not_flagged():
    """CONTROL: the widening is SPECIFIC, not a blanket on custom exceptions.

    Without this, a detector that flagged every ``except SomeClass`` would
    pass the two offender arms above while drowning the ratchet in noise —
    and the noise is what makes a ratchet get allowlisted into uselessness.
    """
    src = (
        "class NotVT(RuntimeError):\n"
        "    pass\n"
        "def f(a):\n"
        "    try:\n"
        "        x = s1(a)\n"
        "        s2(x)\n"
        "        s3(x)\n"
        "    except NotVT:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert not cands, (
        "a subclass of a NON-VT exception must not be flagged: "
        f"{cands}")


def test_control_subclass_with_a_narrow_body_is_not_flagged():
    """CONTROL: the subclass edge does not bypass the BROAD test."""
    src = (
        "class MyErr(ValueError):\n"
        "    pass\n"
        "def f(a):\n"
        "    try:\n"
        "        return int(a)\n"
        "    except MyErr:\n"
        "        return 1\n"
    )
    cands = broad_vt_candidates(src, "psh/fake.py")
    assert not cands, f"a narrow body must stay unflagged: {cands}"


def test_narrow_catch_is_not_flagged():
    """A single-conversion narrow catch is not a candidate."""
    src = (
        "def f(a):\n"
        "    try:\n"
        "        return int(a)\n"           # single statement, 1 call
        "    except ValueError:\n"
        "        return 0\n"
    )
    assert broad_vt_candidates(src, "psh/fake.py") == []


def test_reraising_catch_is_not_flagged():
    """A broad body that RE-RAISES (translate-and-raise) is safe, not a
    candidate — the error still surfaces."""
    src = (
        "def f(a):\n"
        "    try:\n"
        "        x = step_one(a)\n"
        "        step_two(x)\n"
        "    except ValueError as e:\n"
        "        raise ShellError(str(e))\n"
    )
    assert broad_vt_candidates(src, "psh/fake.py") == []
