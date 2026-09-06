"""`trap` option-flag handling (getopt over "lpP").

`trap` accepts the flags -l (list signals), -p (print traps) and -P (print
bare actions; bash 5.3 CHANGES, 5.3-alpha "New Features in Bash" item j)
getopt-style: they cluster (`-lp`, `-pl`, doubled `-ll`/`-pp`) and may be
split across words (`-p -l`), with `-l` dominating when present. Before this
fix psh matched only the exact words `-l`/`-p`, so every cluster was rejected
as an invalid option and `trap -p -l` mis-parsed `-l` as a signal spec. A bad
flag char reports the CHAR (bash: `trap -lx` -> "-x: invalid option"), not the
whole cluster. Probe-pinned vs bash 5.3.15 (the `bash: line N:` stderr prefix
is a separate, systemic divergence — task #35 — so stderr is compared by
content, not prefix).
"""

import pytest


def _out(captured_shell, cmd):
    """Run one command and return its stdout, clearing capture first."""
    captured_shell.clear_output()
    rc = captured_shell.run_command(cmd)
    return rc, captured_shell.get_stdout()


class TestTrapListPrintFlags:
    """-l dominates; clusters and split words parse like bash."""

    def test_l_alone_lists_signals(self, captured_shell):
        rc, out = _out(captured_shell, "trap -l")
        assert rc == 0
        assert "SIGINT" in out and "SIGTERM" in out

    @pytest.mark.parametrize("flags", ["-lp", "-pl", "-ll", "-l -p", "-p -l"])
    def test_l_dominates_lists_signals(self, captured_shell, flags):
        """Any parse containing -l prints the signal list (ignores -p),
        identical to bare `trap -l`, even with a trap set."""
        _, listing = _out(captured_shell, "trap -l")
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, f"trap {flags}")
        assert rc == 0
        assert out == listing

    def test_pp_doubled_shows_traps_like_p(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT")
        _, single = _out(captured_shell, "trap -p")
        rc, doubled = _out(captured_shell, "trap -pp")
        assert rc == 0
        assert doubled == single
        assert "SIGINT" in doubled

    def test_p_l_split_is_not_invalid_signal(self, captured_shell):
        """Regression: `trap -p -l` used to treat `-l` as a signal spec and
        fail with 'invalid signal specification' rc 1."""
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, "trap -p -l")
        assert rc == 0
        assert "SIGINT" in out  # it is the -l signal listing


class TestTrapBadOption:
    """A bad flag char is reported by CHAR with the usage line, rc 2."""

    @pytest.mark.parametrize("cmd,char", [
        ("trap -lx", "-x"),   # valid l, then invalid x
        ("trap -px", "-x"),   # valid p, then invalid x
        ("trap -pq", "-q"),   # valid p, then invalid q
        ("trap -x", "-x"),
    ])
    def test_reports_offending_char(self, captured_shell, cmd, char):
        captured_shell.clear_output()
        rc = captured_shell.run_command(cmd)
        assert rc == 2
        err = captured_shell.get_stderr()
        assert f"trap: {char}: invalid option" in err
        # bash 5.3's usage line (5.2 printed `[-lp] [[arg] ...`).
        assert "usage: trap [-Plp] [[action] signal_spec ...]" in err
        # No signal listing leaked to stdout on the error path.
        assert captured_shell.get_stdout() == ""


class TestTrapPrintActions:
    """`trap -P SIG...` prints each operand's BARE action.

    bash 5.3 CHANGES, 5.3-alpha "New Features in Bash" item j: "`trap' has a
    new -P option that prints the trap action associated with each signal
    argument". Every expectation below is the bash 5.3.15 probe (Wave 0.2;
    the usage-line gate nodes are test_error_prefix_conformance x3 and
    test_trap_signal_spec_conformance::test_single_invalid_operand_usage_error).
    """

    def test_P_prints_bare_action(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == "echo hi\n"
        assert captured_shell.get_stderr() == ""

    def test_P_action_is_not_requoted(self, captured_shell):
        # -p re-quotes for reuse (`trap -- 'echo '\''x'\''' SIGINT`);
        # -P prints the action text as stored.
        captured_shell.run_command('trap "echo \'x\'" INT')
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == "echo 'x'\n"

    def test_P_multiline_action_prints_verbatim(self, captured_shell):
        captured_shell.run_command("trap 'echo a\necho b' INT")
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == "echo a\necho b\n"

    def test_P_unset_signal_prints_nothing(self, captured_shell):
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == ""
        assert captured_shell.get_stderr() == ""

    def test_P_reset_signal_prints_nothing(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT; trap - INT")
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == ""

    def test_P_ignored_signal_prints_empty_line(self, captured_shell):
        # The ignored ('') action is an empty line, unlike an unset one.
        captured_shell.run_command("trap '' INT")
        rc, out = _out(captured_shell, 'trap -P INT')
        assert rc == 0
        assert out == "\n"

    def test_P_one_line_per_operand_in_operand_order(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT; trap 'echo bye' EXIT")
        rc, out = _out(captured_shell, 'trap -P INT EXIT')
        assert rc == 0
        assert out == "echo hi\necho bye\n"
        rc, out = _out(captured_shell, 'trap -P EXIT INT')
        assert out == "echo bye\necho hi\n"

    def test_P_repeats_duplicate_operands(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, 'trap -P 2 SIGINT int')
        assert rc == 0
        assert out == "echo hi\necho hi\necho hi\n"

    def test_P_zero_is_the_exit_trap(self, captured_shell):
        captured_shell.run_command("trap 'echo z' 0")
        rc, out = _out(captured_shell, 'trap -P 0 EXIT')
        assert rc == 0
        assert out == "echo z\necho z\n"

    def test_P_pseudo_signals(self, captured_shell):
        # ERR/RETURN here rather than DEBUG: a DEBUG trap fires for the query
        # command itself, and in-process capture then misses the listing (a
        # captured_shell artefact — the subprocess probe matches bash:
        # `a\na\necho a\necho b`).
        captured_shell.run_command("trap 'echo a' ERR; trap 'echo b' RETURN")
        rc, out = _out(captured_shell, 'trap -P ERR RETURN')
        assert rc == 0
        assert out == "echo a\necho b\n"

    def test_help_advertises_P(self, captured_shell):
        rc, out = _out(captured_shell, 'help trap')
        assert rc == 0
        assert 'trap -P condition...' in out
        assert '\n    -P      ' in out

    def test_P_invalid_spec_reports_and_continues(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, 'trap -P INT NOSUCH')
        assert rc == 1
        assert out == "echo hi\n"  # the valid operand is still printed
        assert ('trap: NOSUCH: invalid signal specification'
                in captured_shell.get_stderr())

    def test_P_empty_spec_is_invalid(self, captured_shell):
        rc, out = _out(captured_shell, 'trap -P ""')
        assert rc == 1
        assert out == ""
        assert 'trap: : invalid signal specification' in captured_shell.get_stderr()

    def test_P_without_operand_is_a_usage_error(self, captured_shell):
        rc, out = _out(captured_shell, 'trap -P')
        assert rc == 2
        assert out == ""
        err = captured_shell.get_stderr()
        assert 'trap: -P requires at least one signal name' in err
        assert 'usage:' not in err  # bash prints no usage line for this one

    def test_P_after_double_dash_still_needs_an_operand(self, captured_shell):
        rc, out = _out(captured_shell, 'trap -P --')
        assert rc == 2
        assert ('trap: -P requires at least one signal name'
                in captured_shell.get_stderr())

    @pytest.mark.parametrize("cmd", ['trap -p -P INT', 'trap -pP INT',
                                     'trap -Pp INT'])
    def test_p_and_P_together_is_a_usage_error(self, captured_shell, cmd):
        rc, out = _out(captured_shell, cmd)
        assert rc == 2
        assert out == ""
        err = captured_shell.get_stderr()
        assert 'trap: cannot specify both -p and -P' in err
        assert 'usage:' not in err

    @pytest.mark.parametrize("cmd", ['trap -lP INT', 'trap -Pl INT'])
    def test_l_dominates_P(self, captured_shell, cmd):
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, cmd)
        assert rc == 0
        assert 'SIGINT' in out and 'echo hi' not in out

    def test_double_dash_then_operand(self, captured_shell):
        captured_shell.run_command("trap 'echo hi' INT")
        rc, out = _out(captured_shell, 'trap -P -- INT')
        assert rc == 0
        assert out == "echo hi\n"

    @pytest.mark.parametrize("cmd", ['trap -P', 'trap -pP INT'])
    def test_P_usage_errors_exit_a_posix_shell_suppressibly(self, captured_shell,
                                                           cmd):
        # Special-builtin usage error: a POSIX-mode non-interactive shell
        # exits (rc 2) unless a `||` guard suppresses it — like `trap -x`.
        captured_shell.run_command('set -o posix')
        rc, out = _out(captured_shell, f'{cmd} || echo caught; echo survived')
        assert out == "caught\nsurvived\n"
