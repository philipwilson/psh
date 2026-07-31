"""Anti-spawn guard (slot 1.2, reappraisal #22 HIGH-1 second half).

Reappraisal #22 HIGH-1 was two defects. Slot 1.1 closed the first structurally
(a typed ``ShellRunResult`` + ``is_comparable``, so a harness failure can never
be compared as shell behavior). This guard closes the second: ~95 differential
modules USED to spawn bash/psh with raw ``subprocess`` and never touched the
typed runner, so the 1.1 safety net never saw them. After slot 1.2's migration,
every differential launch goes through
``tests/harness/shell_oracle.py`` (``run_shell_case`` via ``run_psh``/
``run_bash``). This guard makes that permanent: an *oracle-bearing* test module
may not create a process directly.

**Scope (oracle-bearing set):** a module under ``tests/conformance/`` or
``tests/harness/``, or one whose source IMPORTS ``shell_oracle`` (a real
import, not a docstring mention). Those are the modules where a raw spawn is a
differential-comparison bypass.  At base ``e52957d4`` this scope is **182
modules**, of which **96 spawn directly** (245 sites): the runner itself plus
the **95 migration targets** (243 sites).  Replay with
``python tests/harness/census_replay.py <tree>/tests``; derivation in
``tests/harness/oracle_migration_census.md``.  Most bearing-set modules never
spawn directly at all (they go through ``ConformanceTest``/``run_shell_case``),
so the census's "95/95 differential" describes the SPAWNER SUBSET — not this
182-module scope.

**What is rejected — TWO faces:**

1. *subprocess family* (``find_direct_spawns``):
   ``subprocess.run/Popen/call/check_output/check_call/getoutput/
   getstatusoutput`` and ``os.system``/``os.popen``.
2. *non-subprocess family* (``find_non_subprocess_spawns``):
   ``pexpect.spawn``/``spawnu``/``run``, ``pty.spawn``/``fork``/``openpty``,
   ``os.fork``/``forkpty``/``posix_spawn*``/``exec*``.

Face 2 exists because a PTY differential is still a differential: round-3
verification found a module driving BOTH psh and the resolved bash oracle
through ``pexpect.spawn`` — a genuine bash comparison whose verdict rested on
an unowned harness, invisible to a subprocess-only guard.  **PTY interactivity
is out of the run-to-completion runner's reach** (it has no terminal), so such
a module is not migrated; it is classified and registered (``PTY_REGISTRY``),
which is what keeps it visible.

**Honest limits (documented, not defects):** both faces match the STATIC,
attribute-access form on a module named exactly ``subprocess``/``os``/
``pexpect``/``pty``. Neither catches:

* a bare-name import — ``from subprocess import run; run(...)``;
* an ALIASED import — ``import subprocess as sp; sp.run(...)`` (or
  ``import os as _os; _os.system(...)``): the detector keys on the base NAME,
  so an alias reads as an ordinary attribute call;
* ``getattr(subprocess, 'run')(...)`` or a spawn assembled/``eval``-ed from
  strings;
* a spawn hidden behind a helper in a module OUTSIDE the scanned set;
* whole process-creation FAMILIES that are deliberately not detected because
  nothing in the tree uses them and a detector would be speculative:
  ``multiprocessing.Process`` (and the other multiprocessing start methods) and
  ``asyncio.create_subprocess_exec``/``create_subprocess_shell``. If a
  differential ever arrives through one of those, extend the detectors — do not
  allowlist the module.

A tree audit at adoption found ZERO bare-name and ZERO aliased subprocess/os
imports in the bearing set (``from subprocess import`` / ``import subprocess as``
/ ``import os as`` all return no hits), so the attribute form is the whole live
surface. If any of these appears, extend ``find_direct_spawns`` (resolve import
aliases) rather than allowlisting it.

**Allowlist (two parts, integrator ruling):**
(a) ``NAMED_ALLOWLIST`` — the harness itself plus spawns that genuinely CANNOT
    use the run-to-completion runner (mid-run signal, concurrent writer,
    ``preexec_fn``, non-seekable stdin), each with owner + reason + removal.
(b) ``PSH_ONLY_REGISTRY`` — a FROZEN, SHRINK-ONLY registry of PSH-ONLY raw
    spawners (launch only psh, no bash comparison → no HIGH-1 false IDENTICAL),
    approved to stay raw with a one-line class reason.
Both are GROWTH-REFUSING: an entry may leave (it must, once the file stops
spawning — ``test_allowlist_entries_still_spawn``), but adding one requires a
recorded justification here. The bearing set is 95/95 DIFFERENTIAL modules, so
(b) is INTENTIONALLY EMPTY (no psh-only raw spawner in scope) and every residual
raw spawn is a differential comparison the runner cannot express (all in (a)).
The CLAUDE.md-sanctioned psh-only lifecycle modules are OUTSIDE this scope
entirely (they do not import shell_oracle and are not under conformance).
"""
import ast
import os
import sys

import pytest

TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# subprocess.<attr>(...) spawn methods and os.<attr>(...) shell launchers.
# getoutput/getstatusoutput are spawn-capable too (each runs a command through a
# shell); zero uses today — listed so the surface is complete rather than lucky.
_SUBPROCESS_SPAWNS = frozenset({"run", "Popen", "call", "check_output",
                                "check_call", "getoutput", "getstatusoutput"})
_OS_SPAWNS = frozenset({"system", "popen"})

# The NON-subprocess process-creation family.  These never reach
# ``find_direct_spawns`` (different module, different call shape), yet such a
# module can be every bit as much a bash differential: round-3 verification
# found exactly that — a PTY parity test driving BOTH psh and the resolved bash
# oracle through ``pexpect.spawn``, sitting invisibly inside the bearing set.
_PEXPECT_SPAWNS = frozenset({"spawn", "spawnu", "run", "runu"})
_PTY_SPAWNS = frozenset({"spawn", "fork", "openpty"})
_OS_PROCESS_SPAWNS = frozenset({
    "fork", "forkpty", "posix_spawn", "posix_spawnp",
    "execv", "execve", "execvp", "execvpe",
    "execl", "execle", "execlp", "execlpe",
    # os.spawn* — same static call shape, so trivially detectable; listed for
    # completeness rather than because anything uses them today.
    "spawnl", "spawnle", "spawnlp", "spawnlpe",
    "spawnv", "spawnve", "spawnvp", "spawnvpe",
})

# The ONE exact directory the scan skips: it holds the SYNTHETIC OFFENDER
# fixture, a deliberate spawn used to prove the guard fires.  The skip is
# EXACT-PATH, not name-based: a directory merely NAMED oracle_spawn_fixtures
# elsewhere in the tree (e.g. tests/conformance/oracle_spawn_fixtures/) is
# scanned normally, so an offender cannot hide by borrowing the name (round-1
# verification planted exactly that and it went undetected under the old
# name-based skip).
_FIXTURE_DIR = "oracle_spawn_fixtures"
_FIXTURE_REL = f"unit/tooling/{_FIXTURE_DIR}"

# The allowlist has TWO parts (integrator ruling, slot 1.2). The census finding
# it rests on concerns the SPAWNER SUBSET of the bearing set (95 of the 182
# scanned modules): all 95 are DIFFERENTIAL (36 conformance + 59 shell_oracle
# importers, every one comparing against bash) — there is NO psh-only spawner
# module in scope. (The ~70 CLAUDE.md exec/fd/lifecycle psh-only modules neither
# import shell_oracle nor live under conformance, so they are OUTSIDE this guard
# entirely.) So part (b) is empty.

# (a) NAMED allowlist: the harness itself + spawns that genuinely CANNOT go
# through the run-to-completion runner. owner + reason + removal condition each.
NAMED_ALLOWLIST = {
    "harness/shell_oracle.py":
        "owner=slot1.1. It IS the runner — owns the single real "
        "subprocess.Popen (and the _bash_version probe). Removal: never.",
    "integration/job_control/test_exit_trap_paths.py":
        "owner=slot1.2. DIFFERENTIAL mid-run-signal harness: delivers a signal "
        "to a running psh AND to a running bash (_spawn_and_signal, its "
        "_bash_signal caller, and the stdin-mode Popen in "
        "TestExitTrapStdin) to COMPARE the EXIT trap on a fatal signal; "
        "the run-to-completion runner cannot signal a running child. Its "
        "run-to-completion bash-differential helpers ARE migrated. Removal: "
        "run_shell_case gains a mid-run-signal hook, or a PTY/pexpect harness.",
    "system/test_script_input_sources.py":
        "owner=slot1.2. Concurrent FIFO writer: a bash writer Popen must run "
        "CONCURRENTLY with the blocking psh fifo reader (a fifo open blocks "
        "until both ends are open); routing it through the blocking runner "
        "would deadlock. The psh reader side IS migrated. Removal: a "
        "non-blocking writer helper, or a concurrent-writer runner mode.",
    "system/test_stdin_startup_robustness.py":
        "owner=slot1.2. Needs preexec_fn=os.close(0) (the close-fd0 cases) or "
        "a live file object on stdin — neither expressible through the runner. "
        "The raw-byte-stdin cases DO route through the runner. Removal: the "
        "runner gains a close-fd0 / file-object stdin option.",
    # REMOVED (allowlist shrank): system/test_stdin_script_lazy_read.py. Its
    # removal condition — "the runner gains a non-seekable/pipe stdin mode" —
    # is MET: run_shell_case's stdin_mode='pipe'/'file' gives the child a real
    # non-seekable pipe or a regular seekable file, so the module's pipe-vs-
    # seekable subject survives the migration and it now routes 100% through
    # the runner.
}

# (b) FROZEN, SHRINK-ONLY registry of PSH-ONLY raw spawners: a spawn that only
# ever launches psh with NO bash comparison — so it cannot produce a HIGH-1
# false IDENTICAL and is NOT this slot's defect (approved to stay raw, one-line
# class reason). GROWTH-REFUSING: a NEW psh-only raw spawner appearing in the
# bearing set fails the guard; this registry only loses entries.
#
# INTENTIONALLY EMPTY: the census found the bearing set is 95/95 DIFFERENTIAL
# modules, and after migration every residual raw spawn is a differential
# comparison the runner cannot express (all NAMED above) — there is no psh-only
# raw spawner in scope. The structure is kept so a future psh-only debt would
# be registered here rather than silently allowlisted. (The ~70 CLAUDE.md
# psh-only lifecycle modules are OUTSIDE the bearing set and never reach this
# guard.)
PSH_ONLY_REGISTRY: dict = {}

# The guard treats both parts identically (any listed module may spawn); the
# split is documentation of WHY each is approved.
ALLOWLIST = {**NAMED_ALLOWLIST, **PSH_ONLY_REGISTRY}

# FROZEN MEMBERSHIP — the census-justified set, pinned literally.  Growth
# refusal must be MECHANICAL, not prose: round-1 verification proved that a
# bogus ALLOWLIST entry plus an injected real spawn passed the guard silently,
# because "growth-refusing" lived only in a comment.  With this pin, adding an
# entry fails ``test_allowlist_membership_is_frozen`` until the author ALSO
# edits this expected set — a visible two-place change the reviewer sees.
_EXPECTED_NAMED_ALLOWLIST = frozenset({
    "harness/shell_oracle.py",
    "integration/job_control/test_exit_trap_paths.py",
    "system/test_script_input_sources.py",
    "system/test_stdin_startup_robustness.py",
})
_EXPECTED_PSH_ONLY_REGISTRY: frozenset = frozenset()

# (c) PTY / NON-SUBPROCESS registry — its OWN list, deliberately separate from
# NAMED_ALLOWLIST.  Reason it cannot simply join (a): the allowlist hygiene test
# ``test_allowlist_entries_still_spawn`` keys on ``find_direct_spawns``, which by
# construction never sees a pexpect/pty spawn — a PTY module parked in (a) would
# make that hygiene test fail (or, worse, be loosened until it proved nothing).
# This registry is policed by ``find_non_subprocess_spawns`` instead, so every
# hygiene test stays meaningful.  Same growth-refusing discipline: owner +
# reason + removal condition, plus a frozen membership pin.
PTY_REGISTRY = {
    "system/interactive/test_multiline_immediate_error_i3.py":
        "owner=slot1.2 (module pre-exists this slot; classified here in round "
        "3). PTY bash-DIFFERENTIAL: drives psh AND the resolved bash oracle "
        "through pexpect.spawn over a pseudo-terminal (TERM=xterm) and compares "
        "the LINE INDEX at which each reports a mid-construct syntax error. "
        "Interactive PTY behavior IS the subject — the run-to-completion runner "
        "has no terminal and cannot serve it. Removal: run_shell_case grows a "
        "PTY mode, or the parity rows move to a shared PTY differential harness "
        "that owns oracle resolution and typed outcomes.",
    "system/interactive/test_substitution_abort_interactive_pty.py":
        "owner=slot2.4 (ruling R6-C). PTY bash-DIFFERENTIAL: drives psh (both "
        "parsers) AND the resolved bash oracle through pexpect.spawn over a "
        "pseudo-terminal (TERM=xterm) and compares the status each shell "
        "leaves after a substitution-body syntax error, plus REPL survival. "
        "The TERMINAL is the subject: an interactive shell is a different "
        "is_script_mode world from `-i -c`, and round 5's claim that PTY "
        "coverage falls out of the non-interactive matrix was measured FALSE. "
        "Removal: as above — a PTY mode in run_shell_case, or a shared PTY "
        "differential harness owning oracle resolution and typed outcomes.",
}
_EXPECTED_PTY_REGISTRY = frozenset(PTY_REGISTRY)

# Per-module EXPECTED SPAWN-SITE COUNTS.  The membership pins stop the LISTS
# from growing; these stop an already-listed MODULE from growing new raw spawns.
# Round-4 verification proved that gap had teeth: a brand-new raw
# ``subprocess.run([resolve_bash().path, ...])`` bash-differential appended to an
# allowlisted module left the entire guard suite GREEN, because approval was
# per MODULE. Approval is now per SITE COUNT, so adding a spawn to an approved
# module is the same visible two-place change as adding an entry.
_EXPECTED_SPAWN_SITES = {
    # Popen + version probe + the `ps` descendant enumeration in
    # _killpg_sigkill. The third CANNOT route through the runner: it is the
    # cleanup that makes the runner's own kill authoritative, so going through
    # the runner would be circular. It launches `ps` with a fixed argv, never a
    # shell, and reads only a pid/ppid table — no shell behaviour is observed,
    # so it cannot manufacture a false IDENTICAL. It exists because killpg on
    # the session leader misses children a job-control shell has setpgid'd into
    # groups of their own, which let a writer survive the cap kill and fill an
    # already-unlinked capture file — the nightly's [Errno 28] deaths.
    "harness/shell_oracle.py": 3,
    "integration/job_control/test_exit_trap_paths.py": 2,  # psh + bash signal harness
    "system/test_script_input_sources.py": 2,              # two fifo writers
    "system/test_stdin_startup_robustness.py": 1,          # close-fd0 / file-object branch
}
_EXPECTED_PTY_SITES = {
    "system/interactive/test_multiline_immediate_error_i3.py": 2,  # psh + bash spawn
    "system/interactive/test_substitution_abort_interactive_pty.py": 2,  # psh + bash
}


def _imports_shell_oracle(tree):
    """True iff *tree* really imports shell_oracle (not just mentions it).

    Covers BOTH ``ImportFrom`` shapes: ``from shell_oracle import x`` (the name
    is in ``node.module``) and ``from tests.harness import shell_oracle`` (the
    name is an ALIAS, with ``node.module`` = the package) — the second form used
    to read as non-bearing, which would have let a module opt out of the guard
    by changing its import style (round-3 finding).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "shell_oracle" in node.module:
                return True
            for alias in node.names:
                if "shell_oracle" in alias.name:
                    return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "shell_oracle" in alias.name:
                    return True
    return False


def find_non_subprocess_spawns(src):
    """Return [(lineno, kind)] for PTY / fork / exec process creation.

    The family ``find_direct_spawns`` cannot see: ``pexpect.spawn`` (and
    friends), ``pty.spawn``/``pty.fork``, and ``os.fork``/``os.forkpty``/
    ``os.posix_spawn*``/``os.exec*``.  Same static, attribute-access limits as
    the subprocess detector (an aliased import or a getattr call is not caught).
    """
    tree = ast.parse(src)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)):
            continue
        base, attr = node.func.value.id, node.func.attr
        if base == "pexpect" and attr in _PEXPECT_SPAWNS:
            hits.append((node.lineno, f"pexpect.{attr}"))
        elif base == "pty" and attr in _PTY_SPAWNS:
            hits.append((node.lineno, f"pty.{attr}"))
        elif base == "os" and attr in _OS_PROCESS_SPAWNS:
            hits.append((node.lineno, f"os.{attr}"))
    return hits


def find_direct_spawns(src):
    """Return [(lineno, 'subprocess.run' | 'os.system' | ...)] for *src*."""
    tree = ast.parse(src)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)):
            continue
        base, attr = node.func.value.id, node.func.attr
        if base == "subprocess" and attr in _SUBPROCESS_SPAWNS:
            hits.append((node.lineno, f"subprocess.{attr}"))
        elif base == "os" and attr in _OS_SPAWNS:
            hits.append((node.lineno, f"os.{attr}"))
    return hits


def iter_oracle_bearing_modules():
    """Yield (rel, path, src) for every oracle-bearing module in scope.

    Skips ONLY the exact tooling fixture directory (``_FIXTURE_REL``), where the
    synthetic offender lives by design. A same-named directory anywhere else is
    scanned normally — see ``test_only_the_exact_fixture_path_is_skipped``.
    """
    for dirpath, dirnames, filenames in os.walk(TESTS_ROOT):
        rel_dir = os.path.relpath(dirpath, TESTS_ROOT).replace(os.sep, "/")
        dirnames[:] = [
            d for d in dirnames
            if d != "__pycache__"
            and f"{rel_dir}/{d}".lstrip("./") != _FIXTURE_REL]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, TESTS_ROOT).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                src = f.read()
            in_conf = rel.startswith("conformance/")
            in_harness = rel.startswith("harness/")
            if in_conf or in_harness or _imports_shell_oracle(ast.parse(src)):
                yield rel, path, src


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

def test_no_direct_spawn_in_oracle_bearing_modules():
    """No oracle-bearing module creates a process directly (bar the allowlist)."""
    problems = []
    for rel, _path, src in iter_oracle_bearing_modules():
        if rel in ALLOWLIST:
            continue
        for lineno, kind in find_direct_spawns(src):
            problems.append(f"tests/{rel}:{lineno}: {kind}")
    assert not problems, (
        "oracle-bearing test modules must route every process launch through "
        "the typed runner (run_shell_case / run_psh / run_bash), never raw "
        "subprocess/os — a raw spawn bypasses the is_comparable safety net "
        "(reappraisal #22 HIGH-1). Offenders:\n  " + "\n  ".join(problems)
        + "\n(If a launch GENUINELY cannot use the runner, add a justified "
        "ALLOWLIST entry with owner + reason + removal condition.)")


# ---------------------------------------------------------------------------
# Allowlist hygiene (shrinking / growth-refusing)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", sorted(ALLOWLIST))
def test_allowlist_entries_exist(rel):
    assert os.path.isfile(os.path.join(TESTS_ROOT, rel)), (
        f"ALLOWLIST entry {rel!r} does not exist — prune it")


@pytest.mark.parametrize("rel", sorted(ALLOWLIST))
def test_allowlist_entries_still_spawn(rel):
    """A file that no longer spawns directly must LEAVE the allowlist (shrink)."""
    with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
        src = f.read()
    assert find_direct_spawns(src), (
        f"{rel} no longer creates a process directly — remove its ALLOWLIST "
        "entry (the guard is shrinking).")


def test_no_non_subprocess_spawn_in_oracle_bearing_modules():
    """PTY-aware face: no oracle-bearing module creates a process by
    pexpect/pty/fork/exec either, unless it is in the PTY registry.

    Round-3 finding: a PTY parity test driving BOTH psh and the resolved bash
    oracle sat inside the bearing set, invisible to the subprocess-only guard
    and absent from the census. This closes that blind spot.
    """
    problems = []
    for rel, _path, src in iter_oracle_bearing_modules():
        if rel in PTY_REGISTRY:
            continue
        for lineno, kind in find_non_subprocess_spawns(src):
            problems.append(f"tests/{rel}:{lineno}: {kind}")
    assert not problems, (
        "oracle-bearing modules must not create processes via pexpect/pty/"
        "fork/exec outside the typed runner. A PTY differential is still a "
        "differential: its verdict must not rest on an unowned harness. "
        "Offenders:\n  " + "\n  ".join(problems)
        + "\n(If PTY interactivity is genuinely the subject, add a justified "
        "PTY_REGISTRY entry with owner + reason + removal condition.)")


@pytest.mark.parametrize("rel", sorted(PTY_REGISTRY))
def test_pty_registry_entries_exist(rel):
    assert os.path.isfile(os.path.join(TESTS_ROOT, rel)), (
        f"PTY_REGISTRY entry {rel!r} does not exist — prune it")


@pytest.mark.parametrize("rel", sorted(PTY_REGISTRY))
def test_pty_registry_entries_still_pty_spawn(rel):
    """Shrink discipline, policed by the RIGHT detector.

    Keyed on ``find_non_subprocess_spawns`` — NOT ``find_direct_spawns``, which
    by construction can never see a pexpect/pty spawn. Using the subprocess
    detector here would make this hygiene test vacuous (it would fail for every
    genuine PTY entry, inviting someone to delete or loosen it).
    """
    with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
        src = f.read()
    assert find_non_subprocess_spawns(src), (
        f"{rel} no longer creates a PTY/fork/exec process — remove its "
        "PTY_REGISTRY entry (the registry is shrinking).")


def test_pty_registry_membership_is_frozen():
    """Mechanical growth refusal for the PTY registry (same contract as the
    allowlist): adding an entry is a visible two-place change."""
    assert set(PTY_REGISTRY) == set(_EXPECTED_PTY_REGISTRY), (
        "PTY_REGISTRY membership changed. Unexpected additions: "
        f"{sorted(set(PTY_REGISTRY) - _EXPECTED_PTY_REGISTRY)}; missing: "
        f"{sorted(_EXPECTED_PTY_REGISTRY - set(PTY_REGISTRY))}. An addition "
        "needs owner + reason + removal condition AND an edit to "
        "_EXPECTED_PTY_REGISTRY.")


def test_pty_registry_is_disjoint_from_the_subprocess_allowlists():
    """The three lists govern different detectors; a module in two of them
    would be approved for a spawn family nobody checked."""
    assert not (set(PTY_REGISTRY) & set(ALLOWLIST)), (
        "a module may not sit in both the subprocess allowlist and the PTY "
        "registry — split it or justify each face explicitly")


def test_allowlist_membership_is_frozen():
    """MECHANICAL growth refusal: the allowlist is EXACTLY the census-justified
    set. Adding (or silently swapping) an entry fails here until the expected
    set is edited too — so allowlist growth is a visible, reviewable two-place
    change instead of a one-line slip. Shrinking is equally pinned: removing a
    genuine entry must be accompanied by removing it here (and
    ``test_allowlist_entries_still_spawn`` forces removal once a file stops
    spawning).
    """
    assert set(NAMED_ALLOWLIST) == set(_EXPECTED_NAMED_ALLOWLIST), (
        "NAMED_ALLOWLIST membership changed. Unexpected additions: "
        f"{sorted(set(NAMED_ALLOWLIST) - _EXPECTED_NAMED_ALLOWLIST)}; "
        f"missing: {sorted(_EXPECTED_NAMED_ALLOWLIST - set(NAMED_ALLOWLIST))}. "
        "An addition needs a recorded justification (owner + reason + removal "
        "condition) AND an edit to _EXPECTED_NAMED_ALLOWLIST.")
    assert set(PSH_ONLY_REGISTRY) == set(_EXPECTED_PSH_ONLY_REGISTRY), (
        "PSH_ONLY_REGISTRY membership changed (it is INTENTIONALLY EMPTY — the "
        "bearing set is 95/95 differential). A new psh-only raw spawner must be "
        "justified here AND added to _EXPECTED_PSH_ONLY_REGISTRY.")


def test_expected_site_counts_cover_exactly_the_approved_modules():
    """Every approved module has a site budget, and no budget is orphaned."""
    assert set(_EXPECTED_SPAWN_SITES) == set(ALLOWLIST), (
        "each subprocess-allowlist entry needs exactly one site budget: "
        f"missing {sorted(set(ALLOWLIST) - set(_EXPECTED_SPAWN_SITES))}, "
        f"orphaned {sorted(set(_EXPECTED_SPAWN_SITES) - set(ALLOWLIST))}")
    assert set(_EXPECTED_PTY_SITES) == set(PTY_REGISTRY), (
        "each PTY-registry entry needs exactly one site budget: "
        f"missing {sorted(set(PTY_REGISTRY) - set(_EXPECTED_PTY_SITES))}, "
        f"orphaned {sorted(set(_EXPECTED_PTY_SITES) - set(PTY_REGISTRY))}")


@pytest.mark.parametrize("rel", sorted(_EXPECTED_SPAWN_SITES))
def test_allowlisted_module_has_exactly_its_budgeted_spawn_sites(rel):
    """An APPROVED module may not grow NEW raw spawns (round-4 blocker).

    Approval is per site count, not per module: the four entries were approved
    for specific, justified launches, and a fifth appearing later is an
    unreviewed HIGH-1 bypass regardless of which file it lands in.
    """
    with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
        hits = find_direct_spawns(f.read())
    assert len(hits) == _EXPECTED_SPAWN_SITES[rel], (
        f"{rel} has {len(hits)} direct spawn site(s) at "
        f"{[ln for ln, _ in hits]}, budgeted {_EXPECTED_SPAWN_SITES[rel]}. "
        "A NEW raw spawn in an allowlisted module is still an unreviewed "
        "bypass — route it through the runner, or justify it here AND update "
        "_EXPECTED_SPAWN_SITES (a deliberate two-place change). A DROP means "
        "the budget should shrink.")


@pytest.mark.parametrize("rel", sorted(_EXPECTED_PTY_SITES))
def test_pty_registry_module_has_exactly_its_budgeted_spawn_sites(rel):
    with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
        hits = find_non_subprocess_spawns(f.read())
    assert len(hits) == _EXPECTED_PTY_SITES[rel], (
        f"{rel} has {len(hits)} PTY/fork/exec site(s) at "
        f"{[ln for ln, _ in hits]}, budgeted {_EXPECTED_PTY_SITES[rel]}.")


def test_growth_face_new_spawn_inside_an_allowlisted_module_is_refused():
    """THE round-4 attack, replayed: append a brand-new raw bash differential to
    an ALLOWLISTED module. Under module-granular approval the guard stayed
    green; the site budget now refuses it.

    Operates on the module's SOURCE plus the appended offense — the real file is
    never touched, so the attack is replayed without mutating the tree.
    """
    rel = "system/test_stdin_startup_robustness.py"
    with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
        clean = f.read()
    assert len(find_direct_spawns(clean)) == _EXPECTED_SPAWN_SITES[rel]

    attacked = clean + (
        "\n\ndef _sneaky_new_differential(cmd):\n"
        "    import subprocess\n"
        "    from shell_oracle import resolve_bash\n"
        "    return subprocess.run([resolve_bash().path, '-c', cmd],\n"
        "                          capture_output=True, text=True)\n")
    grown = find_direct_spawns(attacked)
    assert len(grown) == _EXPECTED_SPAWN_SITES[rel] + 1, (
        "the appended raw spawn must be detected at all")
    # The budget assertion is what turns detection into refusal.
    with pytest.raises(AssertionError, match="direct spawn site"):
        assert len(grown) == _EXPECTED_SPAWN_SITES[rel], (
            f"{rel} has {len(grown)} direct spawn site(s) at "
            f"{[ln for ln, _ in grown]}, budgeted "
            f"{_EXPECTED_SPAWN_SITES[rel]}.")


def test_allowlist_parts_are_disjoint_and_complete():
    """The two documented parts partition the allowlist (no module in both,
    nothing outside them). Part (a) = NAMED un-runnerable + the harness; part
    (b) = the frozen psh-only registry."""
    assert not (set(NAMED_ALLOWLIST) & set(PSH_ONLY_REGISTRY)), (
        "a module may not be in BOTH allowlist parts")
    assert set(ALLOWLIST) == set(NAMED_ALLOWLIST) | set(PSH_ONLY_REGISTRY)


def test_psh_only_registry_entries_launch_only_psh():
    """A registry (b) entry must be genuinely PSH-ONLY — its direct spawns
    launch psh (or a python child), never the bash oracle. A residual bash spawn
    means it belongs in the NAMED part (a), not the frozen psh-only registry."""
    for rel in PSH_ONLY_REGISTRY:
        with open(os.path.join(TESTS_ROOT, rel), encoding="utf-8") as f:
            src = f.read()
        assert "resolve_bash().path" not in src and "[BASH" not in src, (
            f"{rel} has a residual bash spawn — move it to NAMED_ALLOWLIST")


# ---------------------------------------------------------------------------
# Mutation check: the SYNTHETIC OFFENDER must be caught (sequence-doc §5.6).
# The guard is NEW in this slot, so on base there was no guard and the offender
# would pass undetected — this proves the detector fires now.
# ---------------------------------------------------------------------------

def test_guard_fires_on_synthetic_offender_fixture():
    """The fixture is oracle-bearing AND spawns directly: were it not in the
    skipped fixtures dir, the guard would flag it."""
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           _FIXTURE_DIR, "offender_module.py")
    with open(fixture, encoding="utf-8") as f:
        src = f.read()
    assert _imports_shell_oracle(ast.parse(src)), "fixture must be oracle-bearing"
    hits = find_direct_spawns(src)
    assert hits, "guard failed to catch the synthetic offender's direct spawn"
    assert any(k == "subprocess.run" for _, k in hits)


def test_only_the_exact_fixture_path_is_skipped(tmp_path, monkeypatch):
    """A directory that merely BORROWS the fixture name elsewhere in the tree is
    still scanned — an offender cannot hide by naming its folder
    ``oracle_spawn_fixtures``.

    Round-1 verification planted an offender in
    ``tests/conformance/oracle_spawn_fixtures/`` and the old NAME-based skip let
    it through. This replays that attack against the exact-path skip, in a
    throwaway tree so the real suite is untouched.
    """
    fake_root = tmp_path / "tests"
    # The legitimate skipped location (must stay skipped)...
    legit = fake_root / "unit" / "tooling" / _FIXTURE_DIR
    legit.mkdir(parents=True)
    (legit / "offender_module.py").write_text(
        "import subprocess\nfrom shell_oracle import is_comparable\n"
        "subprocess.run(['x'])\n")
    # ...and the IMPOSTOR borrowing the name elsewhere (must be scanned).
    impostor = fake_root / "conformance" / _FIXTURE_DIR
    impostor.mkdir(parents=True)
    (impostor / "sneaky.py").write_text(
        "import subprocess\nsubprocess.run(['x'])\n")

    monkeypatch.setattr(sys.modules[__name__], "TESTS_ROOT", str(fake_root))
    scanned = {rel for rel, _, _ in iter_oracle_bearing_modules()}
    assert f"unit/tooling/{_FIXTURE_DIR}/offender_module.py" not in scanned, (
        "the exact tooling fixture path must stay skipped")
    assert f"conformance/{_FIXTURE_DIR}/sneaky.py" in scanned, (
        "a same-named directory elsewhere must NOT be skipped — an offender "
        "could hide there (round-1 verification finding)")


def test_fixture_dir_is_excluded_from_the_scan():
    """The offender fixture must NOT appear in the scanned set (else it would
    fail the real guard).

    Matches the EXACT fixture path, not the bare directory NAME: a substring
    test would ALSO be satisfied by a same-named directory elsewhere in the tree
    and would report the wrong thing (a misattributed diagnostic) — the very
    hole ``test_only_the_exact_fixture_path_is_skipped`` closes.
    """
    scanned = {rel for rel, _, _ in iter_oracle_bearing_modules()}
    assert f"{_FIXTURE_REL}/offender_module.py" not in scanned


def test_fixture_dir_holds_only_the_known_offender():
    """Close the hole: the skipped dir may hold ONLY the offender fixture, so
    nothing else can hide a real spawn there."""
    fixture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               _FIXTURE_DIR)
    py = sorted(f for f in os.listdir(fixture_dir) if f.endswith(".py"))
    assert py == ["offender_module.py", "pty_offender_module.py"], (
        f"the guard skips {_FIXTURE_DIR}/; it may hold ONLY the two known "
        f"offender fixtures, found {py}")


def test_pty_face_fires_on_synthetic_pty_offender_fixture():
    """Mutation check for the PTY face: the fixture is oracle-bearing AND
    spawns a PTY process, so — were it not in the skipped fixtures dir — the
    PTY guard would flag it. The subprocess detector, by contrast, must NOT
    see it: that asymmetry is exactly why the PTY face had to exist.
    """
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           _FIXTURE_DIR, "pty_offender_module.py")
    with open(fixture, encoding="utf-8") as f:
        src = f.read()
    assert _imports_shell_oracle(ast.parse(src)), "fixture must be oracle-bearing"
    hits = find_non_subprocess_spawns(src)
    assert any(k == "pexpect.spawn" for _, k in hits), hits
    # The blind spot the PTY face closes: the subprocess detector sees nothing.
    assert find_direct_spawns(src) == []


# ---------------------------------------------------------------------------
# Detector unit tests (string snippets)
# ---------------------------------------------------------------------------

def test_detector_catches_each_spawn_form():
    snippet = (
        "import subprocess, os, sys\n"
        "subprocess.run([sys.executable, '-c', 'x'])\n"
        "subprocess.Popen(['a'])\n"
        "subprocess.check_output(['a'])\n"
        "os.system('echo hi')\n"
        "os.popen('echo hi')\n"
    )
    kinds = {k for _, k in find_direct_spawns(snippet)}
    assert kinds == {"subprocess.run", "subprocess.Popen",
                     "subprocess.check_output", "os.system", "os.popen"}


def test_growth_face_a_bogus_allowlist_entry_is_refused(monkeypatch):
    """THIRD offender face (round-1 blocker): allowlist GROWTH itself.

    The attack the verifier ran: add a bogus ALLOWLIST entry for a module and
    inject a real spawn into it — under prose-only growth refusal the guard
    stayed green. Replayed here: mutating NAMED_ALLOWLIST now trips the frozen
    membership pin, so the growth is refused mechanically.
    """
    mod = sys.modules[__name__]
    real_named, real_registry = dict(NAMED_ALLOWLIST), dict(PSH_ONLY_REGISTRY)

    # Face 1: an added NAMED entry (the verifier's exact attack).
    grown = dict(real_named)
    grown["conformance/bash/test_nounset_operators_conformance.py"] = "bogus"
    monkeypatch.setattr(mod, "NAMED_ALLOWLIST", grown)
    monkeypatch.setattr(mod, "PSH_ONLY_REGISTRY", real_registry)
    with pytest.raises(AssertionError, match="membership changed"):
        test_allowlist_membership_is_frozen()

    # Face 2: growth of the psh-only registry half.
    monkeypatch.setattr(mod, "NAMED_ALLOWLIST", real_named)
    monkeypatch.setattr(mod, "PSH_ONLY_REGISTRY",
                        {"unit/builtins/test_let.py": "bogus"})
    with pytest.raises(AssertionError, match="membership changed"):
        test_allowlist_membership_is_frozen()


def test_detector_catches_both_offender_faces():
    """Both faces the ruling asks for: a DIRECT BASH oracle spawn (the HIGH-1
    defect) AND an unregistered PSH-ONLY spawn (approved only via the registry).
    The guard rejects ANY direct spawn, so both faces are caught."""
    bash_face = (
        "from shell_oracle import resolve_bash\n"
        "import subprocess\n"
        "subprocess.run([resolve_bash().path, '-c', 'echo hi'])\n"
    )
    psh_face = (
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'psh', '-c', 'echo hi'])\n"
    )
    assert any(k == "subprocess.run" for _, k in find_direct_spawns(bash_face))
    assert any(k == "subprocess.run" for _, k in find_direct_spawns(psh_face))


def test_detector_ignores_runner_calls():
    snippet = (
        "from shell_oracle import run_bash, run_psh, run_shell_case\n"
        "run_psh(['-c', 'x'])\n"
        "run_bash(['-c', 'x'])\n"
        "run_shell_case(['sh', '-c', 'x'])\n"
    )
    assert find_direct_spawns(snippet) == []


def test_detector_ignores_non_spawn_attrs():
    """subprocess.PIPE / subprocess.DEVNULL / os.path.join are not spawns."""
    snippet = (
        "import subprocess, os\n"
        "x = subprocess.PIPE\n"
        "y = subprocess.DEVNULL\n"
        "z = os.path.join('a', 'b')\n"
        "w = os.environ.get('X')\n"
    )
    assert find_direct_spawns(snippet) == []


def test_scope_covers_migrated_and_harness_modules():
    """The scan really reaches a migrated conformance module, a shell_oracle
    importer outside conformance, and the harness itself."""
    scanned = {rel for rel, _, _ in iter_oracle_bearing_modules()}
    for probe in (
            "conformance/bash/test_nounset_operators_conformance.py",
            "harness/shell_oracle.py",
            "integration/redirection/test_here_string_tilde.py",
    ):
        assert probe in scanned, f"guard scope lost {probe}"
