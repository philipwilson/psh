"""M8 mutation locks for the 4B.4 InputCursor contract close.

Same contract as the 4B.2 seam locks (see
``test_input_decoder_m8_locks_4b2.py`` for the full rationale): each arm
re-introduces one specific way the closed defect could come back and asserts
the pins fail FOR THAT ARM'S OWN REASON, with a discrimination row that must
stay green so an arm that breaks everything is itself a failure. The driver
never skips: a mutation whose anchor has moved, or whose pin nodes no longer
collect, FAILS loudly rather than quietly checking nothing.

Slot 4B.4 added FIVE hooks and one registry rule, and every one of them can
fail SILENTLY — a hook that never fires produces exactly the same test output
as a hook that fires and does nothing (the lesson that cost this slot an
invalid measurement during Phase A). That is what these arms exist for.

This file also carries the P1 reintroduction ratchet: the ``_pushback``
bytearray removed in 4B.4 was provably always empty, and a future change that
brings it back must trip here rather than accumulate a second dead buffer.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

# tests/unit/tooling/<this file> -> four levels up is the repo root.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
assert os.path.isdir(os.path.join(REPO, "psh")), (
    f"M8 locks mislocated the repo root: {REPO!r} has no psh/ directory")

REGISTRY = "psh/io_redirect/input_cursor.py"
MANAGER = "psh/io_redirect/manager.py"
COMMAND = "psh/executor/command.py"
FILE_REDIRECT = "psh/io_redirect/file_redirect.py"
READER = "psh/builtins/input_reader.py"

PINS = "tests/integration/redirection/test_input_cursor_contract_4b4.py"
UNIT = "tests/unit/io_redirect/test_input_cursor_registry_4b4.py"

DUP_EXEC = f"{PINS}::TestDupAliasesTheDescription::test_dup_spelling_shares_the_surplus[exec-permanent]"
DUP_NAMED = f"{PINS}::TestDupAliasesTheDescription::test_dup_spelling_shares_the_surplus[named-fd]"
DUP_PERCMD = f"{PINS}::TestDupAliasesTheDescription::test_dup_spelling_shares_the_surplus[per-command]"
FRAME_FWD = f"{PINS}::TestTempFrameScopesTheCursor::test_surplus_does_not_leak_into_the_frame[builtin-redirect]"
FRAME_REV = f"{PINS}::TestTempFrameScopesTheCursor::test_frame_surplus_does_not_escape_into_stdin[builtin-redirect]"
SAME_FD = f"{PINS}::TestMustHold::test_same_fd_persistence"


class Arm:
    def __init__(self, name, path, old, new, breaks, stays_green):
        self.name = name
        self.path = path
        self.old = old
        self.new = new
        self.breaks = breaks
        self.stays_green = stays_green

    def __repr__(self):
        return f"<Arm {self.name}>"


ARMS = [
    Arm(
        # The 2-line registry rule. This is the arm that matters most: without
        # it the dup hooks all still RUN and still record the alias, and the
        # very next read throws it away. Every dup site regresses at once while
        # the hooks look perfectly healthy.
        "cursor-for-fd-overwrites-the-description",
        REGISTRY,
        "        if desc is None:\n"
        "            desc = OpenDescription(f\"fd{fd}\")\n"
        "            self._fd_to_desc[fd] = desc",
        "        desc = OpenDescription(f\"fd{fd}\")\n"
        "        self._fd_to_desc[fd] = desc",
        breaks=[DUP_EXEC],
        # Frame scoping does not depend on the reuse rule.
        stays_green=[FRAME_FWD],
    ),
    Arm(
        # `exec 3<&0` back to dropping the cursor instead of aliasing it.
        "exec-dup-reverted-to-rebind",
        COMMAND,
        "            alias = dup_alias_fds(redirect)\n"
        "            if alias is not None:\n"
        "                registry.bind_dup(*alias)\n"
        "            else:\n"
        "                registry.rebind(fd)",
        "            registry.rebind(fd)",
        breaks=[DUP_EXEC],
        # The per-command dup goes through the manager, not this path.
        stays_green=[DUP_PERCMD],
    ),
    Arm(
        "named-fd-dup-not-aliased",
        FILE_REDIRECT,
        "            self.shell.state.input_cursors.bind_dup(newfd, dup_fd)\n",
        "",
        breaks=[DUP_NAMED],
        stays_green=[DUP_EXEC],
    ),
    Arm(
        "builtin-frame-scoping-removed",
        MANAGER,
        "        frame.saved_input_cursors = self.state.input_cursors.push_frame(\n"
        "            self.cursor_scope_fds(command.redirects))",
        "        frame.saved_input_cursors = {}",
        breaks=[FRAME_FWD],
        # Aliasing is independent of frame scoping.
        stays_green=[DUP_EXEC],
    ),
    Arm(
        # Closing the leak by DESTROYING the outer cursor instead of setting it
        # aside would pass a naive "the frame read is clean" assertion. The pins
        # assert the surplus survives the frame, so this arm is caught.
        "pop-frame-discards-instead-of-restoring",
        REGISTRY,
        "            if desc is not None:\n"
        "                self._fd_to_desc[fd] = desc",
        "            pass",
        breaks=[FRAME_FWD],
        stays_green=[SAME_FD],
    ),
]


def _mutation_env(tree):
    env = dict(os.environ)
    env["PYTHONPATH"] = tree
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_nodes(tree, nodes):
    return subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "-p", "no:randomly"],
        cwd=tree, capture_output=True, text=True, errors="replace",
        timeout=600, env=_mutation_env(tree))


@pytest.fixture(scope="module")
def mutation_tree():
    """A throwaway copy of the tree the arms mutate.

    The scratch parent is the repo's ``tmp/``, which is GITIGNORED and therefore
    ABSENT on a fresh clone or ``git worktree add``. It is created here — a test
    owns the scratch dirs it needs — and every precondition is diagnosed LOUDLY,
    never skipped (4B.2's BL-1: arms that die at setup while an always-on anchor
    check stays green report health precisely because nothing ran).
    """
    scratch_parent = os.path.join(REPO, "tmp")
    try:
        os.makedirs(scratch_parent, exist_ok=True)
    except OSError as exc:
        pytest.fail(
            f"M8 locks CANNOT RUN: scratch parent {scratch_parent!r} is absent "
            f"and could not be created ({exc}). Every arm would die at setup "
            f"while the anchor check stayed green — fix the scratch parent, "
            f"never skip the arms.")
    if not os.path.isdir(scratch_parent):
        pytest.fail(
            f"M8 locks CANNOT RUN: {scratch_parent!r} exists but is not a "
            f"directory.")

    root = tempfile.mkdtemp(prefix="m8-4b4-", dir=scratch_parent)
    tree = os.path.join(root, "tree")
    ignore = shutil.ignore_patterns(
        ".git", "tmp", "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "*.egg-info", "htmlcov", ".coverage",
        "node_modules", "build", "dist", ".venv", "venv")
    shutil.copytree(REPO, tree, ignore=ignore, symlinks=True)
    for required in (REGISTRY, MANAGER, COMMAND, FILE_REDIRECT, PINS):
        if not os.path.isfile(os.path.join(tree, required)):
            pytest.fail(
                f"M8 locks CANNOT RUN: the tree copy at {tree!r} is missing "
                f"{required} — the copy or its ignore-globs are wrong.")
    try:
        yield tree
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.serial
@pytest.mark.parametrize("arm", ARMS, ids=[a.name for a in ARMS])
def test_mutation_is_caught_for_its_own_reason(arm, mutation_tree):
    target = os.path.join(mutation_tree, arm.path)
    if not os.path.exists(target):
        pytest.fail(
            f"M8 arm {arm.name!r} CANNOT RUN: target {arm.path} does not exist "
            f"in the tree under test. The arm has rotted — repair it, do not "
            f"delete it.")
    original = open(target, encoding="utf-8").read()

    occurrences = original.count(arm.old)
    if occurrences != 1:
        pytest.fail(
            f"M8 arm {arm.name!r} CANNOT RUN: its anchor matches "
            f"{occurrences} times in {arm.path} (expected exactly 1). The code "
            f"moved and this lock is no longer mutating what it claims to. "
            f"Anchor:\n{arm.old!r}")

    collect = subprocess.run(
        [sys.executable, "-m", "pytest", *arm.breaks, *arm.stays_green,
         "-q", "--collect-only"],
        cwd=mutation_tree, capture_output=True, text=True, errors="replace",
        timeout=300, env=_mutation_env(mutation_tree))
    if collect.returncode != 0:
        pytest.fail(
            f"M8 arm {arm.name!r} CANNOT RUN: the pin nodes it names do not all "
            f"collect. A renamed or deleted pin silently disarms this lock.\n"
            f"{collect.stdout[-2000:]}")

    try:
        open(target, "w", encoding="utf-8").write(
            original.replace(arm.old, arm.new))

        broke = _run_nodes(mutation_tree, arm.breaks)
        assert broke.returncode != 0, (
            f"M8 arm {arm.name!r} was NOT CAUGHT: the mutation was applied but "
            f"{arm.breaks} still passed. The pin does not actually constrain "
            f"this behaviour.\n{broke.stdout[-2000:]}")

        held = _run_nodes(mutation_tree, arm.stays_green)
        assert held.returncode == 0, (
            f"M8 arm {arm.name!r} is INDISCRIMINATE: it also broke "
            f"{arm.stays_green}, which must survive this mutation. An arm that "
            f"breaks everything proves nothing about its own reason.\n"
            f"{held.stdout[-2000:]}")
    finally:
        open(target, "w", encoding="utf-8").write(original)


def test_every_arm_anchor_is_present_in_the_real_tree():
    """The cheap always-on half: a refactor that moves the code an arm patches
    fails HERE, immediately and by name, instead of silently disarming it."""
    stale = []
    for arm in ARMS:
        path = os.path.join(REPO, arm.path)
        if not os.path.isfile(path):
            stale.append(f"{arm.name}: {arm.path} is missing")
            continue
        count = open(path, encoding="utf-8").read().count(arm.old)
        if count != 1:
            stale.append(f"{arm.name}: anchor matches {count}x in {arm.path}")
    assert not stale, (
        "M8 arm anchors have ROTTED — repair them, do not delete them:\n  "
        + "\n  ".join(stale))


def test_pushback_buffer_is_not_reintroduced():
    """P1 ratchet: the removed raw-byte pushback must not come back.

    ``InputCursor._pushback`` was a bytearray that could never be non-empty —
    its only non-empty writer re-pushed the remainder of what it had just
    drained, seeded from an empty buffer — so it carried a dead branch and a
    misleading "the byte path holds raw bytes here" story for every later
    reader. Slot 4B.4 removed it.

    The byte-record path never over-reads (one byte at a time, stopping AT the
    delimiter), so there is nothing for a pushback buffer to hold. If a change
    genuinely needs one, this ratchet is the place to argue for it — RENAME the
    concept and state why the bytes exist, never just re-add the name and
    silence this.
    """
    source = open(os.path.join(REPO, READER), encoding="utf-8").read()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#"))
    assert "_pushback" not in code, (
        "InputCursor._pushback is back. It was removed in slot 4B.4 as "
        "provably-always-empty dead state. If a raw-byte pushback is now "
        "genuinely needed, give it a name that says what the bytes are and "
        "why they cannot be consumed yet, and pin the path that populates it.")
