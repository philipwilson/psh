"""Conformance: compound commands as pipeline members iterate fully.

A compound command used as a pipeline member runs in a forked child. Its
loop body, if it contains an EXTERNAL command, must NOT exec-replace that
child — otherwise the loop ends after one iteration. While/until/for/case
already reset ``context.in_pipeline`` for their body; C-style ``for ((;;))``
and ``select`` did not (Tier R8.1), so they iterated only once when piped.
These pin bash-identical full iteration.
"""

import subprocess
import sys

from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash

PSH = [sys.executable, '-m', 'psh', '-c']
BASH = [resolve_bash().path, '-c']


class TestCompoundInPipeline(ConformanceTest):
    """C-style for / while / for in a pipeline iterate fully (external body)."""

    def test_cstyle_for_in_pipeline_iterates_fully(self):
        self.assert_identical_behavior(
            'for ((i=0;i<3;i++)); do /bin/echo q$i; done | cat')

    def test_while_in_pipeline_iterates_fully(self):
        self.assert_identical_behavior(
            'i=0; while [ $i -lt 3 ]; do /bin/echo w$i; i=$((i+1)); done | cat')

    def test_for_in_pipeline_iterates_fully(self):
        self.assert_identical_behavior(
            'for x in a b c; do /bin/echo f$x; done | cat')

    def test_cstyle_for_not_in_pipeline_unchanged(self):
        self.assert_identical_behavior(
            'for ((i=0;i<3;i++)); do /bin/echo n$i; done')


def _run(argv, cmd, stdin=''):
    r = subprocess.run(argv + [cmd], capture_output=True, text=True,
                       input=stdin)
    return r.stdout, r.returncode


def test_select_in_pipeline_iterates_fully():
    # select reads its choices from stdin; feed two picks then EOF. The
    # menu/prompt go to stderr (suppressed here so only the body's stdout
    # remains). Before R8.1 select omitted the in_pipeline reset, so an
    # external-command body exec-replaced the forked child after one pick.
    script = 'select x in a b; do /bin/echo got=$x; done 2>/dev/null | cat'
    bash_out, _ = _run(BASH, script, stdin='1\n2\n')
    psh_out, _ = _run(PSH, script, stdin='1\n2\n')
    assert psh_out == bash_out, f"bash={bash_out!r} psh={psh_out!r}"
    assert 'got=a' in psh_out and 'got=b' in psh_out, psh_out
