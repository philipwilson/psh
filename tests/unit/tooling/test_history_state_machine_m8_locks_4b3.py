"""M8 mutation locks for the 4B.3 history state machine and the #25 rider.

A pin proves the code does the right thing TODAY. A mutation lock proves the pin
would NOTICE if it stopped: each arm re-introduces one specific way the defect
could come back, and asserts that the pins fail **for that arm's own reason** —
with a discrimination row that must STAY GREEN under the same mutation, so an
arm that simply breaks everything is itself a failure.

The arms cover the three chartered legs, the two data-integrity faces found
alongside them, the representation itself (pending as a VIEW of memory — the
property that makes "gone from memory means gone from pending" structural), and
the rider's cluster parsing.

**Loud diagnostics.** The driver never skips. If an arm's mutation cannot be
applied — the anchor moved, the module is missing, the pin nodes it names no
longer exist — it FAILS with the arm name and the reason. A mutation lock that
quietly stops mutating reports green forever while checking nothing (D-3.4
lesson 13).
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

MGR = "psh/interactive/history_manager.py"
BUILTIN = "psh/builtins/shell_state.py"
UNIT = "tests/unit/interactive/test_history_state_machine_4b3.py"
CONF = "tests/conformance/bash/test_history_state_machine_conformance.py"


class Arm:
    """One mutation: a text substitution plus what it must and must not break."""

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
        # MEDIUM-7 leg A
        "delete-rewinds-the-read-cursor",
        MGR,
        "        del self.state.history[lo:hi]\n"
        "        self._prune_pending()",
        "        del self.state.history[lo:hi]\n"
        "        before_read = max(0, min(hi, self._file_read_len) - lo)\n"
        "        self._file_read_len = max(0, self._file_read_len - "
        "before_read)\n"
        "        self._prune_pending()",
        breaks=[f"{UNIT}::TestReadCursorPerOp::test_delete_does_not_move_it"],
        stays_green=[
            f"{UNIT}::TestReadCursorPerOp::test_clear_does_not_move_it"],
    ),
    Arm(
        # MEDIUM-7 leg C / LEDGER carry #32
        "clear-resets-the-read-cursor",
        MGR,
        "        # Nothing is left in memory, so nothing is pending (invariant: "
        "pending\n        # is a view of memory). A cleared entry is not "
        "resurrected on save.\n        self._pending = []",
        "        self._pending = []\n        self._file_read_len = 0",
        breaks=[f"{UNIT}::TestReadCursorPerOp::test_clear_does_not_move_it"],
        stays_green=[
            f"{UNIT}::TestReadCursorPerOp::test_delete_does_not_move_it"],
    ),
    Arm(
        # MEDIUM-7 leg B, cap half
        "store-skips-the-recording-policy",
        MGR,
        "        if self._ignorespace_blocks(command):\n            return\n"
        "        self._record(command)",
        "        self.state.history.append(command)",
        breaks=[
            f"{UNIT}::TestReadPathsRespectHistsize::test_store_trims_to_histsize",
            f"{UNIT}::TestStoreUsesTheRecordingPolicy::test_ignoredups_applies",
        ],
        stays_green=[
            f"{UNIT}::TestStoreUsesTheRecordingPolicy::"
            "test_an_embedded_newline_is_NOT_joined"],
    ),
    Arm(
        # The PRODUCER half of membership: if recording stops adding to pending,
        # nothing is ever owed and nothing is ever saved. A different kill
        # reason from the store arm above, which removes the POLICY.
        #
        # (An earlier arm here removed `_prune_pending()` from the trim, on the
        # assumption that the front-drop's eager maintenance was load-bearing.
        # It was NOT CAUGHT — and correctly so: `_pending_entries` resolves
        # against memory, so the eager prune is hygiene, not correctness. The
        # arm was replaced rather than weakened, and the docstring that implied
        # otherwise was corrected. The view is what carries the invariant, and
        # the "pending-stops-being-a-view" arm below is what locks it.)
        "recording-stops-marking-entries-pending",
        MGR,
        "        self.state.history.append(command)\n"
        "        self._pending.append(command)",
        "        self.state.history.append(command)",
        breaks=[
            f"{UNIT}::TestPendingMembership::test_recorded_entries_are_pending",
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_the_typed_entry_reaches_the_file_after_an_interleaved_read",
        ],
        stays_green=[
            f"{UNIT}::TestPendingMembership::test_loaded_lines_are_not_pending"],
    ),
    Arm(
        # The read paths re-marking everything as written: R2-F2's swallow.
        "read-new-swallows-pending-entries",
        MGR,
        "        # Read lines are NEVER pending (see read_history), and the "
        "in-memory\n        # list still respects $HISTSIZE: bash trims after "
        "`-n` too.\n        self._trim_to_max()",
        "        self._trim_to_max()\n        self._mark_written()",
        breaks=[
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_read_new_does_not_swallow_a_pending_typed_entry",
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_the_typed_entry_reaches_the_file_after_an_interleaved_read",
        ],
        stays_green=[
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_read_does_not_swallow_a_pending_typed_entry"],
    ),
    Arm(
        # The leak: lines read from another file treated as ours to save.
        "read-marks-foreign-lines-as-pending",
        MGR,
        "        self.state.history.extend(lines)\n"
        "        # Read lines are NEVER pending",
        "        self.state.history.extend(lines)\n"
        "        self._pending.extend(lines)\n"
        "        # Read lines are NEVER pending",
        breaks=[
            f"{UNIT}::TestPendingMembership::"
            "test_lines_read_from_a_NAMED_file_are_not_pending",
            f"{CONF}::TestDeclaredDeviations::"
            "test_read_named_then_append_bash_keeps_psh_keeps_too",
        ],
        stays_green=[
            f"{UNIT}::TestPendingMembership::test_read_new_lines_are_not_pending"],
    ),
    Arm(
        # P5: the named-target write consuming $HISTFILE's pending entries.
        "write-to-any-file-consumes-pending",
        MGR,
        "        if self._is_default_file(target):\n"
        "            self._mark_written()\n"
        "            self._file_read_len = len(self.state.history)",
        "        self._mark_written()\n"
        "        if self._is_default_file(target):\n"
        "            self._file_read_len = len(self.state.history)",
        breaks=[
            f"{UNIT}::TestWritesConsumePending::"
            "test_write_to_a_NAMED_file_does_NOT_consume_pending",
            f"{CONF}::TestDeclaredDeviations::"
            "test_write_to_a_named_file_still_saves_the_session",
        ],
        stays_green=[
            f"{UNIT}::TestWritesConsumePending::"
            "test_write_to_the_default_file_consumes_pending"],
    ),
    Arm(
        # The REPRESENTATION: pending as a raw list rather than a view of
        # memory. Everything still "works" until an entry leaves memory by a
        # route the manager does not own -- e.g. the builtin's CV3 strip.
        "pending-stops-being-a-view-of-memory",
        MGR,
        "        wanted = Counter(self._pending)\n"
        "        out: List[str] = []\n"
        "        for entry in self.state.history:\n"
        "            if wanted[entry] > 0:\n"
        "                wanted[entry] -= 1\n"
        "                out.append(entry)\n"
        "        return out",
        "        return list(self._pending)",
        breaks=[
            f"{UNIT}::TestPendingIsAViewOfMemory::"
            "test_the_builtin_CV3_strip_removes_from_pending",
        ],
        stays_green=[
            # Membership still works without the view; only the "left memory
            # means left pending" property dies, which is the arm's own reason.
            f"{UNIT}::TestPendingMembership::test_recorded_entries_are_pending",
        ],
    ),
    Arm(
        # Rider #25: clustered flags rejected again.
        "cluster-parsing-reverted",
        BUILTIN,
        "            letters = word[1:]\n"
        "            for j, letter in enumerate(letters):",
        "            letters = word[1:2] if len(word) > 2 else word[1:]\n"
        "            for j, letter in enumerate(letters):",
        breaks=[
            f"{CONF}::TestClusteredFlagsRider::test_ps_stores_and_does_not_print",
        ],
        stays_green=[
            # Single-flag spellings must be untouched by a cluster regression.
            f"{CONF}::TestSequenceParity::test_clear_then_read",
        ],
    ),
    Arm(
        # Rider #25: the `-c` suppresses `-d` rule.
        "clear-no-longer-suppresses-delete",
        BUILTIN,
        "        if 'c' in flags:\n"
        "            # Route through the manager so the file-sync marker resets "
        "too —\n            # clearing state.history directly left it stale and "
        "dropped\n            # post-clear commands from HISTFILE on save (data "
        "loss).\n            hist_mgr.clear_history()\n"
        "        elif 'd' in flags:",
        "        if 'c' in flags:\n"
        "            hist_mgr.clear_history()\n"
        "        if 'd' in flags:",
        breaks=[
            f"{CONF}::TestClusteredFlagsRider::test_clear_suppresses_delete",
        ],
        stays_green=[
            f"{CONF}::TestClusteredFlagsRider::"
            "test_cluster_exit_status_matches_bash[-ps hello-rcps]",
        ],
    ),
]


def _mutation_env(tree: str) -> dict:
    """Environment for a run against the mutated tree.

    ``PYTHONDONTWRITEBYTECODE`` is REQUIRED, not tidiness: Python validates a
    cached ``.pyc`` against the source's mtime and SIZE, and several arms here
    are near-same-size edits. A stale ``.pyc`` would leave the mutated source
    uncompiled and the lock would report "mutation NOT CAUGHT" — a false alarm
    indistinguishable from a real finding.
    """
    return {**os.environ, "PYTHONPATH": tree, "PYTHONDONTWRITEBYTECODE": "1"}


def _run_nodes(tree: str, nodes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "--no-header"],
        cwd=tree, capture_output=True, text=True, errors="replace",
        timeout=900, env=_mutation_env(tree))


@pytest.fixture(scope="module")
def mutation_tree():
    """A throwaway copy of the tree the arms mutate.

    Copied rather than edited in place so a crashed run can never leave the real
    worktree mutated. The scratch parent is the repo's ``tmp/``, which is
    GITIGNORED and therefore ABSENT on a fresh clone or ``git worktree add`` —
    diagnosed as loudly as every other precondition rather than quietly created,
    because arms that die at fixture setup while the anchor check stays green
    are exactly the silent-disarm failure this file exists to prevent.
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

    root = tempfile.mkdtemp(prefix="m8-4b3-", dir=scratch_parent)
    tree = os.path.join(root, "tree")
    ignore = shutil.ignore_patterns(
        ".git", "tmp", "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "*.egg-info", "htmlcov", ".coverage",
        "node_modules", "build", "dist", ".venv", "venv")
    shutil.copytree(REPO, tree, ignore=ignore, symlinks=True)
    for required in (MGR, BUILTIN, UNIT, CONF):
        if not os.path.isfile(os.path.join(tree, required)):
            pytest.fail(
                f"M8 locks CANNOT RUN: the tree copy at {tree!r} is missing "
                f"{required} — the copy or its ignore-globs are wrong.")
    try:
        yield tree
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.serial          # the conformance arms spawn real bash+psh pairs
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
            f"this behaviour.\n{broke.stdout[-3000:]}")

        held = _run_nodes(mutation_tree, arm.stays_green)
        assert held.returncode == 0, (
            f"M8 arm {arm.name!r} is INDISCRIMINATE: it also broke "
            f"{arm.stays_green}, which must survive this mutation. An arm that "
            f"breaks everything proves nothing about its own reason.\n"
            f"{held.stdout[-3000:]}")
    finally:
        open(target, "w", encoding="utf-8").write(original)


def test_every_arm_anchor_is_present_in_the_real_tree():
    """The registry is checked against the REAL tree, not just the copy.

    The cheap always-on half: if a refactor moves the code an arm patches, this
    fails immediately with the arm's name, rather than the arm silently becoming
    a no-op nobody notices for months.
    """
    stale = []
    for arm in ARMS:
        path = os.path.join(REPO, arm.path)
        if not os.path.exists(path):
            stale.append(f"{arm.name}: missing file {arm.path}")
            continue
        count = open(path, encoding="utf-8").read().count(arm.old)
        if count != 1:
            stale.append(
                f"{arm.name}: anchor matches {count}x in {arm.path} (want 1)")
    assert not stale, (
        "M8 arms have rotted against the live tree — repair the anchors:\n  "
        + "\n  ".join(stale))
