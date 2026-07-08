"""POSIX-mode special-builtin EXIT-on-error (matrix implementation pins).

Truth table: docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md,
re-derived + extended live against bash 5.2.26 (tmp/posixexit battery,
fix/posix-special-exit campaign). The rule: with ``set -o posix``, a
NON-interactive shell EXITS — later lines never run — when a special
builtin hits a USAGE/SYNTAX error (invalid option, ``return`` at top
level, missing/unreadable ``.``/``source`` file, ``eval``/dot syntax
error, assignment to a readonly via ``readonly``/``export``/bare
assignment) with the builtin's own status; it does NOT exit on
OPERAND/semantic errors (bad identifier, bad signal spec, unset of a
readonly). ``command``/``builtin`` strip the exit; fork boundaries
(subshell, command substitution, pipeline) contain it.

Red→green anchors (FAILED at base a3629202) are marked RED-ON-BASE in
their docstrings; the must-NOT-exit rows are defensive-green
discriminators (already passing on base) unless marked otherwise.
"""
import os
import subprocess
import sys

import pytest

PSH = [sys.executable, "-m", "psh"]


def run_c(script):
    """Run `psh -c script`; return (rc, stdout, stderr)."""
    p = subprocess.run(PSH + ["-c", script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


def run_script(body, tmp_path):
    """Run a multi-line script FILE: next-line survival distinguishes a
    discarded input unit (or plain failure) from a whole-shell exit."""
    path = tmp_path / "s.sh"
    path.write_text(body)
    p = subprocess.run(PSH + [str(path)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30)
    return p.returncode, p.stdout, p.stderr


def run_stdin(body):
    """Pipe a script into psh's stdin (the third non-interactive mode)."""
    p = subprocess.run(PSH, input=body, capture_output=True, text=True,
                       timeout=30)
    return p.returncode, p.stdout, p.stderr


def posix(case):
    return "set -o posix\n" + case + "\necho survived\n"


def default(case):
    return case + "\necho survived\n"


# Matrix rows that EXIT in POSIX mode: (case-lines, exit status).
EXITING_ROWS = [
    ("set -q", 2),
    ("export -q", 2),
    ("readonly -q", 2),
    ("unset -q", 2),
    ("trap -q", 2),
    ("set -o nosuchoption", 2),
    ("exec -q true", 2),
    ("return", 2),
    (". /nonexistent/psh-posixexit-pin", 1),
    ("source /nonexistent/psh-posixexit-pin", 1),
    ("eval 'if'", 2),
    ("eval 'set -q'", 2),
    ("readonly r=1\nreadonly r=2", 1),
    ("readonly r=1\nexport r=2", 1),
    ("readonly r=1\nr=2", 1),
    ("f() { set -q; }\nf", 2),
]

# Matrix rows that must NOT exit in POSIX mode: (case-lines, $? after).
SURVIVING_ROWS = [
    ("export 1bad=x", 1),
    ("readonly 1bad=x", 1),
    ("trap 'x' NOSUCHSIG", 1),
    ("readonly r=1\nunset r", 1),
    ("unset 1bad", 0),
    ("readonly r=1\ndeclare r=2", 1),   # declare is NOT special
    ("unset -f -v x", 1),               # option CONFLICT, not invalid option
    ("( set -q )", 2),                  # fork boundary contains the exit
    ("x=$(set -q)", 2),                 # command substitution contained
    ("set -q | cat", 0),                # pipeline member contained
    ("set -q &\nwait $!", 2),           # background child contained
    ("command set -q", 2),              # command strips the special property
    ("builtin set -q", 2),              # so does builtin
    ("command eval 'if'", 2),           # ... including the eval-syntax exit
    ("command . /nonexistent/psh-posixexit-pin", 1),
    ("shift 5", 1),                     # operand range error, message only
]


class TestPosixExitRows:
    """Every EXIT row: POSIX-mode script exits (no 'survived', exact rc);
    the SAME script in default mode survives. RED-ON-BASE for every row
    (base psh printed 'survived' with rc 0 in posix mode)."""

    @pytest.mark.parametrize("case,status", EXITING_ROWS,
                             ids=[c.replace("\n", ";") for c, _ in EXITING_ROWS])
    def test_posix_exits(self, case, status, tmp_path):
        rc, out, err = run_script(posix(case), tmp_path)
        assert "survived" not in out, (case, out, err)
        assert rc == status, (case, rc, err)

    @pytest.mark.parametrize("case,status", EXITING_ROWS,
                             ids=[c.replace("\n", ";") for c, _ in EXITING_ROWS])
    def test_default_survives(self, case, status, tmp_path):
        rc, out, err = run_script(default(case), tmp_path)
        assert "survived" in out, (case, out, err)
        assert rc == 0, (case, rc, err)


class TestPosixSurvivingRows:
    """Operand/semantic errors and contained/stripped contexts: the
    POSIX-mode shell continues with the documented $? (defensive-green
    discriminators, except the containment rows for set/eval which are
    green only because the EXIT itself is new)."""

    @pytest.mark.parametrize("case,status", SURVIVING_ROWS,
                             ids=[c.replace("\n", ";") for c, _ in SURVIVING_ROWS])
    def test_posix_survives_with_status(self, case, status, tmp_path):
        body = "set -o posix\n" + case + "\necho rc=$?\necho survived\n"
        rc, out, err = run_script(body, tmp_path)
        assert "survived" in out, (case, out, err)
        assert f"rc={status}" in out, (case, out, err)
        assert rc == 0, (case, rc, err)


class TestInputModes:
    """The exit applies in all three non-interactive input modes."""

    def test_c_mode_exits(self):
        """RED-ON-BASE: -c string abandoned with rc 2."""
        rc, out, err = run_c("set -o posix; set -q; echo survived")
        assert out == ""
        assert rc == 2

    def test_stdin_mode_exits(self):
        """RED-ON-BASE: piped stdin abandoned with rc 2."""
        rc, out, err = run_stdin("set -o posix\nset -q\necho survived\n")
        assert out == ""
        assert rc == 2

    def test_c_mode_bare_readonly_assign_exits_rc1(self):
        """Bare `r=2` on a readonly under -c: psh exits rc 1 — consistent
        with its file/stdin status. DELIBERATE divergence: bash's -c mode
        exits 127 here (an internal last_command_exit_value artifact;
        bash file/stdin modes exit 1, which psh matches everywhere).
        Defensive-green on base: the pre-existing TopLevelAbort discard
        already dropped the whole -c unit with rc 1 (the stdin/file
        shapes were the red ones)."""
        rc, out, err = run_c("set -o posix; readonly r=1; r=2; echo survived")
        assert out == ""
        assert rc == 1

    def test_stdin_mode_bare_readonly_assign_exits_rc1(self):
        """RED-ON-BASE; bash stdin mode also exits rc 1."""
        rc, out, err = run_stdin(
            "set -o posix\nreadonly r=1\nr=2\necho survived\n")
        assert out == ""
        assert rc == 1

    def test_mid_script_toggle_off_restores_survival(self):
        """set +o posix after set -o posix: no exit again (bash)."""
        rc, out, err = run_c(
            "set -o posix; set +o posix; set -q; echo rc=$?")
        assert out == "rc=2\n"
        assert rc == 0


class TestBreakContinuePosixSilence:
    """Top-level break/continue: rc-0 no-op in both modes; POSIX mode is
    SILENT where default mode warns (matrix row). RED-ON-BASE (base
    printed the warning in posix mode too)."""

    @pytest.mark.parametrize("word", ["break", "continue"])
    def test_posix_silent_rc0(self, word, tmp_path):
        rc, out, err = run_script(f"set -o posix\n{word}\necho rc=$?\n",
                                  tmp_path)
        assert out == "rc=0\n"
        assert err == ""
        assert rc == 0

    @pytest.mark.parametrize("word", ["break", "continue"])
    def test_default_warns_rc0(self, word, tmp_path):
        rc, out, err = run_script(f"{word}\necho rc=$?\n", tmp_path)
        assert out == "rc=0\n"
        assert "only meaningful in" in err
        assert rc == 0


class TestTooManyArgumentsDiscardFamily:
    """`return 3 4` / `break 1 2` / `continue 1 2` join the delivered
    exit/shift too-many-arguments DISCARD family (bash 5.2 probe): report,
    kill the current input unit, do NOT exit — next line runs with $?=1,
    in BOTH modes. RED-ON-BASE: base psh sys.exit'd the whole script."""

    @pytest.mark.parametrize("mode", ["default", "posix"])
    def test_return_too_many_next_line_runs(self, mode, tmp_path):
        pre = "set -o posix\n" if mode == "posix" else ""
        rc, out, err = run_script(
            pre + "return 3 4; echo same\necho rc=$?\n", tmp_path)
        assert "same" not in out          # rest of the unit dies
        assert out.endswith("rc=1\n")     # next line runs, $? = 1
        assert "too many arguments" in err
        assert rc == 0

    @pytest.mark.parametrize("mode", ["default", "posix"])
    def test_return_too_many_in_function_discards_body(self, mode, tmp_path):
        pre = "set -o posix\n" if mode == "posix" else ""
        rc, out, err = run_script(
            pre + "f() { return 3 4; echo in; }\nf\necho rc=$?\n", tmp_path)
        assert "in" not in out
        assert out.endswith("rc=1\n")
        assert rc == 0

    @pytest.mark.parametrize("word", ["break", "continue"])
    def test_loop_word_too_many_next_line_runs(self, word, tmp_path):
        rc, out, err = run_script(
            f"for i in 1 2; do {word} 1 2; echo in; done\necho rc=$?\n",
            tmp_path)
        assert "in" not in out
        assert out.endswith("rc=1\n")
        assert "too many arguments" in err
        assert rc == 0

    def test_break_non_numeric_still_exits_128(self, tmp_path):
        """Discriminator: `break x` inside a loop remains a HARD exit 128
        (bash, both modes) — only too-many-args joined the discard."""
        rc, out, err = run_script(
            "for i in 1 2; do break x; done\necho survived\n", tmp_path)
        assert "survived" not in out
        assert rc == 128
        assert "numeric argument required" in err


class TestTrapOptionParsing:
    """bash rejects any leading dash word that is not -/--/-l/-p as an
    invalid option (the action must be protected by --). RED-ON-BASE:
    base psh accepted `trap '-echo hi' INT` as an action (rc 0)."""

    def test_dash_action_without_ddash_is_invalid_option(self):
        rc, out, err = run_c("trap '-echo hi' INT; echo rc=$?")
        assert out == "rc=2\n"
        assert "-e: invalid option" in err
        assert "usage: trap" in err

    def test_trap_q_reports_invalid_option(self):
        """Base printed only the usage line; bash names the option first."""
        rc, out, err = run_c("trap -q; echo rc=$?")
        assert out == "rc=2\n"
        assert "-q: invalid option" in err

    def test_ddash_protected_dash_action_still_works(self):
        rc, out, err = run_c("trap -- '-echo hi' INT; trap -p INT")
        assert rc == 0
        assert out == "trap -- '-echo hi' SIGINT\n"

    def test_reset_dash_still_works(self):
        rc, out, err = run_c("trap 'echo x' INT; trap - INT; trap -p INT; echo rc=$?")
        assert rc == 0
        assert out == "rc=0\n"

    def test_single_nonsignal_operand_posix_exits(self, tmp_path):
        """`trap foo`: usage error rc 2 (bash) — exits in POSIX mode.
        RED-ON-BASE for the posix exit."""
        rc, out, err = run_script(posix("trap foo"), tmp_path)
        assert "survived" not in out
        assert rc == 2


class TestShiftPosixRangeMessage:
    """bash is silent on an out-of-range shift in default mode but reports
    it in POSIX mode (rc 1 both, never exits). RED-ON-BASE for the
    message rows."""

    def test_posix_count_message(self, tmp_path):
        rc, out, err = run_script("set -o posix\nshift 5\necho rc=$?\n",
                                  tmp_path)
        assert out == "rc=1\n"
        assert "shift: 5: shift count out of range" in err

    def test_posix_bare_shift_message_has_no_count(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\nset --\nshift\necho rc=$?\n", tmp_path)
        assert out == "rc=1\n"
        assert "shift: shift count out of range" in err

    def test_default_stays_silent(self, tmp_path):
        rc, out, err = run_script("shift 5\necho rc=$?\n", tmp_path)
        assert out == "rc=1\n"
        assert err == ""


class TestSyntaxErrorExits:
    """POSIX-mode fatal syntax errors: eval'd strings and sourced files
    exit the shell; the trap-action string itself is exempt; unclosed
    quotes are exempt (all probe-pinned to bash 5.2)."""

    def test_sourced_file_syntax_posix_exits(self, tmp_path):
        """RED-ON-BASE."""
        aux = tmp_path / "aux.sh"
        aux.write_text("if\n")
        rc, out, err = run_script(posix(f". {aux}"), tmp_path)
        assert "survived" not in out
        assert rc == 2

    def test_sourced_file_syntax_default_survives(self, tmp_path):
        aux = tmp_path / "aux.sh"
        aux.write_text("if\n")
        rc, out, err = run_script(f". {aux}\necho rc=$?\n", tmp_path)
        assert out == "rc=2\n"
        assert rc == 0

    def test_trap_action_own_syntax_error_is_exempt(self, tmp_path):
        """bash does NOT exit when the trap ACTION string fails to parse."""
        rc, out, err = run_script(
            "set -o posix\ntrap 'if' USR1\nkill -USR1 $$\necho s=$?\n",
            tmp_path)
        assert "s=0" in out
        assert rc == 0

    def test_eval_nested_in_trap_action_exits(self, tmp_path):
        """... but an eval INSIDE the action is fresh input and exits."""
        rc, out, err = run_script(
            "set -o posix\ntrap \"eval 'if'\" USR1\nkill -USR1 $$\necho s=$?\n",
            tmp_path)
        assert "s=" not in out
        assert rc == 2

    def test_special_builtin_error_inside_trap_action_exits(self, tmp_path):
        """The trap exemption covers ONLY the action's parse: a special
        builtin usage error inside the action still exits (bash)."""
        rc, out, err = run_script(
            "set -o posix\ntrap 'set -q' USR1\nkill -USR1 $$\necho s=$?\n",
            tmp_path)
        assert "s=" not in out
        assert rc == 2

    def test_eval_unclosed_quote_is_exempt(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\neval 'echo \"x'\necho s=$?\n", tmp_path)
        assert "s=2" in out
        assert rc == 0

    def test_cmdsub_syntax_contained(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\nx=$(eval 'if')\necho s=$?\n", tmp_path)
        assert "s=2" in out
        assert rc == 0


class TestDotFileClassification:
    """dot/source file errors: missing and unreadable exit in POSIX mode;
    a directory does not (bash probe)."""

    def test_unreadable_file_posix_exits(self, tmp_path):
        target = tmp_path / "noread.sh"
        target.write_text("echo inner\n")
        os.chmod(target, 0)
        try:
            rc, out, err = run_script(posix(f". {target}"), tmp_path)
        finally:
            os.chmod(target, 0o644)
        assert "survived" not in out
        assert rc == 1

    def test_directory_posix_survives(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\n. /\necho rc=$?\n", tmp_path)
        assert out == "rc=1\n"
        assert rc == 0


class TestPrefixAssignmentPosix:
    """`readonly r=1; r=2 cmd` in POSIX mode: the command does NOT run and
    the status is 1; a SPECIAL builtin as the command exits the shell
    rc 1. Default mode reports and RUNS the command (unchanged).
    RED-ON-BASE for the posix rows."""

    def test_posix_nonspecial_not_run_rc1(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\nreadonly r=1\nr=2 echo RAN\necho s=$?\n", tmp_path)
        assert "RAN" not in out
        assert "s=1" in out
        assert rc == 0

    def test_posix_nonspecial_discards_rest_of_line(self, tmp_path):
        """The non-special prefix error is a unit DISCARD like a pure
        readonly assignment: the same-line tail dies, the next line runs
        (bash probe; an `if r=2 cmd; then` runs neither branch)."""
        rc, out, err = run_script(
            "set -o posix\nreadonly r=1\nr=2 echo RAN; echo same=$?\n"
            "echo next=$?\n", tmp_path)
        assert "same=" not in out
        assert out == "next=1\n"
        assert rc == 0

    def test_posix_function_not_run_rc1(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\nf() { echo in; }\nreadonly r=1\nr=2 f\necho s=$?\n",
            tmp_path)
        assert "in" not in out
        assert "s=1" in out
        assert rc == 0

    def test_posix_special_builtin_exits(self, tmp_path):
        rc, out, err = run_script(
            "set -o posix\nreadonly r=1\nr=2 :\necho s=$?\n", tmp_path)
        assert "s=" not in out
        assert rc == 1

    def test_default_command_still_runs(self, tmp_path):
        rc, out, err = run_script(
            "readonly r=1\nr=2 echo RAN\necho s=$?\n", tmp_path)
        assert "RAN" in out
        assert "s=0" in out
        assert rc == 0
