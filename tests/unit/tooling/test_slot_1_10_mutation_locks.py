"""Mutation locks for slot 1.10's two owners (C040, C041).

Each arm re-introduces ONE specific way the closed defect could come back and
asserts the pins fail FOR THAT ARM'S OWN REASON, with a discrimination row that
must stay green so an arm that breaks everything is itself a failure. The
driver never skips: an arm whose anchor has moved, or whose pin nodes no longer
collect, FAILS loudly rather than quietly checking nothing.

Both defects are silent by construction — a command that does not run and a
status that stays 0 both look exactly like success — which is what these arms
exist for.
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
    f"slot 1.10 locks mislocated the repo root: {REPO!r} has no psh/ directory")

CORE = "psh/executor/core.py"
NULL = "psh/executor/null_command.py"
ENVIRONMENT = "psh/builtins/environment.py"

NOEXEC_PINS = "tests/conformance/bash/test_noexec_per_statement_conformance.py"
NULL_PINS = "tests/conformance/bash/test_null_command_status_conformance.py"
NOEXEC_UNIT = "tests/unit/executor/test_noexec_gate.py"

NOEXEC_SAME_LINE = (f"{NOEXEC_PINS}::test_noexec_stops_the_rest_of_the_input"
                    "[same_line-dash_c]")
NOEXEC_SCRIPT = (f"{NOEXEC_PINS}::test_noexec_stops_the_rest_of_the_input"
                 "[same_line-script]")
NOEXEC_INTERACTIVE = (f"{NOEXEC_UNIT}::TestInteractiveRefusal::"
                      "test_interactive_shell_refuses_it")
NULL_BARE = f"{NULL_PINS}::test_null_command_status[bare-dash_c]"
NULL_STDIN = f"{NULL_PINS}::test_null_command_status[stdin_redirect-dash_c]"
NULL_REDIRECT_FILE = (f"{NULL_PINS}::"
                      "test_null_command_performs_its_redirections[dash_c]")


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
        # C040's whole fix: the per-statement gate. Without it, execution
        # falls back to the per-input-unit check, which cannot see a flag
        # flipped by an earlier statement of the same unit.
        "noexec-gate-removed",
        CORE,
        "            if self.state.options.get('noexec', False):",
        "            if False:  # MUTATION: the per-statement gate is gone",
        breaks=[NOEXEC_SAME_LINE],
        # The null-command rule is a different owner entirely.
        stays_green=[NULL_BARE],
    ),
    Arm(
        # A gate that fires only at the ROOT would still pass a `-c` row while
        # leaving every nested statement list (function body, loop body,
        # subshell) unprotected — the shape the per-unit check already had.
        "noexec-gate-narrowed-to-the-program-root",
        CORE,
        "            if self.state.options.get('noexec', False):",
        "            if (self.state.options.get('noexec', False)\n"
        "                    and context is not ROOT_SEQUENCE):",
        breaks=[NOEXEC_SAME_LINE],
        stays_green=[NULL_BARE],
    ),
    Arm(
        # The interactive complement. Dropping the refusal lets `set -n` at a
        # prompt turn the option on, so `$-` grows an `n` and the REPL wedges.
        "interactive-refusal-removed",
        ENVIRONMENT,
        "    if (option == 'noexec' and enable and not from_invocation\n"
        "            and shell.state.options.get('interactive')):\n"
        "        return\n",
        "",
        breaks=[NOEXEC_INTERACTIVE],
        # Non-interactive execution is untouched by the refusal.
        stays_green=[NOEXEC_SAME_LINE],
    ),
    Arm(
        # C041's whole fix: the status propagation. Returning a hard 0 is
        # exactly the pre-slot behaviour.
        "null-command-status-propagation-dropped",
        NULL,
        "    status = state.last_cmdsub_status\n"
        "    return status if status is not None else 0",
        "    return 0  # MUTATION: the substitution status is discarded",
        breaks=[NULL_BARE],
        # The fd-0 clause answers 0 either way, so it must survive.
        stays_green=[NULL_STDIN],
    ),
    Arm(
        # The fd-0 clause is the half that keeps `< f`, `<<EOF` and `<<< z`
        # at 0. Dropping it regresses those rows while the headline row stays
        # green — the exact shape a status-only fix would have shipped.
        "fd0-clause-dropped",
        NULL,
        "    if redirects and null_command_redirects_stdin(redirects):\n"
        "        return 0\n",
        "",
        breaks=[NULL_STDIN],
        stays_green=[NULL_BARE],
    ),
    Arm(
        # The redirections themselves. A null command that reports the right
        # status but never performs its redirections passes every status row
        # and still fails to create the file — which is why a status-only pin
        # is not enough (D3).
        "null-command-skips-its-redirections",
        "psh/executor/command.py",
        "            if node.redirects:\n"
        "                # A setup failure (`> \"\"`, `> adir`, `< missing`) "
        "prints the\n"
        "                # one diagnostic shape and fails with 1, like bash.\n"
        "                with self.io_manager.guarded_redirections("
        "node.redirects) as ok:\n"
        "                    if not ok:\n"
        "                        return 1\n",
        "            pass  # MUTATION: the redirections are not performed\n",
        breaks=[NULL_REDIRECT_FILE],
        stays_green=[NOEXEC_SAME_LINE],
    ),
]


def _mutation_env(tree):
    env = dict(os.environ)
    env["PYTHONPATH"] = tree
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_nodes(tree, nodes):
    return subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "-p", "no:randomly",
         "-p", "no:cacheprovider"],
        cwd=tree, capture_output=True, text=True, errors="replace",
        timeout=600, env=_mutation_env(tree))


@pytest.fixture(scope="module")
def mutation_tree():
    """A throwaway copy of the tree the arms mutate.

    The scratch parent is the repo's ``tmp/``, which is GITIGNORED and
    therefore ABSENT on a fresh clone or ``git worktree add``. It is created
    here — a test owns the scratch dirs it needs — and every precondition is
    diagnosed LOUDLY, never skipped: arms that die at setup while an always-on
    anchor check stays green report health precisely because nothing ran.
    """
    scratch_parent = os.path.join(REPO, "tmp")
    try:
        os.makedirs(scratch_parent, exist_ok=True)
    except OSError as exc:
        pytest.fail(
            f"slot 1.10 locks CANNOT RUN: scratch parent {scratch_parent!r} is "
            f"absent and could not be created ({exc}).")
    root = tempfile.mkdtemp(prefix="slot110-", dir=scratch_parent)
    tree = os.path.join(root, "tree")
    ignore = shutil.ignore_patterns(
        ".git", "tmp", "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "*.egg-info", "htmlcov", ".coverage",
        "node_modules", "build", "dist", ".venv", "venv")
    shutil.copytree(REPO, tree, ignore=ignore, symlinks=True)
    for required in (CORE, NULL, ENVIRONMENT, NOEXEC_PINS, NULL_PINS,
                     NOEXEC_UNIT):
        if not os.path.isfile(os.path.join(tree, required)):
            pytest.fail(
                f"slot 1.10 locks CANNOT RUN: the tree copy at {tree!r} is "
                f"missing {required} — the copy or its ignore-globs are wrong.")
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
            f"slot 1.10 arm {arm.name!r} CANNOT RUN: target {arm.path} does "
            f"not exist in the tree under test. Repair the arm, do not delete "
            f"it.")
    original = open(target, encoding="utf-8").read()

    occurrences = original.count(arm.old)
    if occurrences != 1:
        pytest.fail(
            f"slot 1.10 arm {arm.name!r} CANNOT RUN: its anchor matches "
            f"{occurrences} times in {arm.path} (expected exactly 1). The code "
            f"moved and this lock is no longer mutating what it claims to. "
            f"Anchor:\n{arm.old!r}")

    collect = subprocess.run(
        [sys.executable, "-m", "pytest", *arm.breaks, *arm.stays_green,
         "-q", "--collect-only", "-p", "no:cacheprovider"],
        cwd=mutation_tree, capture_output=True, text=True, errors="replace",
        timeout=300, env=_mutation_env(mutation_tree))
    if collect.returncode != 0:
        pytest.fail(
            f"slot 1.10 arm {arm.name!r} CANNOT RUN: the pin nodes it names do "
            f"not all collect. A renamed or deleted pin silently disarms this "
            f"lock.\n{collect.stdout[-2000:]}")

    try:
        open(target, "w", encoding="utf-8").write(
            original.replace(arm.old, arm.new))

        broke = _run_nodes(mutation_tree, arm.breaks)
        assert broke.returncode != 0, (
            f"slot 1.10 arm {arm.name!r} was NOT CAUGHT: the mutation was "
            f"applied but {arm.breaks} still passed. The pin does not actually "
            f"constrain this behaviour.\n{broke.stdout[-2000:]}")

        held = _run_nodes(mutation_tree, arm.stays_green)
        assert held.returncode == 0, (
            f"slot 1.10 arm {arm.name!r} is INDISCRIMINATE: it also broke "
            f"{arm.stays_green}, which must survive this mutation.\n"
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
        "slot 1.10 arm anchors have ROTTED — repair them, do not delete them:\n"
        "  " + "\n  ".join(stale))
