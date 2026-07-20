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


def _catches_vt(handler):
    names = _exc_names(handler)
    return "ValueError" in names or "TypeError" in names


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (
        f.id if isinstance(f, ast.Name) else "?")


def broad_vt_candidates(src, relpath):
    """Return [(relpath, exc_names, call_names)] for every broad,
    non-re-raising VT catch (the candidate signature, line-independent)."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.Try):
            continue
        calls = sorted({_call_name(c) for st in n.body for c in ast.walk(st)
                        if isinstance(c, ast.Call)})
        broad = len(n.body) > 1 or len(calls) >= 5
        for h in n.handlers:
            if not _catches_vt(h):
                continue
            if any(isinstance(x, ast.Raise) for x in ast.walk(h)):
                continue
            if broad:
                out.append((relpath, _exc_names(h), tuple(calls)))
    return out


def _live_candidates():
    found = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        found.extend(broad_vt_candidates(path.read_text(), rel))
    return set(found)


# --- The known broad maskers (DEBT — shrink-only). Each: what the try wraps. --
BROAD_MASKING = {
    ("psh/builtins/directory_stack.py", ("ValueError",),
     ("_chdir_or_error", "_print_stack", "error", "int", "pop", "size",
      "startswith", "update_current", "update_pwd_vars")):
        "popd: only int(arg) should raise VE, but _chdir_or_error/pop/"
        "update_pwd_vars sit inside the try — a defect there is reported as "
        "'invalid index argument'. The sibling _popd_no_cd wraps ONLY int(arg) "
        "(the codebase's own correct narrow form).",
    ("psh/builtins/directory_stack.py", ("ValueError",),
     ("error", "int", "size", "startswith")):
        "dirs -N: intent is int(arg) but stack.size()/self.error inside the try "
        "can mask a real VE as 'invalid index argument'.",
    ("psh/builtins/disown.py", ("ValueError",),
     ("_disown_job", "error", "get_job_by_pid", "int")):
        "disown: intent is int(spec); get_job_by_pid/_disown_job are also "
        "guarded, so a defect there reads as a bad job specification.",
    ("psh/builtins/parse_tree.py", ("ValueError", "TypeError", "AttributeError"),
     ("ASTDotGenerator", "ASTPrettyPrinter", "Parser", "parse", "render",
      "to_dot", "tokenize", "visit", "write_line")):
        "debug builtin: wraps the whole tokenize->parse->format pipeline; a "
        "parser/visitor VT/AttributeError defect becomes a bland "
        "'visualization error'.",
    ("psh/builtins/read_builtin.py", ("ValueError",),
     ("_assign_to_array", "_assign_to_variables", "_process_escapes",
      "_read_continuations", "_read_exact", "_read_normal", "_read_special",
      "_read_with_timeout", "_split_with_ifs", "append", "cursor_for_fd",
      "endswith", "get", "get_variable", "join", "len", "poll_readable",
      "set_variable")):
        "the whole `read` record engine under one VE net — no int()/documented-"
        "VE source in the body; a VE from any helper bug is reported as a user "
        "'read error'.",
    ("psh/executor/core.py", ("ValueError", "TypeError", "OSError"),
     ("TestExpressionEvaluator", "evaluate")):
        "the entire `[[ ]]` evaluation is inside the try; a VE/TypeError bug in "
        "the evaluator is masked as a `[[` syntax error (exit 2) — it should "
        "catch a narrow evaluator error type, not raw VT.",
    ("psh/parser/combinators/parser.py",
     ("AttributeError", "IndexError", "TypeError", "ParseError"),
     ("_prepare_tokens", "len", "parse")):
        "can_parse wraps a full parse and turns ANY AttributeError/TypeError bug "
        "into 'not parseable'. The educational combinator parser is explicitly "
        "outside the production quality bar (parser/CLAUDE.md) — flagged, low "
        "priority.",
    ("psh/utils/ast_debug.py", ("ValueError", "TypeError", "AttributeError"),
     ("ASTDotGenerator", "ASTPrettyPrinter", "ValueError", "print", "render",
      "to_dot", "visit")):
        "the AST-formatter selection downgrades a TypeError/AttributeError in "
        "ANY formatter to a warning + fallback; a single if/elif statement hides "
        "many formatter calls (the compound-statement masker).",
}

# --- Candidates that are actually NARROW/safe (single conversion or one -------
#     documented-signal primitive whose VT IS its contract). ------------------
NARROW_SAFE = {
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
    ("psh/executor/control_flow.py",
     ("ReadonlyVariableError", "NamerefCycleError", "ValueError",
      "ArithmeticError"), ("evaluate_arithmetic",)):
        "evaluate_arithmetic's VE is a user-reachable arithmetic error (a shell "
        "error, not an internal defect)",
    ("psh/executor/core.py", ("OSError", "ValueError"), ("flush", "write")):
        "stream flush/write documented signal (closed/broken stream)",
    ("psh/executor/core.py", ("ValueError", "ArithmeticError"),
     ("evaluate_arithmetic",)):
        "evaluate_arithmetic user arithmetic error",
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
