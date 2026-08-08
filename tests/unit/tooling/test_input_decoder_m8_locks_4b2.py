"""M8 mutation locks for the 4B.2 decoder seam and the ``-N``/``-t`` rider.

A pin proves the code does the right thing TODAY. A mutation lock proves the pin
would NOTICE if it stopped: each arm below re-introduces one specific way the
defect could come back, and asserts that the pins fail — **for that arm's own
reason**, not merely that something somewhere went red.

Each arm names the pin nodes it expects to break and a discrimination row that
must STAY GREEN under the same mutation, so an arm that simply breaks everything
is itself a failure.

**Loud diagnostics.** The driver never skips. If an arm's mutation cannot be
applied — the anchor text it patches has moved, the target module is missing,
the pin nodes it names no longer exist — it FAILS with the arm name and the
reason. A mutation lock that quietly stops mutating is worse than no lock at
all: it reports green forever while checking nothing (D-3.4 lesson 13).
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

READER = "psh/builtins/input_reader.py"
READ_BUILTIN = "psh/builtins/read_builtin.py"
SEAM_PINS = "tests/unit/builtins/test_input_decoder_seam_4b2.py"
RIDER_PINS = "tests/unit/builtins/test_read_exact_timeout_4b2.py"


class Arm:
    """One mutation: a text substitution plus what it must and must not break."""

    def __init__(self, name, path, old, new, breaks, stays_green):
        self.name = name
        self.path = path
        self.old = old
        self.new = new
        self.breaks = breaks              # node ids that MUST fail
        self.stays_green = stays_green    # node ids that MUST still pass

    def __repr__(self):
        return f"<Arm {self.name}>"


ARMS = [
    Arm(
        "seam-empty-finalize-reintroduced",
        READER,
        "            tail = self._decoder.decode(raw, final=True)",
        "            tail = self._decoder.decode(b'', final=True) + "
        "raw.decode('utf-8', errors='surrogateescape')",
        breaks=[
            f"{SEAM_PINS}::TestSplitCharIdentityAcrossSeam::"
            "test_split_character_survives_the_bulk_drain[e_acute-split1]",
        ],
        stays_green=[
            f"{SEAM_PINS}::TestSeamControlsMalformed::"
            "test_malformed_bytes_round_trip_across_the_seam[orphan-continuation]",
        ],
    ),
    Arm(
        "seam-fresh-decoder-reintroduced",
        READER,
        "            tail = self._decoder.decode(raw, final=True)",
        "            tail = raw.decode('utf-8', errors='surrogateescape')",
        breaks=[
            f"{SEAM_PINS}::TestSplitCharIdentityAcrossSeam::"
            "test_split_character_survives_the_bulk_drain[euro-split2]",
        ],
        # This arm DROPS the pending bytes entirely, so every cell that strands
        # decoder state breaks under it — including the non-continuation and
        # no-completion controls. The discrimination row must therefore be a
        # drain with a CLEAN decoder, which this mutation cannot reach.
        stays_green=[
            f"{SEAM_PINS}::TestCursorStateCensus::"
            "test_read_all_merge_order_is_decoded_then_fd",
        ],
    ),
    Arm(
        "seam-merge-order-scrambled",
        READER,
        "        return prefix + tail",
        "        return tail + prefix",
        breaks=[
            f"{SEAM_PINS}::TestCursorStateCensus::"
            "test_read_all_merge_order_is_decoded_then_fd",
        ],
        stays_green=[
            f"{SEAM_PINS}::TestSplitCharIdentityAcrossSeam::"
            "test_split_character_survives_the_bulk_drain[e_acute-split1]",
        ],
    ),
    Arm(
        "seam-decoder-not-cleared",
        READER,
        "            tail = self._decoder.decode(raw, final=True)\n"
        "            self._decoder = None",
        "            tail = self._decoder.decode(raw, final=True)",
        breaks=[
            f"{SEAM_PINS}::TestCursorStateCensus::"
            "test_read_all_leaves_the_decoder_clean",
        ],
        stays_green=[
            f"{SEAM_PINS}::TestSplitCharIdentityAcrossSeam::"
            "test_split_character_survives_the_bulk_drain[smile-split3]",
        ],
    ),
    Arm(
        "rider-deadline-dropped",
        READ_BUILTIN,
        "                result = reader.read_limited(delimiter=None, "
        "max_chars=count,\n                                             "
        "deadline=deadline)",
        "                result = reader.read_limited(delimiter=None, "
        "max_chars=count)",
        breaks=[
            f"{RIDER_PINS}::TestRiderParityFull::"
            "test_no_input_and_no_eof_times_out",
        ],
        stays_green=[
            f"{RIDER_PINS}::TestLowercaseNAndPlainTReference::"
            "test_n_no_input_times_out",
        ],
    ),
    Arm(
        "rider-timeout-status-mismapped",
        READ_BUILTIN,
        "        if status == 'timeout':\n            return 142\n"
        "        return 1 if status == 'eof' else 0",
        "        return 1 if status in ('eof', 'timeout') else 0",
        breaks=[
            f"{RIDER_PINS}::TestRiderParityFull::"
            "test_partial_input_and_no_eof_assigns_the_partial",
        ],
        stays_green=[
            f"{RIDER_PINS}::TestRiderMustHoldControls::"
            "test_count_satisfied_before_the_deadline",
        ],
    ),
]


def _mutation_env(tree: str) -> dict:
    """Environment for a run against the mutated tree.

    ``PYTHONDONTWRITEBYTECODE`` is REQUIRED, not tidiness. Python validates a
    cached ``.pyc`` against the source's mtime **and size**, and several arms
    here are deliberately same-size edits (``prefix + tail`` ->
    ``tail + prefix``). A ``.pyc`` written by an earlier arm in the same second
    then looks valid, the mutated source is never recompiled, and the lock
    reports "mutation NOT CAUGHT" — a false alarm that, for a lock, is
    indistinguishable from a real finding. No bytecode, no stale cache.
    """
    return {**os.environ, "PYTHONPATH": tree, "PYTHONDONTWRITEBYTECODE": "1"}


def _run_nodes(tree: str, nodes) -> subprocess.CompletedProcess:
    # errors="replace": a failing pin prints the raw bytes it compared, which
    # are not valid UTF-8 by construction in this slot — decoding strictly
    # would turn a legible failure into a UnicodeDecodeError in the harness.
    return subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "--no-header"],
        cwd=tree, capture_output=True, text=True, errors="replace",
        timeout=600, env=_mutation_env(tree))


@pytest.fixture(scope="module")
def mutation_tree():
    """A throwaway copy of the tree the arms mutate.

    Copied rather than edited in place so a crashed run can never leave the real
    worktree mutated.

    The scratch parent is the repo's ``tmp/``, which is GITIGNORED and therefore
    ABSENT on a fresh clone or ``git worktree add``. The test creates it — a test
    owns the scratch dirs it needs. Before it did, all six arms died at fixture
    setup with a bare ``FileNotFoundError`` on any fresh checkout while the
    always-on anchor check stayed GREEN: the rot-detector read healthy precisely
    because the arms could not run. The canonical gate masked it
    (``run_tests.py`` creates ``tmp/`` first), so only a bare ``pytest`` on a
    clean tree — which CLAUDE.md documents as supported — exposed it. That is
    why the missing parent is diagnosed as LOUDLY as every other precondition
    here rather than quietly created.
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

    root = tempfile.mkdtemp(prefix="m8-4b2-", dir=scratch_parent)
    tree = os.path.join(root, "tree")
    # Skip the repo's untracked/derived junk: copying it is pure cost, and a
    # stale cache carried into the copy could mask a mutation.
    ignore = shutil.ignore_patterns(
        ".git", "tmp", "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "*.egg-info", "htmlcov", ".coverage",
        "node_modules", "build", "dist", ".venv", "venv")
    shutil.copytree(REPO, tree, ignore=ignore, symlinks=True)
    if not os.path.isfile(os.path.join(tree, READER)):
        pytest.fail(
            f"M8 locks CANNOT RUN: the tree copy at {tree!r} is missing "
            f"{READER} — the copy or its ignore-globs are wrong.")
    try:
        yield tree
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.serial  # the rider arms drive real deadlines
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

    # The nodes an arm names must exist, or the arm proves nothing.
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
    """The registry is checked against the REAL tree, not just the copy.

    This is the cheap always-on half of the guard: if a refactor moves the code
    an arm patches, this fails immediately with the arm's name, rather than the
    arm silently becoming a no-op that nobody notices for months.
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
