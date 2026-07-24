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
differential-comparison bypass.

**What is rejected:** ``subprocess.run/Popen/call/check_output/check_call`` and
``os.system``/``os.popen`` — detected by attribute access on a ``subprocess``
or ``os`` name.

**Honest limits (documented, not defects):** the guard matches the STATIC,
attribute-access form. It does NOT catch a bare-name import
(``from subprocess import run; run(...)``), ``getattr(subprocess, 'run')(...)``,
a spawn assembled/`eval`-ed from strings, or one hidden behind a helper in a
module outside the scanned set. A tree audit at adoption found zero bare-name
subprocess spawns in the scope, so the attribute form is the whole live
surface; if a bare-name form appears, extend ``find_direct_spawns`` rather than
allowlisting it.

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

import pytest

TESTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# subprocess.<attr>(...) spawn methods and os.<attr>(...) shell launchers.
_SUBPROCESS_SPAWNS = frozenset({"run", "Popen", "call", "check_output",
                                "check_call"})
_OS_SPAWNS = frozenset({"system", "popen"})

# The one directory the scan skips: it holds the SYNTHETIC OFFENDER fixture,
# which is a deliberate spawn used to prove the guard fires.
_FIXTURE_DIR = "oracle_spawn_fixtures"

# The allowlist has TWO parts (integrator ruling, slot 1.2). The census finding
# it rests on: the bearing set is 95/95 differential MODULES (36 conformance +
# 59 shell_oracle importers, every one comparing against bash) — there are NO
# psh-only-only spawner modules in scope (the ~70 CLAUDE.md exec/fd/lifecycle
# psh-only modules do not import shell_oracle and are not under conformance, so
# they are OUTSIDE this guard entirely). So (b) holds only the single psh-only
# RESIDUAL spawn-site left after migration.

# (a) NAMED allowlist: the harness itself + spawns that genuinely CANNOT go
# through the run-to-completion runner. owner + reason + removal condition each.
NAMED_ALLOWLIST = {
    "harness/shell_oracle.py":
        "owner=slot1.1. It IS the runner — owns the single real "
        "subprocess.Popen (and the _bash_version probe). Removal: never.",
    "integration/job_control/test_exit_trap_paths.py":
        "owner=slot1.2. DIFFERENTIAL mid-run-signal harness: delivers a signal "
        "to a running psh AND to a running bash (_spawn_and_signal at :228 for "
        "psh, :284 for [BASH,...]) to COMPARE the EXIT trap on a fatal signal; "
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
    "system/test_stdin_script_lazy_read.py":
        "owner=slot1.2. Pins the PIPE (non-seekable) vs seekable-file stdin "
        "distinction; the runner always feeds stdin from a seekable regular "
        "file, which would collapse the very distinction under test. Removal: "
        "the runner gains a non-seekable/pipe stdin mode.",
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


def _imports_shell_oracle(tree):
    """True iff *tree* really imports shell_oracle (not just mentions it)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module \
                and "shell_oracle" in node.module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "shell_oracle" in alias.name:
                    return True
    return False


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

    Skips the fixtures dir (the synthetic offender lives there by design).
    """
    for dirpath, dirnames, filenames in os.walk(TESTS_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in ("__pycache__", _FIXTURE_DIR)]
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


def test_fixture_dir_is_excluded_from_the_scan():
    """The offender fixture must NOT appear in the scanned set (else it would
    fail the real guard)."""
    scanned = {rel for rel, _, _ in iter_oracle_bearing_modules()}
    assert not any(_FIXTURE_DIR in rel for rel in scanned)


def test_fixture_dir_holds_only_the_known_offender():
    """Close the hole: the skipped dir may hold ONLY the offender fixture, so
    nothing else can hide a real spawn there."""
    fixture_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               _FIXTURE_DIR)
    py = sorted(f for f in os.listdir(fixture_dir) if f.endswith(".py"))
    assert py == ["offender_module.py"], (
        f"the guard skips {_FIXTURE_DIR}/; it may hold ONLY offender_module.py, "
        f"found {py}")


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
