"""The absent-feature ledger: one strict-xfail test per verified-absent bash feature.

Purpose (reappraisal #3, Tier A2): the conformance suite's headline number
only counts features psh HAS; this file gives the denominator its missing
entries. Every test here was probed against bash 5.2 and psh on 2026-06-12
and pins the bash behavior psh currently lacks. Each is marked
``xfail(strict=True)``: the moment psh implements the feature conformantly,
the test XPASSes and (being strict) FAILS the suite loudly — remove the
marker and move the test into the appropriate conformance file.

Comparison contract: stdout and exit code must match bash exactly, and the
two shells must agree on WHETHER anything went to stderr (emptiness, not
text — error-message prefixes legitimately differ: ``psh:`` vs ``bash:``).
Comparing stderr text exactly would make several entries permanently
unflippable.

History expansion (``!!``, ``!n``) is deliberately NOT in this ledger as an
xfail: it is a documented wontfix (see
docs/reviews/architecture_feature_review_2026-06-09.md and the xfail-marked
tests in tests/integration/interactive/test_history.py) — it appears below
as a skip so the census shows the decision rather than a pending feature.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTestFramework

_framework = ConformanceTestFramework()


def assert_bash_parity(command: str):
    """Assert psh matches bash on stdout, exit code, and stderr-emptiness."""
    psh = _framework.run_in_psh(command)
    bash = _framework.run_in_bash(command)
    assert psh.stdout == bash.stdout and psh.exit_code == bash.exit_code \
        and bool(psh.stderr) == bool(bash.stderr), (
        f"psh and bash differ for: {command}\n"
        f"PSH:  stdout={psh.stdout!r} stderr={psh.stderr!r} exit={psh.exit_code}\n"
        f"Bash: stdout={bash.stdout!r} stderr={bash.stderr!r} exit={bash.exit_code}"
    )


class TestAbsentBashFeatures:
    """Verified-absent bash features (probe date 2026-06-12, bash 5.2.26)."""

    @pytest.mark.xfail(strict=True, reason="coproc is not implemented")
    def test_coproc(self):
        """bash: coproc spawns a co-process with fds in ${NAME[0]}/${NAME[1]};
        `coproc CAT { cat; }` lets the shell write to and read from it
        (probe printed got:hi, exit 0). psh: `coproc` is command-not-found
        and the body parses as stray commands."""
        assert_bash_parity(
            'coproc CAT { cat; }; echo hi >&${CAT[1]}; '
            'read line <&${CAT[0]}; echo got:$line')

    # `wait -n` was implemented in v0.557.0 (appraisal #14 Tier 2); its
    # conformance coverage moved to tests/integration/functions/test_wait_n.py.

    @pytest.mark.xfail(strict=True, reason="wait -f is not implemented")
    def test_wait_dash_f(self):
        """bash: `wait -f PID` waits until the job actually terminates
        (probe: rc=0, no stderr). psh: rejects -f as 'not a valid process
        id' on stderr (its stdout happens to match, so this entry leans on
        the stderr-emptiness check)."""
        assert_bash_parity('sleep 0.05 & wait -f $!; echo rc=$?')

    def test_read_dash_u(self):
        """`read -u 3` reads from fd 3 — now matches bash (got:fd_data_xyz).

        Was xfail: it relied on a here-string on an explicit fd
        (``3<<< fd_data_xyz``), which mis-delivered the body until the M6
        explicit-fd heredoc/here-string self-close fix (v0.532). Now parity."""
        assert_bash_parity('read -u 3 line 3<<< fd_data_xyz; echo got:$line')

    @pytest.mark.xfail(strict=True, reason="bind builtin is not implemented")
    def test_bind(self):
        """bash: `bind -V` lists readline variable settings on stdout (with
        a 'line editing not enabled' warning on stderr non-interactively).
        psh: command not found, exit 127."""
        assert_bash_parity('bind -V')

    @pytest.mark.xfail(strict=True, reason="compgen builtin is not implemented")
    def test_compgen(self):
        """bash: `compgen -W "foo bar baz" -- b` prints the matching words
        bar/baz, one per line. psh: command not found, exit 127."""
        assert_bash_parity('compgen -W "foo bar baz" -- b')

    @pytest.mark.xfail(strict=True, reason="complete builtin is not implemented")
    def test_complete(self):
        """bash: `complete -W ... cmd` registers a completion spec and
        `complete -p cmd` prints it back (probe: complete -W 'a b' mycmd).
        psh: command not found, exit 127."""
        assert_bash_parity('complete -W "a b" mycmd; complete -p mycmd')

    @pytest.mark.xfail(strict=True, reason="caller builtin is not implemented")
    def test_caller(self):
        """bash: `caller` inside a function prints the call site (probe:
        '1 NULL' for a -c string). psh: command not found, exit 127."""
        assert_bash_parity('f() { caller; }; f')

    # `hash` was implemented 2026-06-13 (Tier B10a); its ledger entry
    # flipped to passing and moved to test_hash_conformance.py.

    @pytest.mark.xfail(strict=True, reason="enable builtin is not implemented")
    def test_enable(self):
        """bash: `enable echo` (re)enables a builtin and returns 0.
        psh: command not found, exit 127."""
        assert_bash_parity('enable echo; echo rc=$?')

    @pytest.mark.xfail(strict=True, reason="exec -a (custom argv[0]) is not implemented")
    def test_exec_dash_a(self):
        """bash: `exec -a customname sh -c 'echo $0'` execs with argv[0]
        replaced (probe: argv0=customname). psh: parses -a as the command
        to exec — 'exec: -a: command not found'."""
        assert_bash_parity('(exec -a customname sh -c "echo argv0=\\$0")')

    @pytest.mark.xfail(strict=True, reason="shopt -s lastpipe is not implemented "
                                           "(shopt rejects the option name honestly)")
    def test_shopt_lastpipe(self):
        """bash: with lastpipe set (and job control off, as in -c mode) the
        last pipeline element runs in the current shell, so
        `echo hi | read x` makes $x visible afterwards (probe: got:hi).
        psh: 'shopt: lastpipe: invalid shell option name' and got: empty —
        a LOUD rejection, not a silent trap."""
        assert_bash_parity('shopt -s lastpipe; echo hi | read x; echo got:$x')

    # `shopt -s failglob` is now IMPLEMENTED (R13.B): a no-match glob fails the
    # command with "no match" on stderr instead of passing the pattern through.
    # Coverage lives in tests/unit/expansion/test_glob_expansion.py
    # (TestGlobOptions.test_failglob_*).

    @pytest.mark.xfail(strict=True, reason=(
        "SILENT TRAP: ${assoc[@]@K} is not implemented and degrades to the "
        "plain values with NO error — scripts using @K get silently wrong "
        "output rather than a failure"))
    def test_assoc_at_K_transform(self):
        """bash: `${a[@]@K}` expands an associative array as quoted
        key-value pairs for re-input (probe: y "2" x "1"). psh: silently
        prints just the values ('1 2') — the @K operator is ignored."""
        assert_bash_parity(
            'declare -A a=([x]=1 [y]=2); printf "%s\\n" "${a[@]@K}"')

    # extglob inside parameter-expansion patterns IS now implemented
    # (the former xfail trap was removed when the prefix-removal bug was
    # fixed). Positive coverage lives in
    # tests/conformance/bash/test_extglob_parameter_expansion_conformance.py.

    @pytest.mark.xfail(strict=True, reason="jobs -x is not implemented")
    def test_jobs_dash_x(self):
        """bash: `jobs -x command args` runs the command with job specs in
        the args replaced by process-group IDs; with no jobspec args it
        simply runs the command (probe: rc=0). psh: 'jobs: -x: invalid
        option', exit 2."""
        assert_bash_parity('jobs -x true; echo rc=$?')

    @pytest.mark.xfail(strict=True, reason="suspend builtin is not implemented")
    def test_suspend_builtin_exists(self):
        """bash: `type suspend` reports a shell builtin (the builtin itself
        SIGSTOPs the shell, so only its existence is probed non-
        interactively). psh: 'type: suspend: not found', exit 1."""
        assert_bash_parity('type suspend; echo rc=$?')

    # `test -v NAME` (variable-is-set) is now IMPLEMENTED in test/[ ] (R13.A,
    # v0.465) — no longer an absent feature. Parity is pinned by
    # tests/unit/builtins/test_test_builtin.py (test_v_variable_is_set / array).

    @pytest.mark.skip(reason=(
        "history expansion (!!, !n, !string) is a documented WONTFIX, not a "
        "pending feature — see docs/reviews/architecture_feature_review_"
        "2026-06-09.md and the xfail-marked tests in tests/integration/"
        "interactive/test_history.py. (Non-interactive bash also disables "
        "histexpand, and psh additionally rejects `set -H`.)"))
    def test_history_expansion_wontfix(self):
        """Placeholder so the ledger lists the decision; never runs."""
        assert_bash_parity('set -H; echo hi; echo !!')
