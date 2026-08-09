"""Ledger: every terminal ``except Exception`` handler is CLASSIFIED.

A terminal handler — one that catches ``Exception`` and does not let it out —
is the broadest thing a program can do with a fault. Some are correct and
necessary: a forked child must never propagate past the fork, an interactive
REPL must survive a defect, a ``__del__`` must not raise. Others would be
masking. The difference is not visible from the handler itself; it is a
property of the CONTEXT, and that property was previously written down nowhere.

This file writes it down, and keeps it true. Every ``except Exception`` (and
every bare ``except:``) under ``psh/`` is classified here with the MECHANISM
that makes it terminal, or it fails ``test_no_unclassified_terminal_handler``.

**Keys are LINE-INDEPENDENT** — ``(relpath, enclosing function, sorted try-body
call names)`` — and that is the load-bearing design choice. A line-keyed ledger
rots on contact with ordinary refactoring: between the Checkpoint R census and
remediation 5C.1's base, four of these twenty-four handlers moved line (two in
``locale_service.py``, one in ``analysis_session.py``, one in
``source_processor.py``) without a single one of them CHANGING. A ledger that
needed re-editing for that is a ledger people learn to re-edit without reading.

**The classes**, each naming a mechanism rather than a vibe:

``ROLLBACK_AND_RERAISE``   undo partial state, then re-raise — the error still
                           surfaces; these are not masks at all.
``TRANSLATE_AND_RAISE``    convert to a typed error and raise it; also surfaces.
``FORK_BOUNDARY``          a child after fork; it must reach ``os._exit`` rather
                           than unwind into the parent's interpreter state.
``DEFECT_REPORTED``        routes to ``core.internal_errors`` — under
                           ``PSH_STRICT_ERRORS`` the defect surfaces, so the
                           handler is a reporting seam, not a swallow.
``ERROR_PATH_GLUE``        classifies an already-failed operation for the user;
                           the shell must stay alive to report it.
``DESTRUCTOR_OR_RELEASE``  ``__del__`` / a release loop that must free the
                           REMAINING resources even if one release fails.
``OPTIONAL_CAPABILITY``    probing for a platform capability; absence must
                           degrade, never crash.
``REPL_SURVIVAL``          the interactive loop; a defect must not end the
                           session.
``PROMPT_SURVIVAL``        prompt expansion; a failure must not make the shell
                           unusable.
``FD_RESTORE``             restoring descriptors on the way out of a redirection.

Remediation 5C.1 narrowed NONE of these: six already re-raise and three already
report to the defect reporter, and the remaining fifteen are must-not-flip
territory (fork boundary, REPL, reactive locale, ``__del__``). The deliverable
is the classification and the mechanism that keeps it honest.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

#: The closed vocabulary. A class outside this set is a typo or an unargued
#: category; either way the ledger should refuse it.
CLASSES = {
    "ROLLBACK_AND_RERAISE",
    "TRANSLATE_AND_RAISE",
    "FORK_BOUNDARY",
    "DEFECT_REPORTED",
    "ERROR_PATH_GLUE",
    "DESTRUCTOR_OR_RELEASE",
    "OPTIONAL_CAPABILITY",
    "REPL_SURVIVAL",
    "PROMPT_SURVIVAL",
    "FD_RESTORE",
}


def _call_name(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (
        f.id if isinstance(f, ast.Name) else "?")


def _mentions_exception(t):
    if t is None:
        return True          # bare `except:` — the broadest form of all
    if isinstance(t, ast.Tuple):
        return any(_mentions_exception(e) for e in t.elts)
    return isinstance(t, ast.Name) and t.id == "Exception"


def terminal_handlers(src, relpath):
    """``[(relpath, enclosing_fn, call_names)]`` for every ``except Exception``
    / bare-except handler, keyed line-independently."""
    tree = ast.parse(src)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    def enclosing(node):
        cur = parent.get(id(node))
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.name
            cur = parent.get(id(cur))
        return "(module level)"

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        calls = tuple(sorted({_call_name(c) for st in node.body
                              for c in ast.walk(st)
                              if isinstance(c, ast.Call)}))
        for h in node.handlers:
            if _mentions_exception(h.type):
                out.append((relpath, enclosing(node), calls))
    # MULTIPLICITY (verify-round N-1/N-24). The caller sets() these, so two
    # DISTINCT handlers sharing a key -- same file, same enclosing function,
    # identical try-body call names -- would collapse into one entry, and a NEW
    # unclassified handler that happened to collide with a classified one would
    # be auto-classified and invisible to every cell here, the 24-count
    # included. The shape is live-adjacent: run_background_shell_child already
    # holds two of the 24, separated ONLY by their call names.
    #
    # Disambiguating by OCCURRENCE INDEX keeps the key line-independent (the
    # property §A1.1's drift evidence bought) while making a collision visible:
    # the second colliding handler keys as ...#1 and has no ledger entry.
    seen: dict = {}
    keyed = []
    for rel, fn, calls in out:
        n = seen.get((rel, fn, calls), 0)
        seen[(rel, fn, calls)] = n + 1
        keyed.append((rel, fn, calls) if n == 0 else (rel, fn, calls, n))
    return keyed


def _live_handlers():
    found = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        found.extend(terminal_handlers(path.read_text(), rel))
    return set(found)


# --- The ledger: key -> (CLASS, the mechanism that makes it terminal) --------
TERMINAL_HANDLERS = {
    # --- ROLLBACK_AND_RERAISE: undo, then re-raise. Not masks. ---------------
    ("psh/io_redirect/file_redirect.py", "apply_redirections",
     ("_apply_redirections",)):
        ("ROLLBACK_AND_RERAISE",
         "a redirection set is a transaction: if applying any member fails "
         "part-way, the already-applied fds must be restored before the error "
         "propagates, or the shell is left with a half-applied redirection. "
         "restore_redirections() then re-raise."),
    ("psh/io_redirect/file_redirect.py", "apply_permanent_redirections",
     ("apply_in_order",)):
        ("ROLLBACK_AND_RERAISE",
         "same transaction shape for PERMANENT (exec) redirections, which also "
         "own a std-stream lease: the handler rolls back the std streams and "
         "releases the lease before re-raising, so a failed `exec >file` does "
         "not strand the lease."),
    ("psh/io_redirect/manager.py", "setup_builtin_redirections",
     ("apply_in_order",)):
        ("ROLLBACK_AND_RERAISE",
         "builtin redirection setup is likewise all-or-nothing: "
         "restore_builtin_redirections() undoes the partial application, then "
         "the error propagates to the builtin's caller."),
    ("psh/executor/strategies.py", "execute_builtin_guarded",
     ("execute_in_context",)):
        ("ROLLBACK_AND_RERAISE",
         "reports the defect and discards a pending arithmetic assignment so "
         "the failed builtin cannot leave a half-written value behind, then "
         "RE-RAISES — the error still reaches the executor."),

    # --- TRANSLATE_AND_RAISE: convert to a typed error, then raise. ----------
    ("psh/lexer/recognizers/registry.py", "recognize",
     ("can_recognize", "recognize")):
        ("TRANSLATE_AND_RAISE",
         "a recognizer plugin that raises is a defect in that plugin; the "
         "registry converts it to a RuntimeError naming the offending "
         "recognizer, which is strictly more information than the raw error, "
         "and raises. Nothing is swallowed."),
    ("psh/scripting/analysis_session.py", "analyze",
     ("_absorb_transitions", "expands_aliases_now", "lex_and_expand", "max",
      "offset_line_numbers", "parse_tokens")):
        ("TRANSLATE_AND_RAISE",
         "the analysis session converts any failure of one unit into an "
         "AnalysisSyntaxError carrying that unit's start line, which is the "
         "embedder-facing contract; the error is raised, not absorbed."),

    # --- FORK_BOUNDARY: a child must never unwind past the fork. -------------
    ("psh/executor/child_policy.py", "run_background_shell_child",
     ("run_pending_traps",)):
        ("FORK_BOUNDARY",
         "inside a forked background child: running pending traps must not "
         "abort the child's exit sequence, because unwinding here would "
         "re-enter the PARENT's interpreter state in a process that must only "
         "ever reach os._exit."),
    ("psh/executor/child_policy.py", "run_background_shell_child",
     ("execute_exit_trap",)):
        ("FORK_BOUNDARY",
         "same forked child, EXIT-trap stage: a defective user EXIT trap must "
         "not prevent the child reaching os._exit with its computed status "
         "(child-status semantics are 1.3b's, unchanged here)."),
    ("psh/executor/child_policy.py", "run_child_body",
     ("execute_exit_trap",)):
        ("FORK_BOUNDARY",
         "the shared child-body runner's EXIT-trap stage: identical mechanism "
         "to the background variant — the trap is user code running in a "
         "process that must terminate via os._exit regardless."),
    ("psh/executor/child_policy.py", "run_child_shell",
     ("_exit", "apply_child_signal_policy", "flush_child_streams",
      "for_subshell", "io_setup", "run_child_body")):
        ("FORK_BOUNDARY",
         "the outermost child-shell frame: ANY escape here would unwind into "
         "the parent's stack inside a forked process. The handler writes the "
         "diagnostic with a raw fd write (the stream layer may itself be the "
         "casualty) and calls os._exit — the discipline this whole family "
         "exists to guarantee."),
    ("psh/executor/process_launcher.py", "_child_setup_and_exec",
     ("_job_control_off", "apply", "apply_child_signal_policy", "close",
      "execute_fn", "for_launch", "get", "getpgrp", "getpid", "io_setup",
      "isinstance", "print", "read", "setpgid")):
        ("FORK_BOUNDARY",
         "between fork and exec in the launched child: process-group setup, "
         "signal policy and I/O wiring all run here, and a failure must become "
         "an exit status rather than an exception unwinding in a child that "
         "shares the parent's memory image."),

    # --- DEFECT_REPORTED: surfaces under PSH_STRICT_ERRORS. ------------------
    ("psh/core/trap_manager.py", "execute_trap",
     ("get_current_line_number", "run_command")):
        ("DEFECT_REPORTED",
         "a user trap body is arbitrary shell code invoked from a signal-ish "
         "context; a defect in psh while running it is reported through "
         "core.internal_errors (loud under strict-errors) rather than "
         "propagating out of a trap dispatch, where there is no caller "
         "prepared to handle it."),
    ("psh/executor/function.py", "execute_function_call",
     ("execute_debug_trap", "execute_return_trap", "guarded_redirections",
      "visit")):
        ("DEFECT_REPORTED",
         "a shell function call frame: the handler routes to "
         "report_internal_defect so the defect is visible under "
         "strict-errors, while the function's own redirections stay unwound by "
         "the guarded_redirections context manager."),
    ("psh/scripting/visitor_modes.py", "handle_visitor_mode_for_content",
     ("apply_visitor_mode", "parse_for_analysis")):
        ("DEFECT_REPORTED",
         "the --validate/--format visitor modes are a diagnostic front-end; a "
         "defect is reported via core.internal_errors and turned into a "
         "non-zero status rather than a traceback at a user running a linter."),

    # --- ERROR_PATH_GLUE: classify a failure for the user, stay alive. -------
    ("psh/executor/command.py", "_execute_command",
     ("_array_assignment_lhs", "_run_background_assignment",
      "_run_bare_array_assignment", "_run_command", "_run_pure_assignment",
      "execute_debug_trap", "extract", "len", "print", "set_bash_command")):
        ("ERROR_PATH_GLUE",
         "the one door where a command's failure becomes an exit status: "
         "_handle_execution_error maps the error to the right status and "
         "diagnostic (and honours errexit), which is the shell's contract — a "
         "failing command sets $?, it does not abort the interpreter."),
    ("psh/scripting/source_processor.py", "_execute_buffered_command",
     ("_dispatch_execution", "_parse_command", "_preprocess_command", "get",
      "getattr")):
        ("ERROR_PATH_GLUE",
         "_classify_buffered_error decides whether a buffered command's "
         "failure is a syntax error, an incomplete construct needing more "
         "input, or a runtime error — the classification IS the handler's "
         "purpose, and the script processor must survive to report it."),
    ("psh/interactive/rc_loader.py", "load_rc_file",
     ("SourceRequest", "execute_sourced_file")):
        ("ERROR_PATH_GLUE",
         "a broken ~/.pshrc must not make the shell unstartable — bash also "
         "reports and continues. The handler prints the diagnostic and lets "
         "the session come up, which is the only behaviour that leaves the "
         "user able to FIX the rc file."),

    # --- DESTRUCTOR_OR_RELEASE ----------------------------------------------
    ("psh/utils/signal_utils.py", "__del__", ("close",)):
        ("DESTRUCTOR_OR_RELEASE",
         "a __del__ runs during garbage collection where an exception cannot "
         "be delivered to any caller; Python would print and discard it "
         "anyway. Catching keeps interpreter shutdown quiet and deterministic."),
    ("psh/core/process_lease.py", "_release_components", ("_restore",)):
        ("DESTRUCTOR_OR_RELEASE",
         "releasing a lease's components is a loop over independent restores: "
         "one component failing must not strand the REMAINING ones, so the "
         "failure is collected and the loop continues — the errors are "
         "reported by the caller after every component has had its turn."),

    # --- OPTIONAL_CAPABILITY -------------------------------------------------
    ("psh/core/locale_service.py", "_load_libc", ("CDLL", "find_library")):
        ("OPTIONAL_CAPABILITY",
         "probing for libc via ctypes: the library may be absent, unloadable "
         "or differently named on the platform. Absence must degrade to the "
         "pure-Python path, never crash the shell at startup (reactive LC_* "
         "machinery)."),
    ("psh/core/locale_service.py", "_ctypes_member_fn", ("encode", "wctype")):
        ("OPTIONAL_CAPABILITY",
         "resolving one libc symbol through ctypes: a missing or "
         "signature-mismatched member means that capability is unavailable on "
         "this platform, which the caller handles by falling back."),

    # --- REPL / PROMPT survival ---------------------------------------------
    ("psh/interactive/repl_loop.py", "run",
     ("_run_prompt_command", "clear_exit_warning",
      "confirm_exit_with_stopped_jobs", "hasattr", "idle_title",
      "ignoreeof_limit", "note_simple_command", "notify_completed_jobs",
      "notify_stopped_jobs", "print", "process_sigchld_notifications",
      "read_command", "run_command", "set_terminal_title", "strip")):
        ("REPL_SURVIVAL",
         "the interactive read-eval loop: a defect while handling ONE command "
         "must not end the user's session and lose their shell state. This is "
         "the strongest must-not-flip in this file — narrowing it would trade "
         "a reported error for a terminated session."),
    ("psh/interactive/prompt.py", "expand_full", ("expand_string_variables",)):
        ("PROMPT_SURVIVAL",
         "PS1 expansion runs before every prompt; a failure (a bad "
         "command-substitution in PS1, say) must leave the user with a usable "
         "shell rather than an unprompted one."),

    # --- FD_RESTORE ----------------------------------------------------------
    ("psh/io_redirect/file_redirect.py", "restore", ("?", "getattr")):
        ("FD_RESTORE",
         "restoring a saved descriptor on the way out of a redirection: the "
         "target fd may already be closed by the command that ran. Failing to "
         "restore one fd must not prevent restoring the others, nor mask the "
         "command's own exit status."),
}


# --- The ledger's assertions -------------------------------------------------

def test_no_unclassified_terminal_handler():
    """A NEW terminal handler must be classified — or narrowed away."""
    live = _live_handlers()
    new = sorted(live - set(TERMINAL_HANDLERS))
    assert not new, (
        "NEW terminal `except Exception` (or bare `except:`) handler. Either "
        "narrow it to the error types the try body can actually raise, or add "
        "it here with the CLASS and the specific mechanism that makes "
        "swallowing correct in that context:\n  "
        + "\n  ".join(map(str, new)))


def test_ledger_has_no_stale_entries():
    """Shrink-with-the-tree: a classified handler that no longer exists (it was
    narrowed, or its function was renamed) must lose its entry."""
    live = _live_handlers()
    stale = sorted(set(TERMINAL_HANDLERS) - live)
    assert not stale, (
        "classified terminal handlers with no live counterpart — narrowed or "
        "moved. Prune them so the ledger keeps describing the tree:\n  "
        + "\n  ".join(map(str, stale)))


def test_every_class_is_in_the_vocabulary():
    bad = {k: v[0] for k, v in TERMINAL_HANDLERS.items() if v[0] not in CLASSES}
    assert not bad, (
        f"class outside the closed vocabulary {sorted(CLASSES)}: {bad}")


def test_every_entry_names_its_mechanism():
    """A reason must say WHY this context makes swallowing correct. The length
    floor is crude, but it is the same one the Q2 ledger uses and it does keep
    'defensive' and 'just in case' out."""
    for key, (cls, reason) in TERMINAL_HANDLERS.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 60, (
            f"{key} ({cls}) needs a reason naming the mechanism")


def test_detector_is_not_vacuous():
    assert _live_handlers(), "detector found no handlers — it cannot bite"


def test_the_census_figure_holds():
    """The headline: 24 terminal handlers, 0 bare. A partial regression cannot
    hide inside a per-entry table that someone updated to match."""
    live = _live_handlers()
    assert len(live) == 24, (
        f"terminal-handler count is {len(live)}, expected 24. A new one needs "
        "a ledger entry; a removed one needs its entry pruned.")


def test_no_bare_except_survives():
    """Bare `except:` also catches KeyboardInterrupt/SystemExit. There are
    none, and this keeps it that way."""
    bare = []
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bare.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert not bare, (
        "bare `except:` swallows KeyboardInterrupt and SystemExit too — name "
        f"the exception type: {bare}")


# --- Guard-the-guard ---------------------------------------------------------

def test_offender_unclassified_handler_is_detected():
    """A synthetic terminal handler is reported by the detector, so an
    unclassified real one would be too."""
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except Exception:\n"
           "        return 1\n")
    found = terminal_handlers(src, "psh/fake.py")
    assert found == [("psh/fake.py", "f", ("risky",))]
    assert not set(found) <= set(TERMINAL_HANDLERS), (
        "the synthetic offender must NOT already be classified")


def test_offender_a_colliding_second_handler_is_VISIBLE():
    """N-1/N-24: the collapse this keying exists to prevent.

    Two distinct terminal handlers in one function with identical try-body call
    names used to collapse to a single set entry — so the second one was
    auto-classified by the first one's ledger row and the census still read 24.
    The occurrence index makes it a separate, unclassified key.
    """
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except Exception:\n"
           "        pass\n"
           "    try:\n"
           "        risky()\n"          # identical call set, same function
           "    except Exception:\n"
           "        pass\n")
    found = terminal_handlers(src, "psh/fake.py")
    assert len(found) == 2, "both handlers must be reported"
    assert len(set(found)) == 2, (
        "the two handlers collapsed to one key — a colliding NEW handler would "
        "be invisible to every cell in this file")
    assert found[1] == ("psh/fake.py", "f", ("risky",), 1), (
        f"the second occurrence should carry its index, got {found[1]}")


def test_offender_a_stale_entry_is_detected():
    """N-2: the brief's THIRD offender arm, which the first cut omitted.

    A classified handler that is narrowed away, renamed, or moved must force
    its entry out — otherwise the ledger drifts into describing a tree that no
    longer exists, which is the failure mode the Q2 ledger's twin cell prevents.
    Driven against a COPY of the registry so the real one is untouched.
    """
    fake_key = ("psh/zzz_not_a_real_module.py", "nope", ("x",))
    registry = dict(TERMINAL_HANDLERS)
    registry[fake_key] = ("FORK_BOUNDARY", "x" * 70)
    live = _live_handlers()
    stale = sorted(set(registry) - live)
    assert stale == [fake_key], (
        "a classified handler with no live counterpart must be reported as "
        f"stale; got {stale}")
    # CONTROL: the real registry has none.
    assert not sorted(set(TERMINAL_HANDLERS) - live)


def test_offender_bare_except_is_detected():
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except:\n"
           "        pass\n")
    assert terminal_handlers(src, "psh/fake.py") == [
        ("psh/fake.py", "f", ("risky",))]


def test_offender_exception_inside_a_tuple_is_detected():
    """`except (OSError, Exception)` is still terminal."""
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except (OSError, Exception):\n"
           "        pass\n")
    assert terminal_handlers(src, "psh/fake.py")


def test_control_a_narrow_handler_is_not_a_candidate():
    """CONTROL. Without this, a detector that flagged everything would look
    healthy while making the ledger meaningless."""
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except OSError:\n"
           "        pass\n")
    assert terminal_handlers(src, "psh/fake.py") == []


def test_control_every_live_handler_is_classified_by_its_own_key():
    """CONTROL for the keying scheme: every live handler resolves to an entry,
    which is what makes the no-stale and no-unclassified cells meaningful
    rather than trivially satisfiable."""
    live = _live_handlers()
    assert live == set(TERMINAL_HANDLERS), (
        f"unclassified={sorted(live - set(TERMINAL_HANDLERS))} "
        f"stale={sorted(set(TERMINAL_HANDLERS) - live)}")


def test_keys_are_line_independent():
    """The design property, asserted rather than merely documented: inserting
    lines above a handler must not change its key."""
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except Exception:\n"
           "        pass\n")
    shifted = "# a new comment\n" * 12 + src
    assert terminal_handlers(src, "psh/fake.py") == \
        terminal_handlers(shifted, "psh/fake.py")
