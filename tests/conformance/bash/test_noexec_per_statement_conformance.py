"""Conformance: `set -n` (noexec) is re-read per STATEMENT, not per input unit.

C040 (Improvement Program 2026-09, slot 1.10). psh consulted noexec once per
input unit, before execution, so a flag flipped mid-unit was never re-read:

    psh -c 'echo before; set -n; touch marker; echo after'

ran ``touch`` and ``echo after``; bash prints only ``before``. bash checks the
flag at the top of every command it is about to execute, so everything after
``set -n`` on the same input is read but not run — in ``-c``, in a script file
and on stdin alike.

Every row asserts the ACTUAL target rather than a return code: the command that
must not run is ``touch marker``, and the pin asserts the FILE is absent (D3).
The shell's own exit status is asserted too — a skipped command contributes
success, so ``set -n; false`` and ``set -n; exit 7`` both leave 0.

Interactive shells are the complement and are pinned at a real terminal in
tests/system/interactive/test_noexec_interactive_pty.py: bash refuses to turn
noexec on at a prompt at all.
"""
import os

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

MODES = ("dash_c", "script", "stdin")


def _run(runner, script, cwd, mode):
    """Run *script* in one of the three input modes, in *cwd*."""
    if mode == "dash_c":
        result = runner(["-c", script], cwd=cwd)
    elif mode == "script":
        path = os.path.join(cwd, "case.sh")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(script + "\n")
        result = runner([path], cwd=cwd)
    else:
        result = runner([], stdin_data=script + "\n", stdin_mode="pipe",
                        cwd=cwd)
    assert is_comparable(result), result
    return result


# (id, script) — every script would create ./marker if the statements after
# `set -n` ran, and echoes `after` if the tail of the list is reached.
_ROWS = [
    ("same_line", "echo before; set -n; touch marker; echo after"),
    ("set_o_noexec", "echo before; set -o noexec; touch marker; echo after"),
    ("shopt_so_noexec",
     "echo before; shopt -so noexec; touch marker; echo after"),
    # bash never reaches the `set +n`, because that command is skipped too.
    ("set_plus_n_unreachable",
     "echo before; set -n; set +n; touch marker; echo after"),
    ("inside_function_body",
     "f() { set -n; touch marker; }; echo before; f; echo after"),
    ("function_called_after",
     "f() { touch marker; echo infunc; }; echo before; set -n; f; echo after"),
    ("eval_after", "echo before; set -n; eval 'touch marker; echo ineval'; "
                   "echo after"),
    ("source_after", "echo before; set -n; . ./inc.sh; echo after"),
    ("if_after", "echo before; set -n; if true; then touch marker; fi; "
                 "echo after"),
    ("for_after", "echo before; set -n; for i in 1 2; do touch marker; done; "
                  "echo after"),
    ("while_after", "echo before; set -n; while true; do touch marker; break; "
                    "done; echo after"),
    ("pipeline_after", "echo before; set -n; touch marker | cat; echo after"),
    ("subshell_after", "echo before; set -n; (touch marker); echo after"),
    ("brace_group_after", "echo before; set -n; { touch marker; }; echo after"),
    ("background_after", "echo before; set -n; touch marker & wait; "
                         "echo after"),
    ("and_or_after", "echo before; set -n; true && touch marker; echo after"),
    ("assignment_after", "echo before; set -n; x=1; echo x=$x; touch marker"),
    # A trap installed BEFORE the flag: its action is read but not executed.
    ("exit_trap_after",
     "trap 'touch marker; echo intrap' EXIT; echo before; set -n; echo after"),
    # A skipped command contributes SUCCESS: neither `false` nor `exit 7`
    # can change the shell's exit status once noexec is on.
    ("false_after", "echo before; set -n; false"),
    ("exit_after", "echo before; set -n; exit 7"),
    # `set -n` inside a SUBSHELL is local to it: the parent runs on, but the
    # subshell's own tail is skipped.
    ("subshell_local", "echo before; (set -n; touch marker); echo after"),
    # The flag is local to a command substitution too — the substitution's
    # own tail is skipped, so it expands to nothing.
    ("command_substitution_local",
     "x=$(set -n; echo hi); echo \"[$x]\"; echo tail"),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case_id,script", _ROWS, ids=[r[0] for r in _ROWS])
def test_noexec_stops_the_rest_of_the_input(case_id, script, mode, tmp_path):
    bash_dir = tmp_path / f"bash-{case_id}-{mode}"
    psh_dir = tmp_path / f"psh-{case_id}-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    # D3: the pin's target is the FILE the skipped command would have made,
    # not merely a status. Both sides are asserted, so an improvement in bash
    # fails this pin instead of passing unnoticed.
    bash_marker = (bash_dir / "marker").exists()
    psh_marker = (psh_dir / "marker").exists()
    assert psh_marker == bash_marker, (
        f"{case_id}/{mode}: marker bash={bash_marker} psh={psh_marker}")
    assert not psh_marker, f"{case_id}/{mode}: the skipped command ran"

    assert psh.stdout == bash.stdout, (
        f"{case_id}/{mode}: bash={bash.stdout!r} psh={psh.stdout!r}")
    assert psh.returncode == bash.returncode, (
        f"{case_id}/{mode}: bash rc={bash.returncode} psh rc={psh.returncode}")


def test_the_user_guide_noexec_claim(tmp_path):
    """The headline repro in one asserting test — the evidence the user guide's
    `set -o noexec` "Full support" row is mapped to
    (tests/conformance/test_claims_have_tests.py)."""
    script = "echo before; set -n; touch marker; echo after"
    bash_dir = tmp_path / "bash"
    psh_dir = tmp_path / "psh"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), "dash_c")
    psh = _run(run_psh, script, str(psh_dir), "dash_c")

    assert not (bash_dir / "marker").exists()
    assert not (psh_dir / "marker").exists()
    assert psh.stdout == bash.stdout == "before\n"
    assert psh.returncode == bash.returncode == 0


@pytest.mark.parametrize("mode", MODES)
def test_syntax_errors_are_still_reported_under_noexec(mode, tmp_path):
    """The control: noexec means READ but do not execute. A later syntax
    error is still found and still exits 2, and nothing before it ran."""
    script = "echo before\nset -n\ntouch marker\nif;\necho after"
    bash_dir = tmp_path / f"bash-syn-{mode}"
    psh_dir = tmp_path / f"psh-syn-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    assert not (bash_dir / "marker").exists()
    assert not (psh_dir / "marker").exists()
    assert psh.stdout == bash.stdout == "before\n"
    assert psh.returncode == bash.returncode == 2
    assert psh.stderr.strip(), "psh reported no syntax error"


@pytest.mark.parametrize("mode", MODES)
def test_noexec_flag_on_the_command_line_runs_nothing(mode, tmp_path):
    """The other control: the `-n` FLAG (not a runtime `set -n`) already
    matched bash, and still does — including that a runtime `set +n` cannot
    turn it back off, because that command is skipped like every other."""
    bash_dir = tmp_path / f"bash-flag-{mode}"
    psh_dir = tmp_path / f"psh-flag-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()
    script = "set +n; touch marker; echo after"

    if mode == "dash_c":
        bash = run_bash(["-n", "-c", script], cwd=str(bash_dir))
        psh = run_psh(["-n", "-c", script], cwd=str(psh_dir))
    elif mode == "script":
        for directory in (bash_dir, psh_dir):
            (directory / "case.sh").write_text(script + "\n")
        bash = run_bash(["-n", str(bash_dir / "case.sh")], cwd=str(bash_dir))
        psh = run_psh(["-n", str(psh_dir / "case.sh")], cwd=str(psh_dir))
    else:
        bash = run_bash(["-n"], stdin_data=script + "\n", stdin_mode="pipe",
                        cwd=str(bash_dir))
        psh = run_psh(["-n"], stdin_data=script + "\n", stdin_mode="pipe",
                      cwd=str(psh_dir))

    assert is_comparable(bash) and is_comparable(psh)
    assert not (bash_dir / "marker").exists()
    assert not (psh_dir / "marker").exists()
    assert psh.stdout == bash.stdout == ""
    assert psh.returncode == bash.returncode == 0
