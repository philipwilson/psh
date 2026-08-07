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
        "        del self._owed[lo:hi]",
        "        del self.state.history[lo:hi]\n"
        "        del self._owed[lo:hi]\n"
        "        before_read = max(0, min(hi, self._file_read_len) - lo)\n"
        "        self._file_read_len = max(0, self._file_read_len - before_read)",
        breaks=[f"{UNIT}::TestReadCursorPerOp::test_delete_does_not_move_it"],
        stays_green=[
            f"{UNIT}::TestReadCursorPerOp::test_clear_does_not_move_it"],
    ),
    Arm(
        # MEDIUM-7 leg C / LEDGER carry #32
        "clear-resets-the-read-cursor",
        MGR,
        "        self._owed.clear()",
        "        self._owed.clear()\n        self._file_read_len = 0",
        breaks=[f"{UNIT}::TestReadCursorPerOp::test_clear_does_not_move_it"],
        stays_green=[
            f"{UNIT}::TestReadCursorPerOp::test_delete_does_not_move_it"],
    ),
    Arm(
        # MEDIUM-7 leg B: the filters and the cap alike
        "store-skips-the-recording-policy",
        MGR,
        "        if self._ignorespace_blocks(command):\n            return\n"
        "        self._record(command)",
        "        self.state.history.append(command)\n"
        "        self._owed.append(True)",
        breaks=[
            f"{UNIT}::TestReadPathsRespectHistsize::test_store_trims_to_histsize",
            f"{UNIT}::TestStoreUsesTheRecordingPolicy::test_ignoredups_applies",
        ],
        stays_green=[
            f"{UNIT}::TestStoreUsesTheRecordingPolicy::"
            "test_an_embedded_newline_is_NOT_joined"],
    ),
    Arm(
        # THE ROUND-1 BOUNCE REGRESSION ITSELF: detach the owed flag from the
        # entry's POSITION on delete, so the debt slides onto whichever entry
        # survives. That is exactly what text-keyed resolution did: delete the
        # typed copy of a command and the untouched LOADED copy inherited the
        # debt, resurrecting a deleted command into $HISTFILE as a duplicate.
        #
        # (A first version of this arm rewrote _pending_entries to a text
        # multiset but still SOURCED it from the positional flags, so it was
        # NOT CAUGHT — it did not reproduce the defect it was named for. The
        # arm was re-pointed at the mechanism rather than the symptom.)
        "owed-flag-detached-from-entry-position",
        MGR,
        "        del self.state.history[lo:hi]\n"
        "        del self._owed[lo:hi]",
        "        del self.state.history[lo:hi]\n"
        "        del self._owed[:hi - lo]",
        breaks=[
            f"{UNIT}::TestPendingMultisetSemantics::"
            "test_deleting_a_typed_copy_does_not_resurrect_it_via_a_twin",
            f"{UNIT}::TestPendingMultisetSemantics::"
            "test_a_foreign_line_is_not_resurrected_by_a_same_text_delete",
        ],
        stays_green=[
            f"{UNIT}::TestPendingMembership::test_recorded_entries_are_pending"],
    ),
    Arm(
        # The producer half of membership.
        "recording-stops-marking-entries-owed",
        MGR,
        "        self.state.history.append(command)\n"
        "        self._owed.append(True)\n"
        "        self._trim_to_max()",
        "        self.state.history.append(command)\n"
        "        self._owed.append(False)\n"
        "        self._trim_to_max()",
        breaks=[
            f"{UNIT}::TestPendingMembership::test_recorded_entries_are_pending",
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_the_typed_entry_reaches_the_file_after_an_interleaved_read",
        ],
        stays_green=[
            f"{UNIT}::TestPendingMembership::test_loaded_lines_are_not_pending"],
    ),
    Arm(
        # R2-F2's swallow: a read re-marking the whole list as written.
        "read-new-swallows-owed-entries",
        MGR,
        "        self._owed.extend([False] * len(fresh))",
        "        self._owed.extend([False] * len(fresh))\n"
        "        self._mark_written()",
        breaks=[
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_read_new_does_not_swallow_a_pending_typed_entry",
        ],
        stays_green=[
            f"{UNIT}::TestReadsDoNotSwallowPending::"
            "test_read_does_not_swallow_a_pending_typed_entry"],
    ),
    Arm(
        # The leak: foreign lines treated as ours to save.
        "read-marks-foreign-lines-as-owed",
        MGR,
        "        self._owed.extend([False] * len(lines))",
        "        self._owed.extend([True] * len(lines))",
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
        # P5: a named-target write consuming $HISTFILE's owed entries.
        "write-to-any-file-consumes-owed",
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
        # The CV3-strip reconciliation: without it an outside tail delete
        # leaves a phantom debt that a later save resurrects.
        "outside-tail-delete-leaves-a-phantom-debt",
        MGR,
        "        if extra > 0:\n"
        "            del self._owed[len(self.state.history):]",
        "        if False:\n"
        "            del self._owed[len(self.state.history):]",
        breaks=[
            f"{UNIT}::TestPendingIsAViewOfMemory::"
            "test_the_builtin_CV3_strip_removes_from_pending",
        ],
        stays_green=[
            f"{UNIT}::TestPendingMembership::test_recorded_entries_are_pending"],
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
            f"{CONF}::TestSequenceParity::test_clear_then_read",
        ],
    ),
    Arm(
        # Rider #25: the `-c` suppresses `-d` rule.
        "clear-no-longer-suppresses-delete",
        BUILTIN,
        "            hist_mgr.clear_history()\n"
        "        elif 'd' in flags:",
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
    Arm(
        # ROUND-1 BOUNCE-2: the two-of-anrw diagnostic going silent again.
        "anrw-diagnostic-dropped",
        BUILTIN,
        '            self.error("cannot use more than one of -anrw", shell)\n'
        "            return 1",
        "            return 1",
        breaks=[
            f"{CONF}::TestClusteredFlagsRider::"
            "test_two_file_ops_report_the_bash_diagnostic",
        ],
        stays_green=[
            f"{CONF}::TestClusteredFlagsRider::"
            "test_cluster_exit_status_matches_bash[-an-rcan]",
        ],
    ),
    Arm(
        # ROUND-1 BOUNCE-3: the file op running after a clear/delete again.
        "file-op-not-suppressed-after-clear-or-delete",
        BUILTIN,
        "        if file_ops and not ('d' in flags\n"
        "                             or ('c' in flags and not operands)):",
        "        if file_ops:",
        breaks=[
            f"{CONF}::TestClusterActionSelection::"
            "test_clear_without_operand_suppresses_the_file_op",
            f"{CONF}::TestClusterActionSelection::"
            "test_delete_suppresses_the_file_op",
        ],
        stays_green=[
            f"{CONF}::TestClusterActionSelection::"
            "test_clear_with_an_operand_still_runs_the_file_op",
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
    GITIGNORED and therefore ABSENT on a fresh clone or ``git worktree add``, so
    this fixture CREATES it (``exist_ok=True``) and fails LOUDLY if it cannot —
    arms that die at fixture setup while the anchor check stays green are exactly
    the silent-disarm failure this file exists to prevent. (An earlier docstring
    here claimed the parent was diagnosed rather than created, which was the
    opposite of the code beside it.)
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
