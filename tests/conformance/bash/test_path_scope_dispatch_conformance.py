"""Conformance: a scope pop rebinds PATH, so the next dispatch re-resolves (C044).

Returning from a function that held a ``local PATH`` restores the variable, and
must restore what a command NAME resolves to with it.  psh remembered command
locations in a table keyed only on PATH *writes*, and a pop writes no name, so
the entry the discarded scope had put there survived and the next command ran
the wrong executable -- silently, with the right name and the right ``$PATH``::

    PATH=$PWD/a; f(){ local PATH=$PWD/b; probe; }; f; probe
    # bash 5.3.15: B then A.  psh before slot 1.5: B then B.

Every row here dispatches REAL executables -- ``a/probe`` echoes A, ``b/probe``
echoes B -- so what is compared is the binary that ran, not a restored string
(D3).  The reads that follow a pop (``command -v``, ``type``, ``hash -t``) are
pinned too, because they are the same question asked of the same table.

Empirical against bash 5.3.15; this follows no bash 5.3 behavior change, so no
CHANGES item is cited.  Improvement Program 2026-09 slot 1.5 (finding C044).
"""
import os

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import hermetic_shell_env, is_comparable, run_bash, run_psh

#: Two marker executables, and PATH pointing at the first.  Written by the
#: script itself so a row is reproducible by pasting it into either shell.
LAYOUT = (
    'mkdir -p a b\n'
    "printf '#!/bin/sh\\necho A\\n' > a/probe\n"
    "printf '#!/bin/sh\\necho B\\n' > b/probe\n"
    'chmod +x a/probe b/probe\n'
    'PATH=$PWD/a\n'
)

#: The same with a third marker.  PATH is narrowed to ``a`` only at the END of
#: the layout, so every directory has to exist before it: ``mkdir`` is itself an
#: external command and would no longer be findable.
LAYOUT3 = (
    'mkdir -p a b c\n'
    "printf '#!/bin/sh\\necho A\\n' > a/probe\n"
    "printf '#!/bin/sh\\necho B\\n' > b/probe\n"
    "printf '#!/bin/sh\\necho C\\n' > c/probe\n"
    'chmod +x a/probe b/probe c/probe\n'
    'PATH=$PWD/a\n'
)


class TestScopeExitRestoresDispatch(ConformanceTest):
    """Which executable runs after the scope that changed PATH goes away."""

    def test_local_path_then_return(self):
        """The headline C044 repro: B inside the function, A after it."""
        self.assert_identical_behavior(
            LAYOUT + 'f(){ local PATH=$PWD/b; probe; }\nf\nprobe')

    def test_local_path_declared_then_assigned(self):
        self.assert_identical_behavior(
            LAYOUT + 'f(){ local PATH; PATH=$PWD/b; probe; }\nf\nprobe')

    def test_temp_env_prefix_over_a_function(self):
        """The prefix form: the temp-env scope pops the same way a local does."""
        self.assert_identical_behavior(
            LAYOUT + 'f(){ probe; }\nPATH=$PWD/b f\nprobe')

    def test_nested_functions(self):
        """The inner function holds the local; both outer frames see A again."""
        self.assert_identical_behavior(
            LAYOUT + 'g(){ local PATH=$PWD/b; probe; }\n'
            'f(){ g; probe; }\nf\nprobe')

    def test_three_deep_each_frame_restores_its_own(self):
        self.assert_identical_behavior(
            LAYOUT3 + 'h(){ local PATH=$PWD/c; probe; }\n'
            'g(){ local PATH=$PWD/b; probe; h; probe; }\n'
            'f(){ g; probe; }\nf\nprobe')

    def test_early_return(self):
        self.assert_identical_behavior(
            LAYOUT + 'f(){ local PATH=$PWD/b; probe; return 0; }\nf\nprobe')

    def test_failing_body(self):
        self.assert_identical_behavior(
            LAYOUT + 'f(){ local PATH=$PWD/b; probe; false; }\nf\nprobe')

    def test_errexit_does_not_skip_the_restore(self):
        self.assert_identical_behavior(
            'set -e\n' + LAYOUT
            + 'f(){ local PATH=$PWD/b; probe; false; probe; }\nf || true\nprobe')

    def test_declare_g_under_a_local_lands_after_the_pop(self):
        """`declare -g` writes the shadowed global; the pop is what reveals it."""
        self.assert_identical_behavior(
            LAYOUT3
            + 'f(){ local PATH=$PWD/b; probe; declare -g PATH=$PWD/c; probe; }\n'
            'f\nprobe')

    def test_unset_of_the_local_reveals_the_outer_after_the_pop(self):
        self.assert_identical_behavior(
            LAYOUT3
            + 'f(){ local PATH=$PWD/b; probe; unset PATH; PATH=$PWD/c; probe; }\n'
            'f\nprobe')

    def test_a_subshell_does_not_disturb_the_parent(self):
        self.assert_identical_behavior(
            LAYOUT + '( PATH=$PWD/b; probe )\nprobe')

    def test_a_local_that_never_dispatched_is_still_restored(self):
        """The control: no dispatch inside, so nothing was remembered."""
        self.assert_identical_behavior(
            LAYOUT + 'f(){ local PATH=$PWD/b; }\nf\nprobe')

    def test_an_ordinary_return_leaves_the_table_alone(self):
        """A function that binds no PATH keeps the remembered location (bash)."""
        self.assert_identical_behavior(
            LAYOUT + 'probe\nf(){ local X=1; }\nf\nhash -t probe > /dev/null\n'
            'echo "still-hashed=$?"')


# ---------------------------------------------------------------------------
# The same questions in all three input modes (D6), against live bash.
#
# Both shells run in ONE directory so an absolute path printed by `command -v`
# or `hash -t` is comparable; the layout is idempotent, and neither shell can
# see the other's hash table.
# ---------------------------------------------------------------------------

MODES = ("-c", "script", "stdin")

#: ``(id, script, expected stdout)``.  The expectation is bash 5.3.15's own
#: output, asserted alongside the live comparison so a change in either shell
#: is visible rather than silently agreed on.
ROWS = (
    ("dispatch-after-pop",
     LAYOUT + 'f(){ local PATH=$PWD/b; probe; }\nf\nprobe\n', 'B\nA\n'),
    ("dispatch-after-temp-env-pop",
     LAYOUT + 'f(){ probe; }\nPATH=$PWD/b f\nprobe\n', 'B\nA\n'),
    ("dispatch-after-nested-pop",
     LAYOUT + 'g(){ local PATH=$PWD/b; probe; }\nf(){ g; probe; }\nf\nprobe\n',
     'B\nA\nA\n'),
    # `command -v` answers from the same table the dispatcher uses, so it must
    # name the restored PATH's copy.  Printed relative to $PWD so the row does
    # not depend on where the case ran.
    ("command-v-after-pop",
     LAYOUT + 'f(){ local PATH=$PWD/b; probe; }\nf\n'
     'p=$(command -v probe)\necho "${p#$PWD/}"\n', 'B\na/probe\n'),
    # `type` names the same file.  Trimmed with parameter expansion, not
    # `sed`: PATH holds only the marker directory by then.
    ("type-after-pop",
     LAYOUT + 'f(){ local PATH=$PWD/b; probe; }\nf\n'
     't=$(type probe)\nt=${t#*is }\necho "${t#$PWD/}"\n', 'B\na/probe\n'),
    # `hash -t` after the pop: the table was emptied, so the next dispatch
    # re-hashes through the restored PATH.
    ("hash-t-after-pop",
     LAYOUT + 'f(){ local PATH=$PWD/b; probe; }\nf\nprobe\n'
     'h=$(hash -t probe)\necho "${h#$PWD/}"\n', 'B\nA\na/probe\n'),
    ("unset-then-restored-path",
     LAYOUT + 'probe\nunset PATH\nprobe 2>/dev/null\necho "rc=$?"\n'
     'PATH=$PWD/b\nprobe\n', 'A\nrc=127\nB\n'),
)


def _run(runner, script, cwd, mode):
    env = hermetic_shell_env()
    if mode == "-c":
        return runner(["-c", script], cwd=cwd, env=env)
    if mode == "script":
        path = os.path.join(cwd, "case.sh")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(script + "\n")
        return runner([path], cwd=cwd, env=env)
    return runner([], stdin_data=script + "\n", cwd=cwd, env=env)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "script,expected", [pytest.param(s, e, id=i) for i, s, e in ROWS])
def test_dispatch_after_scope_exit(tmp_path, script, expected, mode):
    """psh and bash 5.3.15 agree, and both produce the recorded output (C044)."""
    cwd = str(tmp_path)
    bash = _run(run_bash, script, cwd, mode)
    psh = _run(run_psh, script, cwd, mode)
    assert is_comparable(bash) and is_comparable(psh), (bash, psh)
    # A clean-success row: a dropped `[Errno 1] Operation not permitted` from
    # the host's concurrent-exec flake identifies itself here instead of
    # looking like a regression.
    assert (bash.stderr, psh.stderr) == ("", ""), (bash.stderr, psh.stderr)
    assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode)
    assert bash.stdout == expected
