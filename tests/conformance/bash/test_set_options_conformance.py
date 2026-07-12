"""Conformance pins for the ``set -x`` (xtrace) and ``set -v`` (verbose)
shell options.

The user guide lists both as "Full support", but the older
``TestBashOptions`` class only checked that the options were *settable* -
it never exercised the trace/echo output the options actually produce.
These tests prove that behaviour against bash (trace to stderr with a
``+ `` prefix for xtrace; input lines echoed to stderr for verbose).
"""

import subprocess
import sys

from conformance_framework import ConformanceTest, find_bash


class TestXtraceConformance(ConformanceTest):
    """``set -x`` traces each executed command to stderr with a ``+ `` prefix."""

    def test_xtrace_traces_simple_command(self):
        self.assert_identical_behavior('set -x; echo hi')

    def test_xtrace_traces_assignment_and_command(self):
        self.assert_identical_behavior('set -x; x=5; echo $x')

    def test_xtrace_can_be_turned_off(self):
        self.assert_identical_behavior('set -x; echo on; set +x; echo off')

    def test_xtrace_expands_ps4_lineno(self):
        # The user guide ships `PS4='+ line ${LINENO}: '`; bash expands PS4
        # (parameter/command/arithmetic) on each trace line (R18 T2-E M-s1).
        self.assert_identical_behavior(
            "PS4='+ ${LINENO}: '\nset -x\necho a\necho b")

    def test_xtrace_expands_ps4_command_substitution(self):
        self.assert_identical_behavior("PS4='[$(echo TAG)] '\nset -x\necho a")

    def test_xtrace_expands_ps4_arithmetic(self):
        self.assert_identical_behavior("PS4='$((1+1))> '\nset -x\n:")


class TestVerboseConformance(ConformanceTest):
    """``set -v`` echoes input lines to stderr as the shell reads them."""

    def test_verbose_echoes_subsequent_lines(self):
        self.assert_identical_behavior('set -v\necho hi\necho bye')

    def test_verbose_off_for_the_line_that_enables_it(self):
        self.assert_identical_behavior('echo one\nset -v\necho two')

    def test_verbose_can_be_turned_off(self):
        self.assert_identical_behavior('set -v\necho a\nset +v\necho b')

    def test_verbose_trailing_continuation_into_eof_no_blank_line(self):
        # A trailing backslash-newline continuation that runs into end of input
        # must echo the raw line ONCE — psh used to append a spurious blank line
        # because the buffer kept a line-continuation "reprieve" newline that the
        # verbose print() then doubled.
        self.assert_identical_behavior('set -v\necho a\\\n')

    def test_verbose_backslash_newline_continuation_pair(self):
        # A backslash-newline pair mid-input echoes both physical lines verbatim
        # (with the backslash) and executes the joined command.
        self.assert_identical_behavior('set -v\necho a\\\nb\n')


class TestSetOInvalidNameConformance(ConformanceTest):
    """``set -o BADNAME`` prints ONE line and fails with rc 2 — no dump.

    bash emits only ``set: <name>: invalid option name`` (rc 2). psh used to
    append a ``Valid options: <45 names>`` listing on the enable path with no
    bash analogue. Compared by exit code + stderr content (not the leading
    ``bash: line N:`` prefix, a separate systemic divergence, task #35).
    """

    def _run(self, cmd):
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run([find_bash(), '-c', cmd],
                              capture_output=True, text=True)
        return psh, bash

    def test_set_o_badname_single_line_rc2(self):
        psh, bash = self._run("set -o nosuchopt 2>&1; echo rc=$?")
        assert psh.stdout.endswith("rc=2\n")
        assert bash.stdout.endswith("rc=2\n")
        assert "set: nosuchopt: invalid option name" in psh.stdout
        assert "set: nosuchopt: invalid option name" in bash.stdout
        # No option dump: psh emits exactly the error line + the echo output.
        assert "Valid options:" not in psh.stdout
        assert psh.stdout == "psh: line 1: set: nosuchopt: invalid option name\nrc=2\n"

    def test_set_plus_o_badname_single_line_rc2(self):
        psh, bash = self._run("set +o nosuchopt 2>&1; echo rc=$?")
        assert psh.stdout.endswith("rc=2\n")
        assert bash.stdout.endswith("rc=2\n")
        assert "set: nosuchopt: invalid option name" in psh.stdout
        assert "Valid options:" not in psh.stdout
