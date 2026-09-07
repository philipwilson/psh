"""Pipeline-member exec-in-place is a ONE-SHOT token (C001, C179).

C001 was silent data loss. The member process inherited a "may exec in
place" flag, so the FIRST external command inside a function body, ``eval``
text or a sourced file replaced the member process and every command after
it was discarded, taking the member's exit status with it::

    f(){ /bin/echo A; echo B; }; f | cat        # bash: A B   psh: A
    set -o pipefail; f(){ /bin/echo A; false; }; f | cat   # bash: 1  psh: 0

Owner: ``psh/executor/context.py#ExecutionContext.for_pipeline_member``
grants the token to a SIMPLE-COMMAND member only, and
``ExecutionContext.take_exec_in_place`` spends it on that member's own
dispatch, so no nested frame can observe it.

Both directions are pinned: a plain external member still execve()s in
place (the optimization is kept), and a function / ``eval`` / ``.`` member
does not. Every behavioral row runs in all three input modes (``-c``,
script file, stdin) because C001 reproduced in all three.
"""

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

# Body of the sourced file used by the `.`/source rows.
SOURCED_BODY = "/bin/echo A; echo B\n"

# (id, script) for every row that must match bash byte for byte.
#
# `/usr/bin/false` rather than `/bin/false`: macOS has no /bin/false, and the
# row needs a real EXTERNAL command that fails.
DIFFERENTIAL_ROWS = [
    ("function_body_external_first",
     'f(){ /bin/echo A; echo B; }; f | cat'),
    ("function_body_external_middle",
     'f(){ echo A; /bin/echo B; echo C; }; f | cat'),
    ("nested_function_bodies",
     'g(){ /bin/echo G; echo g2; }; f(){ g; echo F; }; f | cat'),
    ("eval_member",
     'echo x | eval "/bin/echo A; echo B"'),
    ("source_member",
     'echo x | . ./sourced.sh'),
    ("pipefail_status_is_last_command",
     'set -o pipefail; f(){ /bin/echo A; false; }; f | cat; echo rc=$?'),
    ("failing_external_first_still_runs_rest",
     'f(){ /usr/bin/false; echo B; }; f | cat'),
    ("member_status_is_last_command",
     'f(){ /bin/echo A; /usr/bin/false; }; f | cat; echo st=${PIPESTATUS[0]}'),
    ("builtin_last_member_reads_whole_body",
     'f(){ /bin/echo A; echo B; }; f | while read l; do echo "got:$l"; done'),
    ("function_member_with_trailing_external",
     'f(){ echo A; /bin/echo B; }; f | cat'),
    ("function_in_middle_of_three_stage_pipeline",
     'f(){ /bin/echo A; echo B; }; echo seed | f | cat'),
    # Controls: the shapes that already worked must keep working.
    ("control_brace_group_member",
     '{ /bin/echo A; echo B; } | cat'),
    ("control_subshell_member",
     '( /bin/echo A; echo B ) | cat'),
    ("control_for_loop_member",
     'for i in 1 2; do /bin/echo A$i; echo B$i; done | cat'),
    ("control_plain_external_member",
     '/bin/echo A | cat'),
]


def _run_mode(runner, script, mode, tmp_path):
    """Run *script* through *runner* in one of the three input modes."""
    cwd = str(tmp_path)
    if mode == "dash_c":
        return runner(['-c', script], cwd=cwd)
    if mode == "script_file":
        path = tmp_path / "case.sh"
        path.write_text(script + "\n")
        return runner([str(path)], cwd=cwd)
    if mode == "stdin":
        return runner([], stdin_data=script + "\n", stdin_mode="pipe", cwd=cwd)
    raise AssertionError(f"unknown mode {mode!r}")


@pytest.mark.parametrize("mode", ["dash_c", "script_file", "stdin"])
@pytest.mark.parametrize("row_id,script",
                         DIFFERENTIAL_ROWS,
                         ids=[r[0] for r in DIFFERENTIAL_ROWS])
def test_pipeline_member_matches_bash(row_id, script, mode, tmp_path):
    """Every C001 row is byte-identical to bash in all three input modes."""
    (tmp_path / "sourced.sh").write_text(SOURCED_BODY)

    bash = _run_mode(run_bash, script, mode, tmp_path)
    psh = _run_mode(run_psh, script, mode, tmp_path)
    assert is_comparable(bash), bash
    assert is_comparable(psh), psh
    assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode), (
        f"{row_id}/{mode}: bash={bash.stdout!r} rc={bash.returncode} "
        f"psh={psh.stdout!r} rc={psh.returncode}")


@pytest.mark.parametrize("mode", ["dash_c", "script_file", "stdin"])
def test_whole_function_body_reaches_the_file_through_the_pipe(mode, tmp_path):
    """The BYTES land in the file the pipeline writes (C001, D3).

    Reading the runner's stdout would not prove the member's later commands
    reached the pipe rather than some other fd, so the pipeline's tail
    redirects into a file and the file is read from disk.
    """
    script = ('f(){ /bin/echo A; echo B; echo C; }; '
              'f | cat > out.txt')
    bash_dir = tmp_path / "bash"
    psh_dir = tmp_path / "psh"
    bash_dir.mkdir()
    psh_dir.mkdir()

    bash = _run_mode(run_bash, script, mode, bash_dir)
    psh = _run_mode(run_psh, script, mode, psh_dir)
    assert is_comparable(bash) and is_comparable(psh)

    bash_bytes = (bash_dir / "out.txt").read_text()
    psh_bytes = (psh_dir / "out.txt").read_text()
    assert bash_bytes == "A\nB\nC\n", bash_bytes
    assert psh_bytes == bash_bytes, f"bash={bash_bytes!r} psh={psh_bytes!r}"


def _debug_exec_markers(script, tmp_path):
    """Return (exec_in_place_count, forked_exec_count) from --debug-exec.

    ``Before exec`` is printed only by the exec-in-place branch
    (``psh/executor/strategies.py``, guarded by ``context.exec_in_place``);
    ``execvpe`` only by the forked-child path.
    """
    r = run_psh(['--debug-exec', '-c', script], cwd=str(tmp_path))
    assert is_comparable(r), r
    lines = r.stderr.splitlines()
    return (sum('Before exec' in ln for ln in lines),
            sum('execvpe' in ln for ln in lines))


def test_plain_external_member_still_execs_in_place(tmp_path):
    """The optimization is KEPT: a simple external member execve()s in place.

    Both members of `/bin/echo A | cat` are plain external simple commands,
    so both spend their own token and neither forks again (C001).
    """
    in_place, forked = _debug_exec_markers('/bin/echo A | cat', tmp_path)
    assert in_place == 2, f"expected both members to exec in place, got {in_place}"
    assert forked == 0, f"no member should fork again, got {forked}"


def test_function_body_external_does_not_exec_in_place(tmp_path):
    """A function member's body external command FORKS (C001).

    `f | cat`: the `cat` member spends its own token and execs in place; the
    `/bin/echo` inside f's body finds the token already spent, so it forks
    and `echo B` after it still runs. There is no tail-call optimization —
    an external command LAST in the body forks too.
    """
    in_place, forked = _debug_exec_markers(
        'f(){ /bin/echo A; echo B; }; f | cat', tmp_path)
    assert in_place == 1, (
        f"only the `cat` member may exec in place, got {in_place}")
    assert forked == 1, f"the body's /bin/echo must fork, got {forked}"

    tail = _debug_exec_markers('f(){ echo A; /bin/echo B; }; f | cat', tmp_path)
    assert tail == (1, 1), f"no tail-call exec optimization, got {tail}"


def test_eval_and_source_members_do_not_exec_in_place(tmp_path):
    """`eval` and `.` members consume the token themselves (C001)."""
    (tmp_path / "sourced.sh").write_text(SOURCED_BODY)
    assert _debug_exec_markers(
        'echo x | eval "/bin/echo A; echo B"', tmp_path) == (0, 1)
    assert _debug_exec_markers(
        'echo x | . ./sourced.sh', tmp_path) == (0, 1)


def test_psh_has_no_lastpipe_option(tmp_path):
    """psh does not implement `shopt -s lastpipe` (documented gap).

    The slot's risk register asks whether the one-shot could break
    ``lastpipe``. It cannot: psh has no lastpipe path at all — every member
    runs in a forked child — and this pins that premise so the answer stops
    being true silently.
    """
    r = run_psh(['-c', 'shopt -s lastpipe'], cwd=str(tmp_path))
    assert is_comparable(r), r
    assert r.returncode != 0, r
    assert 'lastpipe' in r.stderr, r.stderr
