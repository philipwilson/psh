"""C031: a RedirectOp is planned exactly once.

Planning a redirect is not a pure lookup — ``RedirectPlanner.plan`` expands the
target word (running its command substitutions) and creates its process
substitution (forking). So "how many times was this operation planned" is a
BEHAVIORAL question, and the answer must always be one. It was two for an
in-process builtin with a redirect on fd >= 3: ``setup_builtin_redirections``
resolved the operation, discarded the plan, and let the fd-level fallback
rebuild a program and resolve it again.

This module counts ``RedirectPlanner.plan`` calls per AST ``Redirect`` across
every application path, and backs the count with the two side effects a second
resolution would produce anyway: a command substitution in the target running
twice, and a process substitution forking twice.

Reproducing the defect this guards (bash 5.3.15 prints 1, psh printed 2)::

    echo hi 3> "$(echo x >> ctr; echo o3)"; wc -l < ctr

Owner: ``RedirectPlan`` (psh/io_redirect/planner.py) — every builtin redirect
helper takes the resolved plan, so no path can request a second resolution.
"""
import os
from collections import Counter
from contextlib import contextmanager

import pytest

from psh.io_redirect.planner import RedirectPlanner

# SERIAL, module-wide: these rows apply fd >= 3 redirects IN-PROCESS, which is
# the only way to count ``RedirectPlanner.plan`` calls (the differential rows
# run psh in a subprocess and cannot see them).  Under xdist, fd 3 in a worker
# is the execnet channel; psh's per-command save/restore dup2s over it, which
# ends the worker's receiver thread on macOS and the session dies SILENTLY --
# nodes are never reported rather than failing (this module alone ran 6-9 of 38
# under ``-n 4``, and ``tests/unit/io_redirect`` dropped 202 -> 133).  A
# psh-free ``os.dup2`` on fd 3 in a worker reproduces it; fd 4 does not.  Root
# CLAUDE.md, "Parallel runs and the serial marker": a test that rewires the
# runner's own fds must not run alongside siblings.
pytestmark = pytest.mark.serial


@contextmanager
def recorded_plans():
    """Record the ``Redirect`` handed to every ``RedirectPlanner.plan`` call.

    Class-level so it sees every planner instance, restored unconditionally.
    """
    calls = []
    original = RedirectPlanner.plan

    def counting(self, redirect):
        calls.append(redirect)
        return original(self, redirect)

    RedirectPlanner.plan = counting
    try:
        yield calls
    finally:
        RedirectPlanner.plan = original


def _describe(redirect):
    return (f"{redirect.fd if redirect.fd is not None else ''}"
            f"{redirect.type}{redirect.target or ''}")


def assert_planned_once(calls, expected_ops):
    """Every recorded redirect was planned exactly once, and *expected_ops*
    distinct operations were planned in all."""
    counts = Counter(id(r) for r in calls)
    repeated = sorted({_describe(r) for r in calls if counts[id(r)] > 1})
    assert not repeated, f"planned more than once: {repeated}"
    assert len(counts) == expected_ops, (
        f"expected {expected_ops} planned operation(s), got {len(counts)}: "
        f"{[_describe(r) for r in calls]}")


def run_counting(shell, command, expected_ops):
    """Run *command* and assert its redirects were each planned exactly once."""
    with recorded_plans() as calls:
        status = shell.run_command(command)
    assert_planned_once(calls, expected_ops)
    return status


# ---- the builtin fd >= 3 path (the C031 defect) ----

@pytest.mark.parametrize("command,expected_ops", [
    ("echo hi 3> out", 1),                 # OPEN_FILE output, fd >= 3
    ("echo hi 3>> out", 1),                # append
    (": 9> out", 1),                       # a builtin that writes nothing
    ("printf hi 4> out", 1),
    ("echo hi 3<> out", 1),                # read-write open
    ("read v 3< src", 1),                  # OPEN_FILE input, fd >= 3
    ("echo hi 3> a 4> b", 2),              # two operations, one plan each
    ("echo hi 3>&1", 1),                   # DUP_FD, fd >= 3
    ("echo hi 3>&1-", 1),                  # MOVE: the split must not re-plan
    ("echo hi 3>&-", 1),                   # CLOSE_FD
    ("read v 3<&-", 1),
    ("read v 3<&0", 1),
])
def test_builtin_fd_level_plans_once(isolated_shell_with_temp_dir,
                                     command, expected_ops):
    shell = isolated_shell_with_temp_dir
    with open("src", "w") as f:
        f.write("line\n")
    run_counting(shell, command, expected_ops)


# ---- the fd 1/2 stream path, unchanged ----

@pytest.mark.parametrize("command,expected_ops", [
    ("echo hi > out", 1),
    ("echo hi >> out", 1),
    ("echo hi 2> err", 1),
    ("echo hi &> both", 1),                # COMBINED
    ("echo hi &>> both", 1),
    ("echo hi 2>&1", 1),
    ("echo hi 1>&2", 1),
    ("echo hi 1>&-", 1),
    ("read v < src", 1),
    ("echo hi > out 2> err", 2),
])
def test_builtin_stream_path_plans_once(isolated_shell_with_temp_dir,
                                        command, expected_ops):
    shell = isolated_shell_with_temp_dir
    with open("src", "w") as f:
        f.write("line\n")
    run_counting(shell, command, expected_ops)


# ---- here-documents and here-strings ----

def test_here_input_plans_once(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    run_counting(shell, "read v 3<<< herestring", 1)
    run_counting(shell, "read v <<< herestring", 1)
    run_counting(shell, "read v 3<<EOF\nbody\nEOF\n", 1)


# ---- named fds are self-contained: they never reach the planner ----

def test_named_fd_is_self_contained(isolated_shell_with_temp_dir):
    """``{v}>file`` is one VAR_FD operation applied by
    ``apply_var_fd_redirect``; it expands its own target and never calls
    ``RedirectPlanner.plan``. Zero is the correct count, not one."""
    shell = isolated_shell_with_temp_dir
    with recorded_plans() as calls:
        status = shell.run_command('echo hi {v}> named')
    assert status == 0
    assert calls == []
    assert int(shell.state.get_variable("v")) >= 10   # bash's first-free >= 10
    assert os.path.exists("named")


# ---- compound commands (the fd backend) ----

@pytest.mark.parametrize("command,expected_ops", [
    ("{ echo hi; } 3> out", 1),
    ("{ echo hi; } 3> a 4> b", 2),
    ("if true; then echo hi; fi 3> out", 1),
    ("while false; do :; done 3> out", 1),
    ("f() { echo hi; }; f 3> out", 1),
])
def test_compound_plans_once(isolated_shell_with_temp_dir,
                             command, expected_ops):
    shell = isolated_shell_with_temp_dir
    run_counting(shell, command, expected_ops)


# ---- nesting: an eval'd builtin inside a redirected eval ----

def test_nested_eval_plans_each_operation_once(isolated_shell_with_temp_dir):
    """Two DISTINCT operations (the eval's and the eval'd echo's), one plan
    each — and the inner frame's restore leaves the outer redirect in place."""
    shell = isolated_shell_with_temp_dir
    run_counting(shell, 'eval \'echo inner 3> i3\' 3> o3', 2)
    with open("i3") as f:
        assert f.read() == ""      # `echo inner` writes to stdout, not fd 3
    assert os.path.exists("o3")


# ---- the fork boundary: an external command plans in its CHILD ----

def test_external_command_plans_nothing_in_the_parent(
        isolated_shell_with_temp_dir):
    """``setup_child_redirections`` runs after the fork, so the parent must not
    resolve the redirect at all — a parent-side plan would run the target's
    command substitutions in the shell itself. The child's own plan-once is
    asserted by the side-effect counter below, which is all the parent can
    observe across the fork."""
    shell = isolated_shell_with_temp_dir
    with recorded_plans() as calls:
        status = shell.run_command("/bin/echo hi 3> out")
    assert status == 0
    assert calls == []
    assert os.path.exists("out")


# ---- side-effect counters: the behavior the call count stands for ----

def _counter_lines(path="ctr"):
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return len(f.readlines())


@pytest.mark.parametrize("command", [
    'echo hi 3> "$(echo x >> ctr; echo o3)"',
    'echo hi 3>> "$(echo x >> ctr; echo o3)"',
    ': 9> "$(echo x >> ctr; echo o9)"',
    'printf hi 4> "$(echo x >> ctr; echo o4)"',
])
def test_command_substitution_in_target_runs_once(
        isolated_shell_with_temp_dir, command):
    """The side effect a second resolution would double: the target's command
    substitution appends one line, so the counter file must hold exactly one.
    Asserted on the file's BYTES, not on the exit status."""
    shell = isolated_shell_with_temp_dir
    assert shell.run_command(command) == 0
    assert _counter_lines() == 1


def test_input_redirect_target_expanded_once(isolated_shell_with_temp_dir):
    """An INPUT target on fd >= 3, with the fd's contents actually consumed.

    Reading fd 3 pins the target of the descriptor, not just the counter: the
    single expansion is the file the builtin ends up reading from."""
    shell = isolated_shell_with_temp_dir
    with open("src", "w") as f:
        f.write("line\n")
    assert shell.run_command(
        'read -u 3 v 3< "$(echo x >> ctr; echo src)"') == 0
    assert shell.state.get_variable("v") == "line"
    assert _counter_lines() == 1


def test_process_substitution_in_target_forks_once(
        isolated_shell_with_temp_dir):
    """A process substitution as a redirect target forks exactly one child.

    Reading fd 3 is what makes this deterministic: it synchronizes on the
    child's own output, which the child writes AFTER appending to the counter.
    Sampling the counter without reading fd 3 races the child in bash too."""
    shell = isolated_shell_with_temp_dir
    assert shell.run_command(
        'read -u 3 v 3< <(echo x >> ctr; echo data)') == 0
    assert shell.state.get_variable("v") == "data"
    assert _counter_lines() == 1


def test_noclobber_checks_the_name_it_opens(isolated_shell_with_temp_dir):
    """The noclobber check and the open must see the SAME expansion.

    With the target expanding to a different name each time, psh checked the
    first name and opened the second: under ``set -C`` with the second name
    pre-existing it refused and created nothing, where bash creates the first.
    Asserted on which file EXISTS, never on the return code alone."""
    shell = isolated_shell_with_temp_dir
    with open("c", "w") as f:
        f.write("0\n")
    with open("f2", "w") as f:
        f.write("OLD\n")
    assert shell.run_command(
        'set -C; echo hi 3> '
        '"$(n=$(cat c); n=$((n+1)); echo $n >| c; echo f$n)"') == 0
    assert os.path.exists("f1"), "the first (and only) expansion was not opened"
    with open("f2") as f:
        assert f.read() == "OLD\n", "the wrong file was opened"
