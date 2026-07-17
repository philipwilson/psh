"""break/continue/return must not cross the function or pipeline-subshell scope.

Two boundary bugs (appraisal 2026-06-21, findings H3/H4):

* H3 — a function called from inside a loop inherited the caller's loop
  nesting, so a ``break``/``continue`` in the function body (POSIX: "not
  meaningful") terminated the CALLER's loop instead of erroring.
* H4 — ``return`` (or a ``break N`` exceeding the subshell's own loops) inside
  a pipelined compound leaked the control-flow exception out of the forked
  pipeline child, printing a spurious ``psh: error:`` and the wrong status,
  instead of just ending that subshell with the right code.

Both are fixed by treating a function body and each pipeline component as a
fresh control-flow scope (``loop_depth`` reset to 0). Every expectation here
was probe-verified against bash 5.2 (the error-MESSAGE wording differs by shell
— a separate finding — so we assert behavior/exit code, not stderr text).
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def run(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def run_bash(cmd):
    return subprocess.run([BASH, '-c', cmd], capture_output=True, text=True)


class TestBreakContinueAcrossFunction:
    def test_break_in_function_does_not_break_caller_loop(self):
        # The caller's loop must run all three iterations.
        r = run('f() { break; }; for i in 1 2 3; do echo $i; f; done; echo end')
        assert r.returncode == 0
        assert r.stdout == "1\n2\n3\nend\n"

    def test_continue_in_function_does_not_affect_caller_loop(self):
        r = run('f() { continue; }; for i in 1 2 3; do f; echo $i; done')
        assert r.returncode == 0
        assert r.stdout == "1\n2\n3\n"

    def test_break_level_in_function_loop_stays_in_function(self):
        # `break 2` inside the function's own loop caps at the function's loops;
        # the caller's loop is untouched.
        r = run('f(){ for j in a b; do break 2; done; }; '
                'for i in 1 2 3; do f; echo $i; done; echo end')
        assert r.returncode == 0
        assert r.stdout == "1\n2\n3\nend\n"

    def test_function_own_loop_break_still_works(self):
        r = run('f(){ for j in a b c; do [ $j = b ] && break; echo $j; done; }; '
                'for i in 1 2; do f; echo "i=$i"; done')
        assert r.returncode == 0
        assert r.stdout == "a\ni=1\na\ni=2\n"

    def test_matches_bash(self):
        cmd = 'f() { break; }; for i in 1 2 3; do echo $i; f; done; echo end'
        assert run(cmd).stdout == run_bash(cmd).stdout


class TestReturnBreakInPipelinedCompound:
    def test_return_in_pipelined_while_exits_subshell_with_code(self):
        # bash: the return confines to the pipeline subshell; $? becomes 5 and
        # the function keeps running ("after=5"). No "psh: error:".
        r = run('f() { echo a | while read x; do return 5; done; '
                'echo "after=$?"; }; f')
        assert r.returncode == 0
        assert r.stdout == "after=5\n"
        assert "psh: error" not in r.stderr
        assert "error:" not in r.stderr

    def test_break_level_in_pipelined_while_does_not_leak(self):
        r = run('for i in 1 2; do echo x | while read y; do break 2; done; '
                'echo i=$i; done')
        assert r.returncode == 0
        assert r.stdout == "i=1\ni=2\n"
        assert "error" not in r.stderr

    def test_return_status_propagates_through_pipeline(self):
        r = run('f() { printf "a\\nb\\n" | while read x; do '
                '[ $x = b ] && return 7; done; echo "got=$?"; }; f')
        assert r.returncode == 0
        assert r.stdout == "got=7\n"

    def test_matches_bash(self):
        cmd = ('f() { echo a | while read x; do return 5; done; '
               'echo "after=$?"; }; f')
        assert run(cmd).stdout == run_bash(cmd).stdout
