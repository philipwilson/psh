"""C031: a redirect target is expanded exactly once, in all three input modes.

Defect (v0.781.0): ``IOManager.setup_builtin_redirections`` resolved each
redirect through ``RedirectPlanner.plan`` and then, for an in-process builtin
with a redirect on fd >= 3, DISCARDED the plan and called
``_builtin_redirect_fd_level(redirect, frame)``, which rebuilt a
``RedirectProgram`` and planned the SAME redirect again.  Planning expands the
target word and creates its process substitution, so the target was resolved
twice and only the SECOND resolution was what the fd pointed at::

    echo hi 3> "$(echo x >> ctr; echo o3)"     # bash appends 1 line, psh 2
    read -u 3 v 3< <(echo x >> ctr; echo data) # bash forks 1 child, psh 2

    echo 0 > c; echo OLD > f2; set -C
    echo hi 3> "$(n=$(cat c); n=$((n+1)); echo $n >| c; echo f$n)"
    # bash creates f1.  psh checked noclobber against expansion #1 (f1) and
    # opened expansion #2 (f2), so it refused "f2: cannot overwrite existing
    # file" and created NOTHING.  WRONG TARGET.

INVARIANT PINNED HERE: a ``RedirectOp`` is planned exactly once; the fd-level
builtin path applies the plan it was given.

Every row asserts the ACTUAL target (D3) -- which file was created, the bytes
in it, the value read back through the descriptor -- never a bare return code,
and runs in all three input modes (``-c``, script file, stdin).  Expectations
verified against bash 5.3.15; the differential rows live in
``tests/conformance/bash/test_plan_once_conformance.py``.
"""
import os

import pytest
from shell_oracle import is_comparable, run_psh

# A target that CHANGES on every expansion: the name that exists afterwards
# identifies which expansion the shell actually opened.  `>| c` in the clobber
# variant so the write-back survives `set -C`.
INCR = '"$(n=$(cat c); n=$((n+1)); echo $n > c; echo f$n)"'
INCR_CLOBBER = '"$(n=$(cat c); n=$((n+1)); echo $n >| c; echo f$n)"'

# (id, script, {filename: expected contents}, [must not exist],
#  expected rc, expected stderr substring or "" for none, expected stdout)
CASES = [
    # --- the target's command substitution runs exactly once ---
    ("cmdsub_once_fd3_output",
     'echo hi 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("cmdsub_once_fd3_append",
     'echo hi 3>> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("cmdsub_once_fd9_colon",
     ': 9> "$(echo x >> ctr; echo o9)"',
     {"ctr": "x\n", "o9": ""}, [], 0, "", ""),
    ("cmdsub_once_fd4_printf",
     'printf "hi\\n" 4> "$(echo x >> ctr; echo o4)"',
     {"ctr": "x\n", "o4": ""}, [], 0, "", "hi\n"),
    ("cmdsub_once_fd3_readwrite",
     'echo hi 3<> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("cmdsub_once_fd3_input",
     'printf "L\\n" > src; read -u 3 v 3< "$(echo x >> ctr; echo src)"; '
     'echo "v=$v"',
     {"ctr": "x\n"}, [], 0, "", "v=L\n"),
    # --- the fd points at that single expansion, and carries its bytes ---
    ("fd3_target_receives_the_bytes",
     'eval "echo payload >&3" 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": "payload\n"}, [], 0, "", ""),
    # --- one plan per operation, in source order ---
    ("two_operations_one_expansion_each",
     'echo hi 3> "$(echo a >> ctr; echo o3)" 4> "$(echo b >> ctr; echo o4)"',
     {"ctr": "a\nb\n", "o3": "", "o4": ""}, [], 0, "", "hi\n"),
    ("nested_eval_one_expansion_each",
     'eval \'echo inner 3> "$(echo x >> ctr; echo i3)"\' '
     '3> "$(echo y >> ctr; echo o3)"',
     {"ctr": "y\nx\n"}, [], 0, "", "inner\n"),
    # --- a process substitution target forks exactly one child ---
    ("procsub_forks_once_read",
     'read -u 3 v 3< <(echo x >> ctr; echo data); echo "v=$v"',
     {"ctr": "x\n"}, [], 0, "", "v=data\n"),
    ("procsub_forks_once_mapfile",
     'mapfile -t -u 3 arr 3< <(echo x >> ctr; echo L1; echo L2); '
     'echo "${arr[0]}-${arr[1]}"',
     {"ctr": "x\n"}, [], 0, "", "L1-L2\n"),
    # --- WRONG TARGET: which file is created identifies the expansion used ---
    ("first_expansion_is_the_file_created",
     f'echo 0 > c; echo hi 3> {INCR}',
     {"c": "1\n", "f1": ""}, ["f2"], 0, "", "hi\n"),
    ("noclobber_does_not_refuse_a_name_it_never_opens",
     'echo 0 > c; echo OLD > f2; set -C; '
     f'echo hi 3> {INCR_CLOBBER}',
     {"c": "1\n", "f1": "", "f2": "OLD\n"}, [], 0, "", "hi\n"),
    ("noclobber_refuses_the_name_it_would_open",
     'echo 0 > c; echo OLD > f1; set -C; '
     f'echo hi 3> {INCR_CLOBBER}; echo "rc=$?"',
     {"c": "1\n", "f1": "OLD\n"}, ["f2"], 0,
     "f1: cannot overwrite existing file", "rc=1\n"),
    ("noclobber_still_refuses_an_existing_target",
     'echo OLD > t; set -C; echo hi 3> t; echo "rc=$?"',
     {"t": "OLD\n"}, [], 0, "t: cannot overwrite existing file", "rc=1\n"),
    # --- frame nesting: an inner frame's restore leaves the outer alone ---
    ("nested_frames_restore_innermost_first",
     'eval "echo A >&3; eval \\"echo B >&3\\" 3> in2; echo C >&3" 3> out3',
     {"out3": "A\nC\n", "in2": "B\n"}, [], 0, "", ""),
    ("fd3_restored_after_the_builtin",
     'exec 3> keep; eval "echo inner >&3" 3> tmp3; echo after >&3; '
     'exec 3>&-',
     {"tmp3": "inner\n", "keep": "after\n"}, [], 0, "", ""),
    # --- the move split derives both halves from the one plan ---
    ("move_dups_then_closes_the_source",
     'eval "echo v4 >&4" 3> t3 4>&3-',
     {"t3": "v4\n"}, [], 0, "", ""),
    ("self_move_keeps_the_fd_open",
     'eval "echo s >&3" 3> t3 3>&3-',
     {"t3": "s\n"}, [], 0, "", ""),
    # --- here-input on a high fd is materialized once ---
    ("heredoc_on_fd3",
     'read -u 3 v 3<<EOF\nhello\nEOF\necho "v=$v"',
     {}, [], 0, "", "v=hello\n"),
    ("herestring_on_fd3",
     'read -u 3 v 3<<< "here string"; echo "v=$v"',
     {}, [], 0, "", "v=here string\n"),
    # --- controls: paths that already expanded once, unchanged ---
    ("control_brace_group",
     '{ echo hi; } 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("control_function",
     'g() { echo hi; }; g 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("control_external_command",
     '/bin/echo hi 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("control_subshell",
     '( echo hi ) 3> "$(echo x >> ctr; echo o3)"',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
    ("control_stdout_stream_path",
     'echo hi > "$(echo x >> ctr; echo o1)"',
     {"ctr": "x\n", "o1": "hi\n"}, [], 0, "", ""),
    ("control_stderr_stream_path",
     'eval "echo e >&2" 2> "$(echo x >> ctr; echo o2)"',
     {"ctr": "x\n", "o2": "e\n"}, [], 0, "", ""),
    ("control_combined_redirect",
     'eval "echo o; echo e >&2" &> "$(echo x >> ctr; echo ob)"',
     {"ctr": "x\n", "ob": "o\ne\n"}, [], 0, "", ""),
    ("control_permanent_exec",
     'exec 3> "$(echo x >> ctr; echo o3)"; echo permanent >&3; exec 3>&-',
     {"ctr": "x\n", "o3": "permanent\n"}, [], 0, "", ""),
    ("control_named_fd",
     'echo hi {v}> "$(echo x >> ctr; echo ov)"',
     {"ctr": "x\n", "ov": ""}, [], 0, "", "hi\n"),
    ("control_pipeline_member",
     'echo hi 3> "$(echo x >> ctr; echo o3)" | cat',
     {"ctr": "x\n", "o3": ""}, [], 0, "", "hi\n"),
]

MODES = ["c", "file", "stdin"]


def _run(script, mode, workdir):
    if mode == "c":
        return run_psh(["-c", script], cwd=workdir)
    if mode == "file":
        path = os.path.join(workdir, "s.sh")
        with open(path, "w") as fh:
            fh.write(script + "\n")
        return run_psh(["s.sh"], cwd=workdir)
    return run_psh(["-s"], stdin_data=script + "\n", cwd=workdir)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "case_id,script,files,absent,rc,err_sub,expected_out",
    CASES, ids=[c[0] for c in CASES])
def test_redirect_target_planned_once(case_id, script, files, absent, rc,
                                      err_sub, expected_out, mode, tmp_path):
    workdir = str(tmp_path)
    result = _run(script, mode, workdir)
    assert is_comparable(result), f"{case_id}/{mode}: harness failure {result}"

    assert result.returncode == rc, (
        f"{case_id}/{mode}: rc {result.returncode} != {rc}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    assert result.stdout == expected_out, (
        f"{case_id}/{mode}: stdout {result.stdout!r} != {expected_out!r}")
    if err_sub:
        assert err_sub in result.stderr, (
            f"{case_id}/{mode}: {err_sub!r} not in stderr {result.stderr!r}")
        # The second expansion produced a SECOND diagnostic; one operation
        # emits one.
        assert result.stderr.count(err_sub) == 1, (
            f"{case_id}/{mode}: {err_sub!r} appears "
            f"{result.stderr.count(err_sub)} times in {result.stderr!r}")
    else:
        assert result.stderr == "", (
            f"{case_id}/{mode}: unexpected stderr {result.stderr!r}")

    # D3: the pin asserts the ACTUAL target -- which file exists and its bytes.
    for name, expected in files.items():
        path = os.path.join(workdir, name)
        assert os.path.exists(path), f"{case_id}/{mode}: {name} was never created"
        with open(path) as fh:
            got = fh.read()
        assert got == expected, (
            f"{case_id}/{mode}: {name} = {got!r} != {expected!r}")
    for name in absent:
        assert not os.path.exists(os.path.join(workdir, name)), (
            f"{case_id}/{mode}: {name} exists -- the wrong expansion was opened")
