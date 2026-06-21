"""Two executor MED fixes (2026-06-21 appraisal Tier 3, M4/M5).

* M4 — a backgrounded pure/array assignment (``x=5 &``) mutated the PARENT; bash
  runs it in a subshell so the parent is untouched.
* M5 — the DEBUG trap did not fire before ``for`` / C-style-``for`` iterations or
  before a ``case`` statement; bash fires it before each such step.

Counts/values were probe-verified against bash 5.2.
"""

import subprocess
import sys

import pytest


def run(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def run_bash(cmd):
    return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)


class TestBackgroundedAssignmentInSubshell:
    def test_scalar_assignment_does_not_mutate_parent(self):
        r = run('x=5 & wait; echo "x=[$x]"')
        assert r.stdout == "x=[]\n"

    def test_command_sub_assignment_does_not_mutate_parent(self):
        r = run('x=$(echo hi) & wait; echo "x=[$x]"')
        assert r.stdout == "x=[]\n"

    def test_array_assignment_does_not_mutate_parent(self):
        r = run('a[0]=99 & wait; echo "a=[${a[0]}]"')
        assert r.stdout == "a=[]\n"

    def test_sets_bg_pid(self):
        r = run('x=5 & echo "has_pid=$([ -n \"$!\" ] && echo yes)"; wait')
        assert "has_pid=yes" in r.stdout

    def test_non_background_assignment_still_mutates(self):
        r = run('x=5; echo "x=[$x]"')
        assert r.stdout == "x=[5]\n"

    @pytest.mark.parametrize('cmd', [
        'x=5 & wait; echo "[$x]"',
        'a[0]=99 & wait; echo "[${a[0]}]"',
    ])
    def test_matches_bash(self, cmd):
        assert run(cmd).stdout == run_bash(cmd).stdout


class TestDebugTrapBeforeLoopsAndCase:
    @pytest.mark.parametrize('script', [
        'trap "echo D" DEBUG; for i in 1 2; do echo x; done',
        'trap "echo D" DEBUG; for i in 1; do :; done',
        'trap "echo D" DEBUG; case x in x) echo c;; esac',
        'trap "echo D" DEBUG; case z in x) echo c;; esac',
        'trap "echo D" DEBUG; for ((i=0;i<2;i++)); do echo $i; done',
        # regressions (already matched): while / until / if
        'trap "echo D" DEBUG; i=0; while [ $i -lt 1 ]; do echo y; i=1; done',
        'trap "echo D" DEBUG; if true; then echo a; fi',
    ])
    def test_debug_trap_count_matches_bash(self, script):
        assert run(script).stdout == run_bash(script).stdout
