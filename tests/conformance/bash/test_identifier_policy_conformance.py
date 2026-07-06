r"""Conformance tests for the identifier policy (reappraisal #18, Tier-3 T3-5).

psh routes every runtime name-validation site through one authoritative
predicate (``unicode_support.is_valid_name``). The rules, pinned against
bash 5.2:

* **Valid ASCII names** (``foo``, ``_bar``, ``x9``) behave IDENTICALLY to bash
  in both default and ``set -o posix`` mode — at assignment, ``declare``,
  ``export``, ``read``, ``for`` and function definition.
* **Names that never start legally** (``9x``, ``a-b``) are rejected in BOTH
  modes, exactly as bash does (``9x=1`` runs as a command → 127; ``read 9x`` →
  status 1).
* **Under ``set -o posix``**, Unicode-letter names (``é``, ``naïve``, ``café``)
  are REJECTED just as bash rejects them — an assignment ``é=1`` becomes a
  command (``command not found``, 127); ``declare``/``export``/``read`` report
  "not a valid identifier" (status 1) and continue.
* **Without posix mode**, psh ACCEPTS those Unicode-letter names — a DELIBERATE,
  documented divergence from bash (see docs/user_guide/17_differences_from_bash.md).
  This class pins BOTH sides so the divergence is explicit and intentional.

Note on ``for``/``function`` error flow: in DEFAULT mode both shells report
"not a valid identifier" (status 1) and CONTINUE — psh matches bash. The flow
differs only under ``set -o posix``: bash then treats the invalid name as a
PARSE error and aborts the whole input (exit 2), whereas psh — which parses the
entire program before executing, so runtime ``set -o posix`` cannot influence
parsing — still rejects it at EXECUTION time (status 1, then continues). Both
REJECT the name; only the posix abort-vs-continue flow differs. The posix cases
are pinned as "psh rejects, bash rejects" rather than identical.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest

PSH = [sys.executable, '-m', 'psh', '-c']
BASH = ['bash', '-c']


# These tests compare how bash and psh RENDER Unicode identifier names (é,
# naïve, café) in diagnostics, which is only well-defined in a UTF-8 locale:
# under LC_ALL=C (the suite-wide pin) bash escapes é to ``$'\303\251'`` while
# psh keeps it as UTF-8, so the byte-equality assertion below would spuriously
# fail. Pin an explicit UTF-8 locale for these subprocesses (overrides the
# suite pin for these children only). C.UTF-8 is portable across the macOS gate
# and the Linux nightly.
_UTF8_ENV = {**os.environ, 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8'}


def _run(argv, command):
    # errors='replace': bash expanding an invalid ``$é`` can emit non-UTF-8
    # bytes; we only assert on exit codes and ASCII substrings for those cases.
    return subprocess.run(argv + [command], capture_output=True, text=True,
                          errors='replace', timeout=30, env=_UTF8_ENV)


def _tail(stderr):
    """Strip the shell-name (and bash's "line N:") prefix from an error line."""
    line = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    return re.sub(r'^(bash|psh): (line \d+: )?', '', line)


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

    def test_declare_export_read_report_and_continue(self):
        for builtin in ["declare é=1", "export é=1", "read é <<< hi"]:
            command = f"set -o posix; {builtin}; echo done"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert psh.stdout == bash.stdout == "done\n", command
            assert psh.returncode == bash.returncode == 0, command
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command

    def test_for_and_function_rejected_by_both(self):
        # Both shells REJECT; bash parse-aborts (exit 2), psh rejects at exec
        # (status 1, then continues) — see module docstring.
        for construct in ["for é in a; do echo body; done",
                          "function é { echo body; }",
                          "é() { echo body; }"]:
            command = f"set -o posix; {construct}"
            bash = _run(BASH, command)
            psh = _run(PSH, command)
            assert bash.returncode != 0, command
            assert psh.returncode != 0 or "body" not in psh.stdout, command
            assert "not a valid identifier" in psh.stderr, command
            assert "not a valid identifier" in bash.stderr, command
            assert "body" not in psh.stdout, command  # body never runs


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
