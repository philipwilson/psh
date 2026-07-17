r"""Conformance tests for ``${...}`` bad-substitution rejection (bash).

Pins the L1 fix (2026-06-14, reappraisal #6): bash rejects a ``${...}`` whose
parameter name is empty or syntactically invalid with "bad substitution"
(exit 1, reported at EXPANSION time, not parse time). Examples that are
rejected: ``${}``, ``${ }``, ``${1abc}``, ``${.foo}``, ``${a.b}``,
``${:-x}``, ``${1abc:-x}``. Examples that remain VALID: ``${12}`` (positional),
``${1}``, ``${a-x}`` (default op), ``${#}`` (count), ``${-}`` ($-),
``${?}``, ``${arr[0]}``, ``${#arr[@]}``, ``${!arr[@]}``.

The valid forms are pinned with ``assert_identical_behavior`` (exact stdout /
stderr / exit match). The rejected forms differ only in the error-message
prefix (``bash: line 1:`` vs ``psh:``), so they are pinned separately by a
direct subprocess comparison of exit code + the message tail. All expectations
verified against bash 5.2.
"""

import re
import subprocess
import sys

from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash

PSH = [sys.executable, '-m', 'psh', '-c']
BASH = [resolve_bash().path, '-c']


def _run(argv, command):
    return subprocess.run(argv + [command], capture_output=True, text=True)


def _error_tail(stderr):
    """Strip the shell-name (and bash's "line N:") prefix from an error line."""
    line = stderr.strip()
    # bash: "bash: line 1: ${}: bad substitution"; psh: "psh: ${}: bad substitution"
    line = re.sub(r'^(bash|psh): (line \d+: )?', '', line)
    return line


class TestBadSubstitutionValidForms(ConformanceTest):
    """Forms bash ACCEPTS must keep working identically in psh."""

    def test_positional_two_digits(self):
        self.assert_identical_behavior("echo ${12}")

    def test_positional_one(self):
        self.assert_identical_behavior("echo ${1}")

    def test_default_operator(self):
        self.assert_identical_behavior("echo ${a-x}")

    def test_count(self):
        self.assert_identical_behavior("echo ${#}")

    def test_dash_special(self):
        # $- option flags differ between shells, so just check it does not error.
        self.assert_identical_behavior("echo ${-} >/dev/null; echo ok")

    def test_question(self):
        self.assert_identical_behavior("echo ${?}")

    def test_length_of_unset(self):
        self.assert_identical_behavior("echo ${#x}")

    def test_array_element(self):
        self.assert_identical_behavior("arr=(p q); echo ${arr[0]}")

    def test_array_count(self):
        self.assert_identical_behavior("arr=(p q); echo ${#arr[@]}")

    def test_array_keys(self):
        self.assert_identical_behavior("arr=(p q); echo ${!arr[@]}")

    def test_indirection_with_default(self):
        self.assert_identical_behavior("ref=ROW; ROW=val; echo ${!ref:-d}")

    def test_indirection_unset_uses_default(self):
        self.assert_identical_behavior("echo ${!10:-none}")


class TestBadSubstitutionRejected:
    """Forms bash REJECTS with "bad substitution" (exit 1, message tail)."""

    BAD_CASES = [
        "echo ${}",
        "echo ${ }",
        "echo ${1abc}",
        "echo ${.foo}",
        "echo ${a.b}",
        "echo ${:-x}",
        "echo ${1abc:-x}",
        "echo ${ :-x}",
        "echo ${!.foo}",
        "echo ${!1abc}",
        "echo ${! }",
    ]

    def test_rejected_cases_match_bash(self):
        for command in self.BAD_CASES:
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert bash.returncode == 1, f"bash unexpected for {command!r}: {bash.stderr}"
            assert psh.returncode == bash.returncode, (
                f"exit mismatch for {command!r}: bash={bash.returncode} psh={psh.returncode}")
            assert psh.stdout == bash.stdout == "", (
                f"stdout mismatch for {command!r}: bash={bash.stdout!r} psh={psh.stdout!r}")
            # Message tail (after the shell-name / "line N:" prefix) must match.
            bash_tail = _error_tail(bash.stderr)
            psh_tail = _error_tail(psh.stderr)
            assert "bad substitution" in psh_tail, (
                f"psh did not report bad substitution for {command!r}: {psh.stderr!r}")
            assert psh_tail == bash_tail, (
                f"message tail mismatch for {command!r}: bash={bash_tail!r} psh={psh_tail!r}")

    def test_reported_at_runtime_not_parse(self):
        # bash reports bad substitution at runtime: an earlier command runs.
        command = "echo before; echo ${}; echo after"
        bash = _run(BASH, command)
        psh = _run(PSH, command)
        assert psh.stdout == bash.stdout == "before\n"
        assert psh.returncode == bash.returncode == 1

    def test_not_taken_branch_does_not_error(self):
        command = "if false; then echo ${}; fi; echo reached"
        bash = _run(BASH, command)
        psh = _run(PSH, command)
        assert psh.stdout == bash.stdout == "reached\n"
        assert psh.returncode == bash.returncode == 0
