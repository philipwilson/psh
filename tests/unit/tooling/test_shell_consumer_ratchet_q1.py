"""Shrink-only ratchet: full-``Shell`` consumers among the Q1 boundary modules.

Campaign Q1 (§13) migrates a service-locator boundary — a component that took
the whole ``Shell`` and reached whatever subsystem it liked — to a narrow
protocol whenever its actual needs fit one. Some boundaries genuinely still need
the full ``Shell`` (they FORWARD it to something that needs the whole shell, or
they reach the trap/signal/executor machinery no protocol models). This ratchet
freezes THAT set: every function/method in a boundary module whose parameter is
the full ``Shell`` is recorded here WITH a one-line justification.

**The contract on ``ALLOWLIST`` is shrink-only WITH ONE NARROW EXCEPTION.** The
recorded set may only SHRINK, except that entries MAY be added when a module
newly enters the scan scope — whether because the scope was extended or because
the DETECTOR was taught a shape it previously missed — provided each addition
lands in the SAME COMMIT as that extension and carries its own specific
justification (integrator pre-ruling 5B.1-R0, extended to detector-shape by
R1.6). Growth in any other circumstance is a contract breach, not a judgement
call. The exception exists because the alternative is worse: a scope extension
that cannot record what it finds either lands red or quietly narrows what it
scans, and both defeat the ratchet. Remediation 5B.1 used it exactly once, for
the three ``analysis_session`` consumers (6 entries -> 9).

- A NEW full-``Shell`` consumer in a scanned module (not in ``ALLOWLIST``) fails
  ``test_no_unrecorded_full_shell_consumers`` — narrow it to a protocol or
  justify it here (a reviewed edit).
- A recorded consumer that no longer takes ``Shell`` (migrated to a protocol)
  fails ``test_ratchet_only_shrinks`` — remove its stale entry; the set shrank.

**Module scope — source of truth.** ``CREATED_MODULES`` is the set of files the
campaign ADDED, defined by (and verified against, when the tag is present, by
``test_created_modules_match_enumeration``):

    git log --diff-filter=A --pretty=format: --name-only v0.724.0..8af29e6d -- psh/

``TOUCHED_PREEXISTING`` adds the pre-campaign files the campaign MIGRATED or that
carry a recorded consumer, so the ratchet actually SEES them (an allowlist entry
in an unscanned file, or a future offender there, would otherwise be invisible).

**Scope CURRENCY (remediation 5B.1).** The enumeration above is pinned to an
ENDPOINT, so it says nothing about modules born after it — and a scan scope that
silently stops covering new code is a ratchet in name only. Checkpoint R proved
this concretely: three production modules created after the PREVIOUS endpoint
(``75ab5625``) were unscanned, and a synthetic full-``Shell`` offender planted in
two of them passed every test in this file. Two things keep the scope current:

* ``POST_ENDPOINT_SCANNED`` — modules born AFTER the pinned endpoint that this
  ratchet nonetheless scans. They cannot live in ``CREATED_MODULES``: that list
  is asserted EQUAL to the pinned git enumeration, which by construction cannot
  contain them.
* ``test_post_endpoint_modules_are_all_dispositioned`` — the COVERAGE assertion.
  Every ``psh/`` module created after the endpoint must be either scanned or
  recorded in ``POST_ENDPOINT_OUT_OF_SCOPE`` with a justification, so a new
  module forces an explicit disposition instead of vanishing into the gap. Its
  decision logic is the pure function ``uncovered_post_endpoint_modules``,
  self-tested against an INJECTED enumeration — never against real commits,
  which would make the self-test's own subject move underneath it.

**Detector.** A full-``Shell`` consumer is either:

* a PARAMETER whose annotation mentions ``Shell`` as an identifier — bare
  (``shell: Shell``), a string forward-ref (``'Shell'``), OR wrapped/nested
  (``Optional['Shell']``, ``'Shell | None'``, ``Callable[['Shell'], int]``) — OR
  a parameter that is UNANNOTATED and named exactly ``shell`` (a smuggled reach
  with no type); or
* a CLASS-LEVEL ANNOTATED ATTRIBUTE whose annotation mentions ``Shell``
  (``class C: shell: 'Shell'``). Holding the whole shell as a declared field is
  the same service-locator reach as taking it as a parameter, one indirection
  later. Remediation 5B.1 found the parameter-only detector blind to this, which
  mattered because it is the exact shape of the "broad owner escape hatch" 5B's
  exit criterion names; or
* an INSTANCE ATTRIBUTE named ``shell``/``_shell`` bound to a bare name inside a
  method body (``def wire(self, s): self.shell = s``). Remediation 5B.2 added
  this arm for the shape 5B.1 registered as its remaining blind spot: a shell
  stored by plain assignment, with no annotation anywhere.

  **It is keyed on the assignment TARGET, and that is the point.** Keying it on
  the SOURCE instead — "an attribute assigned from a full-``Shell`` parameter" —
  is the design that first suggests itself and it is worthless: to write
  ``self.x = shell`` the value must BE a full-``Shell`` parameter, and every
  function that has one is already flagged by the parameter arm, so a
  source-keyed arm cannot report anything the detector did not already know. It
  was measured doing precisely that (33 hits tree-wide, none of them new)
  before being replaced. The shape the parameter arm genuinely cannot see is
  the one where the parameter is unannotated AND not named ``shell``, so that
  only the FIELD's name reveals what is being held.

  The value must be a BARE NAME, deliberately: ``self.mgr =
  shell.expansion_manager`` and ``self.state = shell.state`` are the narrowings
  this campaign exists to produce, and both are attribute accesses. An arm that
  flagged the migration target as the offender would fight its own purpose.

No form ever matches ``ShellState`` (a distinct identifier — already a
narrowing). ``ShellState`` is deliberately NOT counted in ANY position
(``process_launcher`` / ``input_sources`` take it as a parameter; ``JobRuntime``
carries it as a member): it is a state container, not a service locator, and
counting it would flag the narrowings the campaign asked for as though they were
debt.

The ``test_detector_*`` self-tests prove the detector flags the bare, wrapped,
unannotated, class-attribute and instance-assignment shapes, and ignores
``ShellState`` / protocol members / narrowings in every position, so the ratchet
cannot rot into a no-op.
"""

import ast
import pathlib
import re
import subprocess
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


# Campaign Q3 (WP5): the git self-check below verifies CREATED_MODULES against
# the actual campaign-added set. When git or the base tag is unavailable it must
# WARN (naming the protection lost) before skipping — never skip silently, or
# list drift goes undetected in shallow/tarball checkouts. This mirrors the
# uniform F9 hardening in test_mypy_untyped_defs_coverage.py. Green-repo
# behavior (git + tag present) is unchanged: the assertion runs.
_SELFCHECK_UNVERIFIED = (
    "SELF-CHECK SKIPPED: cannot verify {name} against the git enumeration "
    "(git log --diff-filter=A {range} -- psh/): {reason}. The "
    "hardcoded list is TRUSTED UNVERIFIED here — drift between it and the "
    "actual campaign-created set will go UNDETECTED until this test runs in a "
    "full checkout with the base tag present."
)

#: The pinned scope endpoint. ``CREATED_MODULES`` is exactly the psh/ modules
#: added in ``SCOPE_BASE..SCOPE_ENDPOINT``; everything born after
#: ``SCOPE_ENDPOINT`` is dispositioned by the coverage assertion instead.
#: Advancing the endpoint is a deliberate, reviewed edit — it re-baselines what
#: "new" means, so it moves only together with the two lists below.
SCOPE_BASE = "v0.724.0"
SCOPE_ENDPOINT = "8af29e6d"
SCOPE_RANGE = f"{SCOPE_BASE}..{SCOPE_ENDPOINT}"


def _warn_selfcheck_unverified(list_name, reason, rng=None):
    warnings.warn(
        _SELFCHECK_UNVERIFIED.format(
            name=list_name, reason=reason, range=rng or SCOPE_RANGE),
        stacklevel=2,
    )


# Files the campaign ADDED (git --diff-filter=A v0.724.0..8af29e6d -- psh/).
CREATED_MODULES = [
    "psh/ast_nodes/syntax_templates.py",
    "psh/core/process_lease.py",
    "psh/core/variable_lookup.py",
    "psh/executor/command_resolution.py",
    "psh/executor/foreground_session.py",
    "psh/expansion/procsub_render.py",
    "psh/expansion/subscript.py",
    "psh/interactive/history_result.py",
    "psh/invocation.py",
    "psh/io_redirect/input_cursor.py",
    "psh/io_redirect/redirect_program.py",
    "psh/parser/parse_inputs.py",
    "psh/parser/parse_outcome.py",
    "psh/parser/recursive_descent/support/syntax_templates.py",
    "psh/parser/session.py",
    "psh/parser/unclosed_expansion.py",
    "psh/protocols/__init__.py",
    "psh/scripting/analysis_session.py",
    "psh/scripting/program_source.py",
]

# Pre-campaign files the campaign MIGRATED or that carry a recorded consumer —
# scanned so the ratchet can see them (each annotated with why).
TOUCHED_PREEXISTING = [
    "psh/executor/process_launcher.py",   # campaign added AsyncJobPolicy; takes ShellState
    "psh/executor/child_policy.py",       # holds the 3 full-Shell subshell runners (allowlisted)
    "psh/scripting/input_sources.py",     # pre-campaign (v0.285); campaign-touched; takes ShellState
    "psh/builtins/input_reader.py",       # holds migrated make_reader (Shell -> IOContext)
]

# Modules born AFTER SCOPE_ENDPOINT that this ratchet scans anyway. These cannot
# go in CREATED_MODULES (asserted equal to the pinned enumeration, which cannot
# contain them). Each entry is a module the coverage assertion below would
# otherwise flag as undispositioned.
POST_ENDPOINT_SCANNED: list = [
    "psh/utils/posix_classes.py",   # 5B.1: the shared POSIX class table (data leaf)
    # slot 1.9 (C020): the one trailing-redirection helper. Parser-only — it
    # touches a CommandParsers, never a Shell — so it is scanned, not exempted.
    "psh/parser/combinators/trailing_redirects.py",
    # Slot 2.3: bash's legal_number for builtin numeric operands. A pure
    # str -> Optional[int] leaf that takes no Shell at all, so it is SCANNED
    # (and finds nothing) rather than declared out of scope.
    "psh/builtins/numeric.py",
    # slot 1.10 (C041): the null-command status rule. Takes ShellState and a
    # redirect list, never a full Shell — scanned so it stays that way.
    "psh/executor/null_command.py",
]

# Modules born after SCOPE_ENDPOINT that are deliberately NOT scanned —
# (path -> why). Kept honest by the coverage assertion: a new module must land
# in one list or the other, never in neither.
POST_ENDPOINT_OUT_OF_SCOPE: dict = {}

TOUCHED_MODULES = CREATED_MODULES + TOUCHED_PREEXISTING + POST_ENDPOINT_SCANNED


# The frozen set of boundary-module defs that legitimately still take the full
# ``Shell`` — (dotted-module, qualified-symbol) -> justification. Each forwards
# the shell to a whole-shell need or reaches a subsystem no protocol
# (ExpansionRuntime/IOContext/JobRuntime/LocaleAccess) models.
#
# CONTRACT: shrink-only, EXCEPT entries added in the SAME COMMIT as a scan-scope
# or detector-shape extension, each with its own justification (pre-ruling
# 5B.1-R0, extended to detector-shape by R1.6). Any other growth is a breach.
# See the module docstring for why the exception exists.
ALLOWLIST = {
    ("psh.executor.command_resolution", "resolve_command"):
        "forwards `shell` to ExecutionStrategy.can_execute(name, shell), which "
        "reads the function/builtin registries — a whole-shell dispatch need, "
        "not a protocol-shaped slice (it only reads shell.state.options itself)",
    ("psh.executor.child_policy", "run_background_shell_child"):
        "backgrounded compound-child runner: re-arms trap handlers via "
        "trap_manager + interactive_manager.signal_manager and runs the child "
        "body — whole-shell machinery, no protocol fit",
    ("psh.executor.child_policy", "run_child_body"):
        "shared child-Shell body runner: drives trap_manager, errexit/loop "
        "seeds and _current_executor — whole-shell machinery, no protocol fit",
    ("psh.executor.child_policy", "run_child_shell"):
        "substitution-child runner built on run_child_body: forks a child "
        "Shell (Shell.for_subshell) and reaches trap/signal/executor/streams",
    # RETIRED by remediation 5C.1 — the ratchet SHRANK, 9 entries -> 8.
    # ("psh.expansion.subscript", "SubscriptEvaluator.__init__") is gone. Its
    # justification read "the arithmetic forward forces the full Shell", which
    # was true until `evaluate_arithmetic` was typed to take
    # `protocols.ExpansionHost` — after which the sentence was simply false.
    # Leaving the entry would have parked a FALSE justification inside a
    # ratchet, which is worse than a missing one, because the next reader has
    # no way to tell it from a real one. Measured before removal: the module
    # reaches `.state` (:163), `.expansion_manager` (:176) and the arithmetic
    # forward (:383) — all ExpansionHost members, nothing else. The field is
    # RENAMED to `self.host`, not merely retyped, because this file's
    # instance-assignment arm keys on the FIELD NAME: a narrow `self.shell`
    # would still read as a service locator here, and rightly so.
    ("psh.scripting.program_source", "execute_sourced_file"):
        "THE sourced-file executor (source/. + rc load): owns state.source_depth, "
        "the positional-params swap/restore, FunctionReturn handling, the RETURN "
        "trap, and drives the input source through the executor — a whole-shell "
        "transaction, not a protocol-shaped slice",
    # --- entered scope with the 5B.1 scan-scope extension (pre-ruling 5B.1-R0:
    # entries added ONLY for modules newly entering scope, in the SAME commit as
    # the extension, each with a specific justification). All three are one
    # forward-chain ending at a construction no protocol can model.
    ("psh.scripting.analysis_session", "AnalysisSession._build_carrier"):
        "builds the analysis carrier via `type(shell)(parent_shell=shell, "
        "norc=True)` — construction through the caller's OWN Shell subclass with "
        "the shell itself as parent; a protocol models a surface an object HAS, "
        "never a constructible type, so this is irreducible (the EMBEDDER "
        "CONTRACT the method's docstring declares)",
    ("psh.scripting.analysis_session", "AnalysisSession.__init__"):
        "forwards `shell` to _build_carrier (the type(shell)(parent_shell=...) "
        "construction) and reads shell.analysis_mode; the forward forces the "
        "full Shell",
    ("psh.scripting.analysis_session", "parse_for_analysis"):
        "THE one door into analysis parsing; forwards `shell` to "
        "AnalysisSession(shell), whose carrier construction needs the whole Shell",
}


def _module_dotted(rel_path: str) -> str:
    return rel_path[:-3].replace("/", ".")


def _string_mentions_shell(s: str) -> bool:
    """True if a forward-ref string annotation names ``Shell`` as an identifier
    (``'Shell'``, ``"Optional[Shell]"``, ``'Shell | None'``) — never
    ``ShellState``."""
    try:
        sub = ast.parse(s, mode="eval")
    except SyntaxError:
        # Unparseable string: word-boundary match. `\bShell\b` does NOT match
        # inside `ShellState` (the following `S` is a word char).
        return re.search(r"\bShell\b", s) is not None
    # Delegate back so a doubly-nested forward-ref (Callable[['Shell'], int] —
    # 'Shell' is a string INSIDE the string) is unwrapped too.
    return _ann_mentions_shell(sub)


def _ann_mentions_shell(node) -> bool:
    """True if an annotation mentions ``Shell`` as an identifier anywhere —
    bare, string forward-ref, or wrapped (Optional/Union/Callable/…)."""
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "Shell":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if _string_mentions_shell(n.value):
                return True
    return False


#: Instance-attribute names that denote "the whole shell" when a method stores
#: one. Kept explicit rather than inferred: the arm exists precisely for the
#: case where nothing else in the signature says what is being held.
SHELL_FIELD_NAMES = {"shell", "_shell"}


def _stores_shell_by_assignment(fn) -> bool:
    """True if *fn* binds ``self.shell`` / ``self._shell`` to a bare name.

    See the module docstring for why this is keyed on the target rather than on
    the assigned value's origin, and why a bare NAME (not an attribute access)
    is the discriminator that keeps narrowings out.
    """
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                targets = tgt.elts if isinstance(tgt, ast.Tuple) else [tgt]
                values = (node.value.elts
                          if isinstance(tgt, ast.Tuple)
                          and isinstance(node.value, ast.Tuple)
                          else [node.value] * len(targets))
                for t, v in zip(targets, values, strict=False):
                    if (isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"
                            and t.attr in SHELL_FIELD_NAMES
                            and isinstance(v, ast.Name)):
                        return True
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            t = node.target
            if (isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                    and (t.attr in SHELL_FIELD_NAMES
                         or _ann_mentions_shell(node.annotation))
                    and isinstance(node.value, ast.Name)):
                return True
    return False


def full_shell_consumers(src: str, module: str) -> set:
    """Return {(module, qualname)} for every full-``Shell`` consumer: a def with
    a ``Shell`` parameter (annotated, or unannotated + named ``shell``), a class
    with a ``Shell``-annotated class-level attribute, or a method that STORES
    the shell as ``self.shell``/``self._shell``.

    The attribute form (``class C: shell: 'Shell'``) is the same service-locator
    reach one indirection later — a parameter-only detector was blind to it
    (remediation 5B.1) — and the instance-assignment form is the same reach with
    no declaration anywhere (remediation 5B.2). ``ShellState`` is never a hit in
    any position.
    """
    tree = ast.parse(src)
    found: set = set()

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                # Class-level annotated attributes holding the whole Shell.
                for stmt in child.body:
                    if (isinstance(stmt, ast.AnnAssign)
                            and isinstance(stmt.target, ast.Name)
                            and _ann_mentions_shell(stmt.annotation)):
                        found.add(".".join(
                            prefix + [child.name, stmt.target.id]))
                visit(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = child.args
                params = (list(a.posonlyargs) + list(a.args)
                          + list(a.kwonlyargs))
                if a.vararg:
                    params.append(a.vararg)
                if a.kwarg:
                    params.append(a.kwarg)
                hit = any(
                    _ann_mentions_shell(p.annotation)
                    or (p.annotation is None and p.arg == "shell")
                    for p in params
                ) or _stores_shell_by_assignment(child)
                if hit:
                    found.add(".".join(prefix + [child.name]))
                visit(child, prefix + [child.name])

    visit(tree, [])
    return {(module, sym) for sym in found}


def _live_consumers() -> set:
    consumers: set = set()
    for rel in TOUCHED_MODULES:
        path = ROOT / rel
        assert path.exists(), f"scanned module missing: {rel}"
        consumers |= full_shell_consumers(path.read_text(), _module_dotted(rel))
    return consumers


# --- The ratchet ------------------------------------------------------------

def test_scanned_modules_all_exist():
    for rel in TOUCHED_MODULES:
        assert (ROOT / rel).exists(), f"scanned module missing: {rel}"


def _enumerate_added(rng, list_name):
    """psh/ modules added in *rng*, or None when git/the range is unavailable
    (warning loudly first — never a silent skip)."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--pretty=format:",
             "--name-only", rng, "--", "psh/"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _warn_selfcheck_unverified(
            list_name, f"git unavailable ({type(e).__name__})", rng)
        return None
    if out.returncode != 0:
        _warn_selfcheck_unverified(
            list_name, f"base tag/range {rng} not present", rng)
        return None
    return {ln.strip() for ln in out.stdout.splitlines()
            if ln.strip().endswith(".py")}


def uncovered_post_endpoint_modules(created_after_endpoint, scanned,
                                    out_of_scope):
    """The post-endpoint modules that are neither scanned nor declared
    out-of-scope — i.e. the ones that would silently fall outside the ratchet.

    Pure, so the coverage assertion's logic can be self-tested against an
    INJECTED enumeration rather than against real commits (which would move
    under the test).
    """
    return sorted(set(created_after_endpoint) - set(scanned)
                  - set(out_of_scope))


def test_created_modules_match_enumeration():
    """CREATED_MODULES is exactly the campaign-added set. Verified against git
    when the base tag is present; when git or the tag is absent the self-check
    WARNS loudly (Q3 WP5) before skipping, never silently (shallow checkout)."""
    enumerated = _enumerate_added(SCOPE_RANGE, "CREATED_MODULES")
    if enumerated is None:
        pytest.skip("git/base range unavailable in this checkout")
    assert enumerated == set(CREATED_MODULES), (
        "CREATED_MODULES drifted from the git enumeration "
        f"({SCOPE_RANGE} --diff-filter=A -- psh/). Update the list.\n"
        f"  only in git: {sorted(enumerated - set(CREATED_MODULES))}\n"
        f"  only in list: {sorted(set(CREATED_MODULES) - enumerated)}"
    )


def _endpoint_is_ancestor_of_head():
    """True/False if git can answer, None if git cannot be consulted."""
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", SCOPE_ENDPOINT, "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    return None   # not a repo / unknown rev — indistinguishable from absent


def test_post_endpoint_modules_are_all_dispositioned():
    """COVERAGE (5B.1): every psh/ module born after SCOPE_ENDPOINT is either
    scanned or explicitly declared out-of-scope.

    Without this, the scan scope silently stops covering new code the moment the
    endpoint is pinned — exactly the Checkpoint R q5-F2 defect, where three
    modules created after the previous endpoint were invisible and a planted
    offender passed every test here.

    ANCESTOR CHECK FIRST. ``SCOPE_ENDPOINT..HEAD`` is EMPTY — and this test
    therefore vacuously green — whenever the endpoint is not an ancestor of
    HEAD: a branch that predates it, a rewritten history, a fresh shallow
    clone. That is the same silent-rot failure mode the test exists to prevent,
    one level up, so it WARNS loudly instead of passing quietly.

    KNOWN AND RECORD-ONLY: a module that exists in the working tree but is not
    yet COMMITTED is invisible to the git enumeration and so is not
    dispositioned here. That is inherent to enumerating by history, and gates
    run on committed SHAs, so it cannot hide a landed module.
    """
    ancestry = _endpoint_is_ancestor_of_head()
    if ancestry is False:
        _warn_selfcheck_unverified(
            "POST_ENDPOINT coverage",
            f"SCOPE_ENDPOINT {SCOPE_ENDPOINT} is NOT an ancestor of HEAD, so "
            "the range is empty and this coverage check would pass VACUOUSLY",
            f"{SCOPE_ENDPOINT}..HEAD")
        pytest.skip(f"{SCOPE_ENDPOINT} is not an ancestor of HEAD")
    created = _enumerate_added(f"{SCOPE_ENDPOINT}..HEAD",
                              "POST_ENDPOINT_SCANNED")
    if created is None or ancestry is None:
        pytest.skip("git/endpoint range unavailable in this checkout")
    # Only modules that still exist can be scanned; one created and later
    # deleted needs no disposition.
    live = {rel for rel in created if (ROOT / rel).exists()}
    uncovered = uncovered_post_endpoint_modules(
        live, TOUCHED_MODULES, POST_ENDPOINT_OUT_OF_SCOPE)
    assert not uncovered, (
        "psh/ module(s) created after the pinned scope endpoint "
        f"({SCOPE_ENDPOINT}) with NO disposition: {uncovered}. Either add each "
        "to POST_ENDPOINT_SCANNED (so the ratchet sees its full-`Shell` "
        "consumers) or to POST_ENDPOINT_OUT_OF_SCOPE with a justification. "
        "Leaving it in neither is how the scan scope silently rots."
    )


def test_selfcheck_warns_loudly_when_git_unavailable():
    """Q3 WP5: the git self-check WARNS (naming the lost protection) rather than
    skipping silently — so CREATED_MODULES drift is signalled even in a checkout
    without git/the base tag. Uniform with the F9 twin."""
    with pytest.warns(UserWarning, match="TRUSTED UNVERIFIED"):
        _warn_selfcheck_unverified("CREATED_MODULES", "git unavailable (OSError)")


def test_no_unrecorded_full_shell_consumers():
    live = _live_consumers()
    new = live - set(ALLOWLIST)
    assert not new, (
        "New full-`Shell` consumer(s) in a boundary module. Narrow the "
        "parameter to a psh.protocols protocol whose surface covers its needs, "
        "or (if it genuinely needs the whole shell) add it to ALLOWLIST with a "
        f"justification: {sorted(new)}"
    )


def test_ratchet_only_shrinks():
    live = _live_consumers()
    stale = set(ALLOWLIST) - live
    assert not stale, (
        "ALLOWLIST entries that no longer take `Shell` (migrated away). The "
        "ratchet only shrinks — delete these stale entries: " f"{sorted(stale)}"
    )


def test_every_allowlist_entry_has_justification():
    for key, reason in ALLOWLIST.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, (
            f"allowlist entry {key} needs a real justification")


def test_iocontext_migration_removed_input_cursor():
    """The Q1 IOContext migration narrowed InputCursorRegistry.cursor_for_fd
    and make_reader from `Shell` to IOContext — neither may appear as a
    full-Shell consumer."""
    live = _live_consumers()
    assert ("psh.io_redirect.input_cursor",
            "InputCursorRegistry.cursor_for_fd") not in live
    assert ("psh.builtins.input_reader", "make_reader") not in live


# --- Detector self-tests ----------------------------------------------------

def test_detector_flags_bare_shell():
    src = ("class Foo:\n"
           "    def bar(self, shell: 'Shell', fd: int) -> None: ...\n")
    assert ("psh.fake", "Foo.bar") in full_shell_consumers(src, "psh.fake")


def test_detector_flags_wrapped_shell():
    # Optional['Shell'], 'Shell | None', Callable[['Shell'], int] — all evade a
    # bare-name-only detector; all must fire here.
    src = (
        "from typing import Callable, Optional\n"
        "class Foo:\n"
        "    def a(self, shell: Optional['Shell']) -> None: ...\n"
        "    def b(self, shell: 'Shell | None') -> None: ...\n"
        "    def c(self, cb: \"Callable[['Shell'], int]\") -> None: ...\n"
    )
    found = full_shell_consumers(src, "psh.fake")
    assert {("psh.fake", "Foo.a"), ("psh.fake", "Foo.b"),
            ("psh.fake", "Foo.c")} <= found


def test_detector_flags_unannotated_shell():
    src = ("class Foo:\n"
           "    def sneaky(self, shell) -> None: ...\n")
    assert ("psh.fake", "Foo.sneaky") in full_shell_consumers(src, "psh.fake")


def test_detector_ignores_state_and_protocol_and_other_names():
    src = (
        "from typing import Optional\n"
        "class Foo:\n"
        "    def a(self, io_ctx: 'IOContext') -> None: ...\n"
        "    def b(self, state: 'ShellState') -> None: ...\n"
        "    def c(self, state: Optional['ShellState']) -> None: ...\n"
        "    def d(self, x: int) -> None: ...\n"
        "    def e(self, other) -> None: ...\n"   # unannotated but NOT named 'shell'
    )
    assert full_shell_consumers(src, "psh.fake") == set()


def test_detector_flags_class_attribute_shell():
    """5B.1: holding the whole Shell as a FIELD is the same reach as taking it
    as a parameter. The parameter-only detector returned nothing here."""
    src = ("class Foo:\n"
           "    shell: 'Shell'\n")
    assert ("psh.fake", "Foo.shell") in full_shell_consumers(src, "psh.fake")


def test_detector_flags_wrapped_class_attribute_shell():
    src = ("from typing import Optional\n"
           "class Foo:\n"
           "    a: Optional['Shell']\n"
           "    b: 'Shell | None'\n")
    found = full_shell_consumers(src, "psh.fake")
    assert {("psh.fake", "Foo.a"), ("psh.fake", "Foo.b")} <= found


def test_detector_flags_instance_assignment_with_an_undeclared_param():
    """5B.2: the shape NO declaration reveals.

    The parameter is unannotated AND not named ``shell``, so the parameter arm
    is silent; only the field's name says the whole shell is being held. This
    is the case the source-keyed design could not have caught.
    """
    src = ("class Foo:\n"
           "    def wire(self, s):\n"
           "        self.shell = s\n")
    assert ("psh.fake", "Foo.wire") in full_shell_consumers(src, "psh.fake")


def test_detector_flags_instance_assignment_to_underscore_shell():
    """``self._shell = s`` is the same reach one underscore away — the live
    spelling in ``core/scope.py#ScopeManager.set_shell``."""
    src = ("class Foo:\n"
           "    def set_shell(self, s):\n"
           "        self._shell = s\n")
    assert ("psh.fake", "Foo.set_shell") in full_shell_consumers(src, "psh.fake")


def test_detector_ignores_a_narrowing_assignment():
    """CONTROL, and the most important one in this file.

    ``self.mgr = shell.expansion_manager`` / ``self.state = shell.state`` are
    the migrations the campaign asks for. If the instance-assignment arm
    flagged those, the ratchet would report the fix as the defect. Only the
    ``shell`` parameter itself is a hit here.
    """
    src = ("class Foo:\n"
           "    def __init__(self, other):\n"
           "        self.mgr = other.expansion_manager\n"
           "        self.state = other.state\n"
           "        self.shell = other.shell\n")
    assert full_shell_consumers(src, "psh.fake") == set()


def test_detector_ignores_a_none_store():
    """``self.shell = None`` holds no shell."""
    src = ("class Foo:\n"
           "    def reset(self):\n"
           "        self.shell = None\n")
    assert full_shell_consumers(src, "psh.fake") == set()


def test_detector_ignores_a_non_shell_field_name():
    """A bare-name store into an unrelated field is not this arm's business."""
    src = ("class Foo:\n"
           "    def wire(self, s):\n"
           "        self.thing = s\n")
    assert full_shell_consumers(src, "psh.fake") == set()


def test_instance_assignment_arm_adds_no_allowlist_entries():
    """The arm is PROPHYLACTIC: it closes the gap without conscripting the
    tree.

    Measured before it was written: across the scanned modules the arm reports
    nothing the parameter/class-attribute arms did not already report, so
    ``ALLOWLIST`` neither grew nor needed the 5B.1-R0 growth exception. If this
    cell ever fails, a genuine smuggled store has appeared and needs a
    disposition — narrow it, or record it with a justification.
    """
    live = _live_consumers()
    assert live == set(ALLOWLIST), (
        "the scanned set no longer equals ALLOWLIST exactly: "
        f"new={sorted(live - set(ALLOWLIST))} stale={sorted(set(ALLOWLIST) - live)}")


def test_detector_ignores_class_attribute_shellstate():
    """``ShellState`` is a narrowing, not a service locator — it is not counted
    as a PARAMETER and must not be counted as an ATTRIBUTE either, or the
    ratchet would flag the very migrations the campaign asked for.
    ``JobRuntime.shell_state`` is the live instance of this shape."""
    src = ("from typing import Optional\n"
           "class Foo:\n"
           "    shell_state: 'Optional[ShellState]'\n"
           "    state: 'ShellState'\n")
    assert full_shell_consumers(src, "psh.fake") == set()


# --- Coverage-assertion self-tests (INJECTED enumeration, never real commits) -

def test_coverage_flags_an_undispositioned_post_endpoint_module():
    """The offender case: a module born after the endpoint that is in neither
    register must be reported."""
    uncovered = uncovered_post_endpoint_modules(
        {"psh/newpkg/newborn.py"}, scanned=[], out_of_scope={})
    assert uncovered == ["psh/newpkg/newborn.py"]


def test_coverage_accepts_a_scanned_post_endpoint_module():
    assert uncovered_post_endpoint_modules(
        {"psh/newpkg/newborn.py"},
        scanned=["psh/newpkg/newborn.py"], out_of_scope={}) == []


def test_coverage_accepts_a_declared_out_of_scope_module():
    assert uncovered_post_endpoint_modules(
        {"psh/newpkg/newborn.py"}, scanned=[],
        out_of_scope={"psh/newpkg/newborn.py": "generated stub, no defs"}) == []


def test_coverage_reports_only_the_undispositioned_one():
    """Mixed input: the two dispositioned modules stay silent, the third does
    not — so a passing coverage assertion cannot be passing vacuously."""
    assert uncovered_post_endpoint_modules(
        {"psh/a.py", "psh/b.py", "psh/c.py"},
        scanned=["psh/a.py"],
        out_of_scope={"psh/b.py": "declared"}) == ["psh/c.py"]


def test_every_out_of_scope_entry_has_justification():
    for path, reason in POST_ENDPOINT_OUT_OF_SCOPE.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, (
            f"out-of-scope entry {path} needs a real justification")


def test_a_non_ancestor_endpoint_warns_with_its_reason():
    """The vacuous-pass window is LOUD, and the warning says WHY.

    A RED arm that only checks "something was raised" would be satisfied by any
    failure at all — the wrong-reason trap. This asserts the warning names the
    vacuity, so a future edit that keeps warning but drops the explanation is
    caught too.
    """
    with pytest.warns(UserWarning, match="VACUOUSLY") as caught:
        _warn_selfcheck_unverified(
            "POST_ENDPOINT coverage",
            f"SCOPE_ENDPOINT {SCOPE_ENDPOINT} is NOT an ancestor of HEAD, so "
            "the range is empty and this coverage check would pass VACUOUSLY",
            f"{SCOPE_ENDPOINT}..HEAD")
    text = str(caught[0].message)
    assert "TRUSTED UNVERIFIED" in text        # the shared loud-warning shape
    assert "NOT an ancestor" in text           # the specific cause
    assert SCOPE_ENDPOINT in text              # which endpoint


def test_ancestor_check_answers_true_for_the_pinned_endpoint():
    """Control for the arm above: on a normal checkout the endpoint IS an
    ancestor, so the coverage test runs for real rather than skipping. Without
    this, the warn path could swallow every invocation and both cells would
    still look healthy."""
    ancestry = _endpoint_is_ancestor_of_head()
    if ancestry is None:
        pytest.skip("git unavailable")
    assert ancestry is True, (
        f"{SCOPE_ENDPOINT} is not an ancestor of HEAD — the coverage assertion "
        "is skipping, not checking")
