"""Startup-ordering pins: rc runs only AFTER the full invocation (F1).

Continuation finding A's four probe classes, each demonstrated red on base
992787a9 (tmp/boundary-ledgers/F1-probes/base-battery.txt):

a. rc-sees-options    — under ``--rcfile rc -u -i -s`` the rc observes ``u``
                        in ``$-`` (base: only the body did);
b. rc-sees-parser     — under ``--parser combinator`` the rc's
                        ``parser-select`` marks combinator active (base: rd);
c. rc-sees-positionals— under ``-i -s A B`` the rc sees ``$1 $2`` (base: 0);
d. invalid-parser     — ``--parser bogus`` exits 2 BEFORE the rc runs
                        (base: the rc ran first, touch-file proof).

Plus the ordering/status corollaries probed alongside (rc before body, rc's
``$?`` visible to the body, rc lines never bang-expanded) and bash's analog
for class d (an invalid long option exits 2 without running the rc).
"""
import sys
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, run_shell_case, try_resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
_ORACLE = try_resolve_bash()


def run_psh(args, *, stdin=None, cwd, extra_env=None):
    env = hermetic_shell_env({"PYTHONPATH": str(REPO_ROOT),
                              "HISTFILE": str(Path(cwd) / ".histfile"),
                              **(extra_env or {})})
    result = run_shell_case([sys.executable, "-m", "psh", *args],
                            stdin_data=stdin, env=env, cwd=str(cwd), timeout=30)
    assert isinstance(result, Completed), result
    return result


def run_bash(args, *, stdin=None, cwd):
    assert _ORACLE is not None
    env = hermetic_shell_env({"HISTFILE": str(Path(cwd) / ".histfile")})
    result = run_shell_case([_ORACLE.path, *args], stdin_data=stdin, env=env,
                            cwd=str(cwd), timeout=30)
    assert isinstance(result, Completed), result
    return result


class TestRcSeesOptions:
    """Probe class a: the rc observes CLI set-options."""

    def test_rc_sees_set_u(self, tmp_path):
        (tmp_path / "rc").write_text("echo rc:$-\n")
        result = run_psh(["--rcfile", "rc", "-u", "-i", "-s"],
                         stdin="echo body:$-\n", cwd=tmp_path)
        assert result.returncode == 0
        rc_line, body_line = result.stdout.splitlines()
        assert rc_line.startswith("rc:") and "u" in rc_line
        assert body_line.startswith("body:") and "u" in body_line
        # rc and body observe the SAME flag set — no half-configured window.
        assert rc_line.removeprefix("rc:") == body_line.removeprefix("body:")

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_sees_set_u_matches_bash(self, tmp_path):
        (tmp_path / "rc").write_text("echo rc:$-\n")
        psh = run_psh(["--rcfile", "rc", "-u", "-i", "-s"],
                      stdin="echo body:$-\n", cwd=tmp_path)
        bash = run_bash(["--rcfile", "rc", "-u", "-i", "-s"],
                        stdin="echo body:$-\n", cwd=tmp_path)
        assert psh.stdout == bash.stdout  # rc:hiuBHs / body:hiuBHs
        assert psh.returncode == bash.returncode == 0

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_sees_cluster_option_with_dash_c(self, tmp_path):
        # E11: `-uic 'cmd'` — the rc under -ic sees u AND i AND c.
        (tmp_path / "rc").write_text("echo rc:$-\n")
        psh = run_psh(["--rcfile", "rc", "-uic", "echo body:$-"], cwd=tmp_path)
        bash = run_bash(["--rcfile", "rc", "-uic", "echo body:$-"], cwd=tmp_path)
        assert psh.stdout == bash.stdout  # rc:hiuBHc / body:hiuBHc
        assert psh.returncode == bash.returncode == 0


class TestRcSeesParser:
    """Probe class b (psh-only): the rc observes --parser."""

    def test_rc_reports_combinator_active(self, tmp_path):
        (tmp_path / "rc").write_text("parser-select\n")
        result = run_psh(["--rcfile", "rc", "--parser", "combinator",
                          "-i", "-s"],
                         stdin="parser-select\n", cwd=tmp_path)
        assert result.returncode == 0
        lines = result.stdout.splitlines()
        rc_view, body_view = lines[:2], lines[2:]
        assert any(ln.lstrip().startswith("*") and "combinator" in ln
                   for ln in rc_view), (
            f"rc did not see the combinator parser active: {rc_view}")
        assert rc_view == body_view


class TestRcSeesPositionals:
    """Probe class c: the rc observes -s positional parameters."""

    def test_rc_sees_positionals(self, tmp_path):
        (tmp_path / "rc").write_text('echo rc:$#:${1-none}:${2-none}\n')
        result = run_psh(["--rcfile", "rc", "-i", "-s", "A", "B"],
                         stdin='echo body:$#:${1-none}:${2-none}\n',
                         cwd=tmp_path)
        assert result.returncode == 0
        assert result.stdout == "rc:2:A:B\nbody:2:A:B\n"

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_sees_positionals_matches_bash(self, tmp_path):
        (tmp_path / "rc").write_text('echo rc:$#:${1-none}:${2-none}\n')
        args = ["--rcfile", "rc", "-i", "-s", "A", "B"]
        stdin = 'echo body:$#:${1-none}:${2-none}\n'
        psh = run_psh(args, stdin=stdin, cwd=tmp_path)
        bash = run_bash(args, stdin=stdin, cwd=tmp_path)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode == 0


class TestInvalidParserBeforeRc:
    """Probe class d: invalid parser exits 2 with NO rc execution."""

    def test_invalid_parser_exits_2_without_running_rc(self, tmp_path):
        (tmp_path / "rc").write_text("echo RCRAN\ntouch rc_marker\n")
        result = run_psh(["--rcfile", "rc", "--parser", "bogus", "-i", "-s"],
                         stdin="echo body\n", cwd=tmp_path)
        assert result.returncode == 2
        assert result.stdout == ""            # neither rc nor body ran
        assert "unknown parser: bogus" in result.stderr
        assert not (tmp_path / "rc_marker").exists(), (
            "the rc file executed before the invalid-parser exit")

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_invalid_long_option_exits_2_without_rc_like_bash(self, tmp_path):
        (tmp_path / "rc").write_text("echo RCRAN\ntouch rc_marker\n")
        args = ["--rcfile", "rc", "--bogus-option", "-i", "-s"]
        psh = run_psh(args, stdin="echo body\n", cwd=tmp_path)
        bash = run_bash(args, stdin="echo body\n", cwd=tmp_path)
        assert psh.returncode == bash.returncode == 2
        assert psh.stdout == bash.stdout == ""
        assert not (tmp_path / "rc_marker").exists()


class TestRcOrderingCorollaries:
    """rc runs before the body, its $? is visible, and it never bang-expands."""

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_output_precedes_command_body(self, tmp_path):
        (tmp_path / "rc").write_text("echo FIRST\n")
        args = ["--rcfile", "rc", "-ic", "echo body"]
        psh = run_psh(args, cwd=tmp_path)
        bash = run_bash(args, cwd=tmp_path)
        assert psh.stdout == bash.stdout == "FIRST\nbody\n"

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_output_precedes_script_body(self, tmp_path):
        (tmp_path / "rc").write_text("echo FIRST\n")
        (tmp_path / "s.sh").write_text("echo SECOND\n")
        args = ["--rcfile", "rc", "-i", "s.sh"]
        psh = run_psh(args, cwd=tmp_path)
        bash = run_bash(args, cwd=tmp_path)
        assert psh.stdout == bash.stdout == "FIRST\nSECOND\n"

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_exit_status_visible_to_body(self, tmp_path):
        (tmp_path / "rc").write_text("false\n")
        args = ["--rcfile", "rc", "-ic", "echo rc=$?"]
        psh = run_psh(args, cwd=tmp_path)
        bash = run_bash(args, cwd=tmp_path)
        assert psh.stdout == bash.stdout == "rc=1\n"
        assert psh.returncode == bash.returncode == 0

    @pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")
    def test_rc_lines_are_never_bang_expanded(self, tmp_path):
        # bash keeps `!!` literal in rc files even for -i shells.
        (tmp_path / "rc").write_text("echo RCA\necho rc:!!\n")
        args = ["--rcfile", "rc", "-i", "-s"]
        psh = run_psh(args, stdin="echo body\n", cwd=tmp_path)
        bash = run_bash(args, stdin="echo body\n", cwd=tmp_path)
        assert psh.stdout == bash.stdout == "RCA\nrc:!!\nbody\n"


class TestConstructionPurity:
    """Shell construction reads no startup input; startup is explicit."""

    def test_construction_does_not_load_rc_or_history(self, tmp_path):
        # In-process: construct an interactive-family Shell (one that WILL
        # source rc and history at startup) pointing at a marker-writing rc
        # and a canary history file; NOTHING may be read until the explicit
        # startup step, which then reads both exactly once.
        marker = tmp_path / "marker"
        rc = tmp_path / "rc"
        rc.write_text(f"echo ran >> {marker}\n")
        hist = tmp_path / "hist"
        hist.write_text("echo canary\n")

        import os
        old_histfile = os.environ.get("HISTFILE")
        os.environ["HISTFILE"] = str(hist)
        try:
            from psh.shell import Shell
            shell = Shell(rcfile=str(rc), force_interactive=True)
            try:
                assert not marker.exists(), "construction ran the rc file"
                assert shell.state.history == [], (
                    "construction loaded the history file")

                shell.run_invocation_startup()
                assert marker.read_text() == "ran\n"
                assert shell.state.history == ["echo canary"]

                # Idempotent: a second call must not re-run either.
                shell.run_invocation_startup()
                assert marker.read_text() == "ran\n"
                assert shell.state.history == ["echo canary"]
            finally:
                shell.close()
        finally:
            if old_histfile is None:
                os.environ.pop("HISTFILE", None)
            else:
                os.environ["HISTFILE"] = old_histfile

    def test_for_subshell_never_repeats_startup(self, tmp_path):
        marker = tmp_path / "marker"
        rc = tmp_path / "rc"
        rc.write_text(f"echo ran >> {marker}\n")
        from psh.shell import Shell
        parent = Shell(rcfile=str(rc))
        try:
            child = Shell.for_subshell(parent)
            try:
                # The child is born with startup already marked done: even an
                # explicit call must be a no-op.
                child.run_invocation_startup()
                assert not marker.exists()
            finally:
                child.close()
        finally:
            parent.close()
