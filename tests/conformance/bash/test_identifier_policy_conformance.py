r"""Conformance tests for the identifier policy (reappraisal #18, Tier-3 T3-5).

psh routes every runtime name-validation site through one authoritative
predicate (``unicode_support.is_valid_name``). The rules, pinned against
bash 5.2 and re-verified against bash 5.3.15 (Wave 0.2, 2026-09-06):

* **Valid ASCII names** (``foo``, ``_bar``, ``x9``) behave IDENTICALLY to bash
  in both default and ``set -o posix`` mode — at assignment, ``declare``,
  ``export``, ``read``, ``for`` and function definition.
* **Names that never start legally** (``9x``, ``a-b``) are rejected in BOTH
  modes, exactly as bash does (``9x=1`` runs as a command → 127; ``read 9x`` →
  status 1).
* **Under ``set -o posix``**, Unicode-letter names (``é``, ``naïve``, ``café``)
  are REJECTED just as bash rejects them — an assignment ``é=1`` becomes a
  command (``command not found``, 127); ``declare``/``read`` report "not a
  valid identifier" (status 1) and continue in both shells, while ``export``/
  ``readonly`` EXIT a non-interactive posix shell (bash 5.3 CHANGES,
  bash-5.3-alpha, "1. Changes to Bash" items jj / nnnnn; psh followed in slot
  2.2, so test_export_readonly_unicode_exit_in_posix is an equality row).
* **Function NAMES are unrestricted in posix mode** in both shells (bash 5.3
  CHANGES, 5.3-beta "New Features in Bash" item p: "Posix mode no longer
  requires function names to be valid shell identifiers"): ``é``, ``9x`` and
  ``a-b`` all define and run. bash 5.3 still validates the OPERAND of
  ``declare -f``/``-F``/``typeset -f`` under posix; psh does not (declared
  divergence, pinned both sides in TestPosixFunctionNamesUnrestricted).
* **Without posix mode**, psh ACCEPTS those Unicode-letter names — a DELIBERATE,
  documented divergence from bash (see docs/user_guide/17_differences_from_bash.md).
  This class pins BOTH sides so the divergence is explicit and intentional.

Note on ``for``/``select`` error flow: in DEFAULT mode both shells report
"not a valid identifier" (status 1) and CONTINUE — psh matches bash. The flow
differs only under ``set -o posix``: bash then treats the invalid name as a
PARSE error and aborts the whole input (exit 2), whereas psh rejects it at
EXECUTION time (status 1, then continues). Both REJECT the name; only the
posix abort-vs-continue flow differs, and the posix cases are pinned as "psh
rejects, bash rejects" rather than identical. (bash 5.3 CHANGES 5.3-alpha
"Changes to Bash" item hhhhh makes ``select`` behave like ``for`` here.)

The REASON is not that psh parses everything up front — it does not, and the
sentence that used to say so here was false at every commit. psh's execution
parses ONE COMMAND AT A TIME, so a runtime ``set -o posix`` DOES reach the
parse of later commands: measured, ``äö=hello`` followed by ``echo $äö``
prints ``hello``, while the same script with ``set -o posix`` between them
prints ``$äö`` — the option changed how the LATER command was parsed. What
differs between the shells is WHERE the name is judged: psh's parser accepts
the ``for`` name and the identifier policy rejects it at execution, while bash
rejects it in the parser. The pinned conclusion below is unchanged.

This sentence was the verbatim twin of the user-guide claim corrected earlier
in remediation 2.6 (R11-B N4); it is fixed here under R21-A, and a
certification row now asserts the whole phrase family is absent tree-wide so a
third twin cannot survive.
"""

import re

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, run_bash, run_psh

PSH = 'psh'
BASH = 'bash'


# These tests compare how bash and psh RENDER Unicode identifier names (é,
# naïve, café) in diagnostics, which is only well-defined in a UTF-8 locale:
# under LC_ALL=C (the suite-wide pin) bash escapes é to ``$'\303\251'`` while
# psh keeps it as UTF-8, so the byte-equality assertion below would spuriously
# fail. Pin an explicit UTF-8 locale for these subprocesses (overrides the
# suite pin for these children only). C.UTF-8 is portable across the macOS gate
# and the Linux nightly.
_UTF8_ENV = {'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8'}


def _run(shell, command):
    runner = run_psh if shell == PSH else run_bash
    r = runner(['-c', command], timeout=30, env=_UTF8_ENV)
    assert is_comparable(r), r
    return r


def _tail(stderr):
    """Strip the shell-name (and bash's "line N:") prefix from an error line.

    bash's prefix is its $0 — a full path under the resolve_bash() oracle —
    so the shell-name part matches any non-space token ending in the name.
    """
    line = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    return re.sub(r'^(\S*bash|psh): (line \d+: )?', '', line)


class TestValidAsciiNamesIdentical(ConformanceTest):
    """Valid ASCII names behave identically to bash in BOTH modes."""

    def test_assignment_default(self):
        self.assert_identical_behavior("foo=1; echo $foo")

    def test_assignment_posix(self):
        self.assert_identical_behavior("set -o posix; foo=1; echo $foo")

    def test_underscore_name(self):
        self.assert_identical_behavior("set -o posix; _bar=hi; echo $_bar")

    def test_trailing_digit(self):
        self.assert_identical_behavior("set -o posix; x9=z; echo $x9")

    def test_declare_default(self):
        self.assert_identical_behavior("declare foo=1; echo $foo")

    def test_declare_posix(self):
        self.assert_identical_behavior("set -o posix; declare foo=1; echo $foo")

    def test_export_posix(self):
        self.assert_identical_behavior("set -o posix; export FOO=bar; echo $FOO")

    def test_read_posix(self):
        self.assert_identical_behavior("set -o posix; read a b <<< '1 2'; echo \"$a-$b\"")

    def test_for_posix(self):
        self.assert_identical_behavior(
            "set -o posix; for i in 1 2 3; do echo -n $i; done; echo")

    def test_function_posix(self):
        self.assert_identical_behavior("set -o posix; foo() { echo hi; }; foo")

    def test_array_element_read(self):
        self.assert_identical_behavior('read "a[0]" <<< hi; echo "${a[0]}"')


class TestInvalidInBothModes:
    """``9x`` / ``a-b`` are rejected in BOTH modes, matching bash."""

    def test_assignment_runs_as_command_127(self):
        for command in ["9x=1; echo rc=$?", "a-b=1; echo rc=$?"]:
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "rc=127\n", command
            assert psh.returncode == bash.returncode == 0, command

    def test_assignment_posix_also_127(self):
        for command in ["set -o posix; 9x=1; echo rc=$?"]:
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "rc=127\n", command

    def test_read_rejects_in_both_modes(self):
        for prefix in ["", "set -o posix; "]:
            command = prefix + "read 9x <<< hi; echo rc=$?"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "rc=1\n", command
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command


class TestPosixRestrictsUnicodeLikeBash:
    """Under ``set -o posix``, Unicode names are rejected exactly as bash does."""

    def test_assignment_becomes_command_not_found(self):
        for name in ["é", "naïve", "café"]:
            command = f"set -o posix; {name}=1; echo done"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            # Not an assignment -> run as a command -> not found (127), then the
            # next command runs (stdout "done", final exit 0). Message tails match.
            assert psh.stdout == bash.stdout == "done\n", command
            assert psh.returncode == bash.returncode == 0, command
            assert "command not found" in _tail(psh.stderr), command
            assert _tail(psh.stderr) == _tail(bash.stderr), command

    def test_declare_read_report_and_continue(self):
        # declare and read are NOT POSIX special builtins: bash 5.3.15 still
        # reports "not a valid identifier" (status 1) and continues; psh is
        # identical.  (export/readonly moved to the declared-divergence row
        # below when bash 5.3 made them exit.)
        for builtin in ["declare é=1", "read é <<< hi"]:
            command = f"set -o posix; {builtin}; echo done"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "done\n", command
            assert psh.returncode == bash.returncode == 0, command
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command

    @pytest.mark.oracle_min("5.3")
    def test_export_readonly_unicode_exit_in_posix(self):
        """The POSIX special builtins ``export`` and ``readonly`` EXIT a
        non-interactive posix-mode shell on an invalid identifier.

        bash 5.3 (CHANGES, bash-5.3-alpha, "1. Changes to Bash" items jj /
        nnnnn) widened the exit set to this operand error; psh followed in
        slot 2.2 (gate row G22).  Probed on 5.3.15 (C.UTF-8, -c / script /
        stdin alike): ``export é=1`` and ``readonly é=1`` print nothing to
        stdout and exit 1, and both sides diagnose "not a valid identifier".
        The three-mode legs live in
        tests/conformance/posix/test_posix_special_builtin_exit_conformance.py
        (this module's runner is -c only).
        """
        for builtin in ["export é=1", "readonly é=1"]:
            command = f"set -o posix; {builtin}; echo done"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert (bash.stdout, bash.returncode) == ("", 1), (
                f"ORACLE side moved: {command!r} -> {bash.stdout!r} "
                f"rc={bash.returncode}")
            assert (psh.stdout, psh.returncode) == ("", 1), (
                f"{command!r} -> {psh.stdout!r} rc={psh.returncode}")
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command

    def test_for_and_select_rejected_by_both(self):
        # Both shells REJECT; bash parse-aborts (exit 2), psh rejects at exec
        # (status 1, then continues) — see module docstring. Function names
        # left this loop in Wave 0.2 (bash 5.3 accepts them; class below).
        for construct in ["for é in a; do echo body; done",
                          "select é in a; do echo body; done </dev/null"]:
            command = f"set -o posix; {construct}"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert bash.returncode != 0, command
            assert psh.returncode != 0 or "body" not in psh.stdout, command
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command
            assert "body" not in psh.stdout, command  # body never runs


@pytest.mark.oracle_min("5.3")
class TestPosixFunctionNamesUnrestricted:
    """Function names are NOT identifier-checked under ``set -o posix``.

    bash 5.3 CHANGES (5.3-beta, "New Features in Bash" item p): "Posix mode
    no longer requires function names to be valid shell identifiers." 5.2
    parse-aborted these; psh rejected them at execution. Verified against
    5.3.15 (Wave 0.2; gate node test_for_and_function_rejected_by_both, split).
    """

    def test_function_names_unrestricted_in_posix(self):
        for name in ["é", "naïve", "9x", "a-b"]:
            for construct in [f"function {name} {{ echo body; }}",
                              f"{name}() {{ echo body; }}"]:
                command = f"set -o posix; {construct}; {name}; echo rc=$?"
                bash = _run(BASH, command)
                psh = _run(PSH, command)
                assert psh.stdout == bash.stdout == "body\nrc=0\n", command
                assert psh.returncode == bash.returncode == 0, command
                assert psh.stderr == bash.stderr == "", command

    def test_posix_enabled_after_definition_still_calls(self):
        # GREEN CONTROL (passes on the Wave 0 base): a function defined before
        # `set -o posix` was always callable afterwards; lookup never checked.
        command = "é() { echo body; }; set -o posix; é; echo rc=$?"
        bash = _run(BASH, command)
        psh = _run(PSH, command)
        assert psh.stdout == bash.stdout == "body\nrc=0\n"
        assert psh.stderr == bash.stderr == ""

    def test_readonly_and_export_f_accept_any_defined_function(self):
        # -f operands of readonly/export are function names, not identifiers:
        # bash 5.3 accepts a defined `é` (rc 0) and reports an undefined one
        # as `not a function` (psh says `not found` for readonly — pre-existing
        # wording nit, not pinned here).
        for builtin in ["readonly -f é", "export -f é"]:
            command = f"set -o posix; é() {{ echo body; }}; {builtin}; echo rc=$?; é"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "rc=0\nbody\n", command
            assert psh.stderr == bash.stderr == "", command

    def test_unset_f_accepts_any_function_name_in_posix(self):
        command = ("set -o posix; é() { echo body; }; unset -f é; echo rc=$?; "
                   "é 2>/dev/null; echo rc=$?")
        bash = _run(BASH, command)
        psh = _run(PSH, command)
        assert psh.stdout == bash.stdout == "rc=0\nrc=127\n"
        assert psh.stderr == bash.stderr == ""  # the definition is silent

    def test_declare_f_operand_check_is_a_declared_divergence(self):
        """DECLARED DIVERGENCE (Wave 0.2 side finding; needs a ledger N-row
        with an owner). bash 5.3 still identifier-checks the OPERAND of
        `declare -f` / `declare -F` / `typeset -f` under posix — `declare:
        `é': not a valid identifier`, rc 1 — even when é is defined; psh's
        function path does not validate -f operands and prints the definition,
        rc 0. Both sides pinned so the divergence is explicit; flip this pin
        when psh adopts the operand check.
        """
        command = "set -o posix; é() { echo body; }; declare -f é; echo rc=$?"
        bash = _run(BASH, command)
        psh = _run(PSH, command)
        assert bash.stdout == "rc=1\n" and "not a valid identifier" in bash.stderr
        assert psh.stdout.endswith("rc=0\n") and "echo body" in psh.stdout
        assert psh.stderr == ""


class TestUnicodeAcceptedWithoutPosixDivergence:
    """DELIBERATE divergence: without posix mode psh accepts Unicode names that
    bash rejects. Pins BOTH sides so the divergence is explicit."""

    def test_assignment_accepted_by_psh_rejected_by_bash(self):
        # psh: é is a valid name without posix mode -> assignment succeeds.
        psh = _run(PSH, 'é=5; echo "$é"')
        assert psh.stdout == "5\n", psh.stdout
        assert psh.returncode == 0
        # bash: é=5 is not an assignment -> command not found (127).
        bash = _run(BASH, "é=5")
        assert bash.returncode == 127

    def test_declare_accepted_by_psh(self):
        psh = _run(PSH, "declare é=1; echo rc=$?")
        assert psh.stdout == "rc=0\n"
        bash = _run(BASH, "declare é=1; echo rc=$?")
        assert bash.stdout == "rc=1\n"

    def test_for_loop_accepted_by_psh(self):
        psh = _run(PSH, "for é in a b; do echo -n $é; done; echo")
        assert psh.stdout == "ab\n"
        assert psh.returncode == 0

    def test_function_name_accepted_by_psh(self):
        # bash ALSO accepts Unicode function names without posix mode, so this
        # one actually agrees with bash in the default mode.
        psh = _run(PSH, "é() { echo hi; }; é")
        bash = _run(BASH, "é() { echo hi; }; é")
        assert psh.stdout == bash.stdout == "hi\n"
        assert psh.returncode == bash.returncode == 0
