"""Conformance: a command that runs no program still reports a status.

C041 (Improvement Program 2026-09, slot 1.10). A bare command substitution left
``$?`` untouched:

    psh -c '$(exit 5); echo rc=$?'   # printed rc=0; bash prints rc=5

When a simple command's words expand to ZERO fields it is still a command —
bash calls it the null command. Its redirections are performed and its status
is the exit status of the LAST command substitution run while expanding it,
unless a redirection targeted fd 0, which bash performs in a forked child whose
success erases that status. psh's one rule lives in
``psh/executor/null_command.py``; these rows pin it against bash 5.3.15 in all
three input modes.

The fd-0 clause is EMPIRICAL against bash 5.3.15 — it is a consequence of
``execute_null_command``'s fork, with no CHANGES entry — so the rows that
depend on it (``< f``, ``<<EOF``, ``<<< z``, ``{v}> f``) are pinned on BOTH
sides: an improvement on the bash side fails this file rather than passing.
"""
import os

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

MODES = ("dash_c", "script", "stdin")

#: Every case creates ./z.txt first, so the input-redirect rows have a file.
_PRELUDE = "echo z > z.txt; "


def _run(runner, script, cwd, mode):
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


# (id, script) — each ends by printing the status the rule decides.
_ROWS = [
    # --- clause 3: the last command substitution wins -------------------
    ("bare", '$(exit 5); echo rc=$?'),
    ("backticks", '`exit 7`; echo rc=$?'),
    ("nested", '$(exit $(echo 4)); echo rc=$?'),
    ("nested_inner_only", '$( $(exit 9) ); echo rc=$?'),
    ("backtick_inside_dollar", '$(`exit 4`); echo rc=$?'),
    ("substitution_with_output", '$(echo; exit 3); echo rc=$?'),
    ("two_substitutions_last_wins", '$(exit 5) $(exit 6); echo rc=$?'),
    ("whitespace_word_then_sub", 'x="  "; $x $(exit 4); echo rc=$?'),
    ("empty_var_then_sub", 'false; ${nope} $(exit 2); echo rc=$?'),
    ("in_function_body", 'f() { $(exit 5); }; f; echo rc=$?'),
    ("in_brace_group", '{ $(exit 5); }; echo rc=$?'),
    ("in_subshell", '( $(exit 5) ); echo rc=$?'),
    ("in_case_arm", 'case x in x) $(exit 5);; esac; echo rc=$?'),
    ("in_loop_body", 'for i in 1 2; do $(exit $i); echo rc=$?; done'),
    # The status is a REAL status: conditions and negation read it.
    ("if_condition", 'if $(exit 5); then echo T; else echo F; fi'),
    ("and_or", '$(exit 5) && echo YES || echo NO'),
    ("negation", '! $(exit 5); echo rc=$?'),
    ("errexit_exits", 'set -e; $(exit 5); echo rc=$?'),
    ("shell_exit_status", '$(exit 5)'),
    # --- clause 3 through redirections ----------------------------------
    ("redirect_only_with_sub", '> f $(exit 6); echo rc=$?'),
    ("sub_then_stdout_redirect", '$(exit 5) > /dev/null; echo rc=$?'),
    ("sub_in_redirect_target", 'false; > $(echo f; exit 8); echo rc=$?'),
    ("redirect_target_wins_over_word",
     '> $(echo f; exit 8) $(exit 3); echo rc=$?'),
    ("word_then_redirect_target", '$(exit 3) > $(echo f; exit 8); echo rc=$?'),
    ("stderr_redirect_is_not_stdin", _PRELUDE + '$(exit 5) 2> e.txt; echo rc=$?'),
    ("fd3_input_is_not_stdin", _PRELUDE + '$(exit 5) 3< z.txt; echo rc=$?'),
    ("fd3_dup_is_not_stdin",
     _PRELUDE + 'exec 7</dev/null; $(exit 5) 3<&7; echo rc=$?'),
    ("combined_redirect_is_not_stdin", '$(exit 5) &> o.txt; echo rc=$?'),
    ("clobber_override_is_not_stdin", '$(exit 5) >| o.txt; echo rc=$?'),
    ("close_stdout_is_not_stdin", '$(exit 5) >&-; echo rc=$?'),
    ("fd3_output_is_not_stdin", '$(exit 5) 3> f3.txt; echo rc=$?'),
    # --- clause 2: a redirection on fd 0 erases the status --------------
    ("stdin_redirect", _PRELUDE + '$(exit 5) < z.txt; echo rc=$?'),
    ("explicit_fd0_input", _PRELUDE + '$(exit 5) 0< z.txt; echo rc=$?'),
    ("fd0_output", '$(exit 5) 0> o3.txt; echo rc=$?'),
    ("fd0_readwrite", '$(exit 5) <> rw.txt; echo rc=$?'),
    ("stdin_dup", 'exec 7</dev/null; $(exit 5) <&7; echo rc=$?'),
    ("close_stdin", '$(exit 5) <&-; echo rc=$?'),
    ("explicit_close_stdin", '$(exit 5) 0<&-; echo rc=$?'),
    ("fd0_dup_from_stdout", '$(exit 5) 0>&1; echo rc=$?'),
    ("heredoc", '$(exit 5) <<EOF\nz\nEOF\necho rc=$?'),
    ("here_string", '$(exit 5) <<< z; echo rc=$?'),
    ("process_substitution_on_stdin", '$(exit 5) < <(echo hi); echo rc=$?'),
    ("named_fd_input", _PRELUDE + '$(exit 5) {v}< z.txt; echo rc=$?'),
    ("named_fd_output", '$(exit 5) {v}> o4.txt; echo rc=$?'),
    ("stdin_and_stdout", _PRELUDE + '$(exit 5) > o5.txt < z.txt; echo rc=$?'),
    # --- clause 1: a redirection SETUP failure is 1 ---------------------
    ("bad_output_redirect",
     'false; $(exit 5) > /nonexistent-dir-zz/f; echo rc=$?'),
    ("bad_input_redirect", 'false; $(exit 5) < /nonexistent-zz; echo rc=$?'),
    ("noclobber_refusal",
     'set -C; : > pre.txt; $(exit 5) > pre.txt; echo rc=$?'),
    # --- the shapes that already matched, kept as controls ---------------
    ("assignment_only", 'x=$(exit 5); echo rc=$?'),
    ("two_assignments", 'x=$(exit 5) y=$(exit 6); echo rc=$?'),
    ("assignment_then_vanishing_word", 'x=$(exit 5) $(exit 6); echo rc=$?'),
    ("assignment_with_stdin_redirect",
     _PRELUDE + 'x=$(exit 5) < z.txt; echo rc=$?; echo x=$x'),
    ("array_assignment", 'a=($(sh -c "exit 7")); echo rc=$?'),
    ("array_assignment_with_stdin_redirect",
     _PRELUDE + 'a=($(exit 5)) < z.txt; echo rc=$?'),
    ("prefix_assignment_persists",
     'v=1 $(exit 5) >/dev/null; echo rc=$?; echo v=$v'),
    ("quoted_empty_is_a_command_not_found", '"$(exit 5)"; echo rc=$?'),
    ("no_substitution_at_all", 'false; > f; echo rc=$?'),
    ("no_substitution_bad_redirect",
     'false; > /nonexistent-dir-zz/f; echo rc=$?'),
    ("unset_variable_vanishes", 'false; $undefined; echo rc=$?'),
    ("last_substitution_succeeded", '$(exit 5); $(exit 0); echo rc=$?'),
    ("arithmetic_expansion_is_a_word", 'false; $((1+1)); echo rc=$?'),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case_id,script", _ROWS, ids=[r[0] for r in _ROWS])
def test_null_command_status(case_id, script, mode, tmp_path):
    bash_dir = tmp_path / f"bash-{case_id}-{mode}"
    psh_dir = tmp_path / f"psh-{case_id}-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    assert psh.stdout == bash.stdout, (
        f"{case_id}/{mode}: bash={bash.stdout!r} psh={psh.stdout!r}")
    assert psh.returncode == bash.returncode, (
        f"{case_id}/{mode}: bash rc={bash.returncode} psh rc={psh.returncode}")


@pytest.mark.parametrize("mode", MODES)
def test_null_command_performs_its_redirections(mode, tmp_path):
    """D3: the pin's target is the FILE, not the status. A null command's
    output redirection really does create and truncate the file — psh used to
    skip the redirection entirely on the words-vanished path."""
    script = '$(exit 5) > made.txt; echo rc=$?'
    bash_dir = tmp_path / f"bash-file-{mode}"
    psh_dir = tmp_path / f"psh-file-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    assert (bash_dir / "made.txt").exists(), "the bash oracle changed"
    assert (psh_dir / "made.txt").exists(), "psh skipped the redirection"
    assert psh.stdout == bash.stdout == "rc=5\n"


@pytest.mark.parametrize("mode", MODES)
def test_backgrounded_null_command_carries_its_status(mode, tmp_path):
    """Backgrounded, the null command runs in the child: the FOREGROUND status
    is 0 and the JOB's status is the null-command status."""
    script = '$(exit 5) & echo immediate=$?; wait $!; echo job=$?'
    bash_dir = tmp_path / f"bash-bg-{mode}"
    psh_dir = tmp_path / f"psh-bg-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    assert psh.stdout == bash.stdout, (
        f"{mode}: bash={bash.stdout!r} psh={psh.stdout!r}")
    assert psh.stdout == "immediate=0\njob=5\n"


@pytest.mark.parametrize("mode", MODES)
def test_null_pipeline_member_reports_its_status(mode, tmp_path):
    """A null command used as a pipeline member reports the same status in
    $PIPESTATUS and under `set -o pipefail`."""
    script = ('set -o pipefail; $(exit 5) | true; '
              'echo "ps=${PIPESTATUS[@]}"; echo rc=$?')
    bash_dir = tmp_path / f"bash-pipe-{mode}"
    psh_dir = tmp_path / f"psh-pipe-{mode}"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run(run_bash, script, str(bash_dir), mode)
    psh = _run(run_psh, script, str(psh_dir), mode)

    assert psh.stdout == bash.stdout, (
        f"{mode}: bash={bash.stdout!r} psh={psh.stdout!r}")
    assert psh.stdout.startswith("ps=5 0\n")
