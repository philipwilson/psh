"""`trap` option-flag handling (getopt over "lp").

`trap` accepts the flags -l (list signals) and -p (print traps) getopt-style:
they cluster (`-lp`, `-pl`, doubled `-ll`/`-pp`) and may be split across words
(`-p -l`), with `-l` dominating when present. Before this fix psh matched only
the exact words `-l`/`-p`, so every cluster was rejected as an invalid option
and `trap -p -l` mis-parsed `-l` as a signal spec. A bad flag char reports the
CHAR (bash: `trap -lx` -> "-x: invalid option"), not the whole cluster.
Probe-pinned vs bash 5.2 (the `bash: line N:` stderr prefix is a separate,
systemic divergence — task #35 — so stderr is compared by content, not prefix).
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
        assert "usage: trap [-lp] [[arg] signal_spec ...]" in err
        # No signal listing leaked to stdout on the error path.
        assert captured_shell.get_stdout() == ""
