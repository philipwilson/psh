r"""Conformance tests for ``${...}`` bad-substitution rejection (bash).

Pins the L1 fix (2026-06-14, reappraisal #6): bash rejects a ``${...}`` whose
parameter name is empty or syntactically invalid with "bad substitution"
(exit 1, reported at EXPANSION time, not parse time). Examples that are
rejected: ``${}``, ``${1abc}``, ``${.foo}``, ``${a.b}``, ``${:-x}``,
``${1abc:-x}``. Examples that remain VALID: ``${12}`` (positional),
``${1}``, ``${a-x}`` (default op), ``${#}`` (count), ``${-}`` ($-),
``${?}``, ``${arr[0]}``, ``${#arr[@]}``, ``${!arr[@]}``.

``${ `` followed by a space is NOT a bad substitution on bash 5.3: NEWS item
s introduced FUNCTION SUBSTITUTION, ``${ command; }`` / ``${|command;}``,
which captures COMMAND's output without forking. So ``${ }`` is an EMPTY
function substitution (rc 0, expands to nothing) and ``${ :-x}`` opens one
that ``:-x}`` never closes (a parse error, rc 2, "unexpected EOF while
looking for matching `}'"). psh has no function substitution and still
rejects both as bad substitutions (rc 1) — a DECLARED divergence, pinned
both-sides in ``TestFunctionSubstitutionDeclaredDivergence`` and parked
(Park P-3) until psh implements the feature.

The valid forms are pinned with ``assert_identical_behavior`` (exact stdout /
stderr / exit match). The rejected forms differ only in the error-message
prefix (``bash: line 1:`` vs ``psh:``), so they are pinned separately by a
direct comparison of exit code + the message tail. All expectations verified
against bash 5.3.15 (Wave 0.1; first pinned on 5.2).
"""

import re

import pytest
from conformance_framework import ConformanceTest
from oracle_policy import oracle_feature
from shell_oracle import is_comparable, run_bash, run_psh


def _run_psh(command):
    r = run_psh(['-c', command])
    assert is_comparable(r), r
    return r


def _run_bash(command):
    r = run_bash(['-c', command])
    assert is_comparable(r), r
    return r


def _error_tail(stderr):
    """Strip the shell-name (and bash's "line N:") prefix from an error line.

    bash's prefix is its $0 — with the resolve_bash() oracle that is a full
    path ("/opt/homebrew/bin/bash: line 1: ..."), so the shell-name part is
    matched as any non-space token ending in the shell name, not a bare word.
    """
    line = stderr.strip()
    # bash: "<argv0>: line 1: ${}: bad substitution"; psh: "psh: ${}: bad substitution"
    line = re.sub(r'^(\S*bash|psh): (line \d+: )?', '', line)
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

    # `${ }` and `${ :-x}` left this list with bash 5.3's function
    # substitution (module docstring); they live in the declared-divergence
    # class below.
    BAD_CASES = [
        "echo ${}",
        "echo ${1abc}",
        "echo ${.foo}",
        "echo ${a.b}",
        "echo ${:-x}",
        "echo ${1abc:-x}",
        "echo ${!.foo}",
        "echo ${!1abc}",
        "echo ${! }",
    ]

    def test_rejected_cases_match_bash(self):
        for command in self.BAD_CASES:
            bash = _run_bash(command)
            psh = _run_psh(command)
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
        bash = _run_bash(command)
        psh = _run_psh(command)
        assert psh.stdout == bash.stdout == "before\n"
        assert psh.returncode == bash.returncode == 1

    def test_not_taken_branch_does_not_error(self):
        command = "if false; then echo ${}; fi; echo reached"
        bash = _run_bash(command)
        psh = _run_psh(command)
        assert psh.stdout == bash.stdout == "reached\n"
        assert psh.returncode == bash.returncode == 0


class TestFunctionSubstitutionDeclaredDivergence:
    """DECLARED DIVERGENCE (Park P-3): bash 5.3 function substitution.

    bash 5.3 NEWS item s: ``${ command; }`` / ``${|command;}`` capture
    COMMAND's output (``${|`` hands back ``$REPLY``) without forking. psh has
    no function substitution and rejects every ``${ `` spelling as a bad
    substitution. Both sides are pinned so the row goes red the moment
    EITHER shell moves — when psh implements the feature these rows become
    parity pins and ``${ }`` returns to the valid-forms class. Guarded by
    the PROBED ``funsub`` oracle feature, never a version literal (D5): an
    oracle without function substitution skips the row with a reason.
    """

    def test_funsub_bash_expands_psh_rejects(self):
        if not oracle_feature('funsub'):
            pytest.skip("oracle bash has no ${ cmd; } function substitution "
                        "(pre-5.3); this declared-divergence row needs one")
        for command, bash_out in [
            ("echo ${ }", "\n"),                 # empty funsub -> nothing
            ("echo ${ echo fs; }", "fs\n"),      # captured output, no fork
            ("echo ${| REPLY=rv; }", "rv\n"),    # ${| form hands back $REPLY
        ]:
            bash = _run_bash(command)
            psh = _run_psh(command)
            assert (bash.returncode, bash.stdout, bash.stderr) == (0, bash_out, ""), (
                f"bash unexpected for {command!r}: {bash}")
            assert psh.returncode == 1 and psh.stdout == "", (
                f"psh unexpected for {command!r}: {psh}")
            assert "bad substitution" in _error_tail(psh.stderr), psh.stderr

    def test_unclosed_funsub_is_a_bash_parse_error(self):
        """``${ :-x}`` opens a function substitution that ``:-x}`` never
        closes: bash 5.3 reports an unexpected EOF (parse error, rc 2)
        where psh still says bad substitution (rc 1)."""
        if not oracle_feature('funsub'):
            pytest.skip("oracle bash has no ${ cmd; } function substitution "
                        "(pre-5.3); this declared-divergence row needs one")
        bash = _run_bash("echo ${ :-x}")
        psh = _run_psh("echo ${ :-x}")
        assert bash.returncode == 2 and bash.stdout == "", bash
        assert "unexpected EOF" in bash.stderr, bash.stderr
        assert psh.returncode == 1 and psh.stdout == "", psh
        assert "bad substitution" in _error_tail(psh.stderr), psh.stderr
