"""Process substitution delivers every byte, however late the consumer opens
the path, and holds no descriptor afterwards (C082, C081, C091).

C082: the write side used to be a named FIFO whose child gave up after a fixed
5 s, opened ``/dev/null``, unlinked the FIFO and exited 0 — a producer that
slept 6 s before opening the handed-out path got ``No such file or directory``
and the substitution processed NOTHING, silently. C081: that FIFO was used on
every platform, though the docs called it a macOS-only fallback and bash names
a ``/dev/fd/N`` pipe everywhere. Both directions are now one pipe named
``/dev/fd/N``, so a late open still finds the descriptor.

Every row is a differential against the resolved bash oracle in all three
input modes (``-c``, script file, stdin), and asserts the ACTUAL target: the
bytes that reached the substitution's file, and the shell's own descriptor
census before and after a loop of substitutions — never a bare exit status.

The late-open row deliberately sleeps past the old 5 s boundary, so it costs
~6 s per shell per mode; it is the only pin that can distinguish "the consumer
got everything" from "the name was unlinked under it".

Acquisition-fault and static-ownership coverage lives in
``tests/unit/io_redirect/test_process_sub_lifetime.py``.
"""
import os
import re

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

BASH = resolve_bash().path
MODES = ["c", "file", "stdin"]

#: A shell-neutral, bounded barrier: substitution delivery is ASYNCHRONOUS in
#: both shells (neither waits for a >(...) child at command end), so a row that
#: reads the substitution's output file must wait for the flag the body drops
#: after writing. Bounded, so a genuine delivery regression fails as a
#: comparison rather than hanging.
BARRIER = ('i=0; until [ -e flag ] || [ "$i" -ge 600 ]; '
           'do sleep 0.05; i=$((i+1)); done; ')

_DEV_FD = re.compile(r"/dev/fd/\d+")


def _normalize(text, how):
    """Erase the parts of the output the two shells legitimately disagree on."""
    if how == "devfd":
        # Both shells move the descriptor to the highest free number below 64
        # and so emit the same names, but the number is an allocation detail:
        # rows that are only about the SHAPE normalise it away, and
        # `path_numbers_match_bash` below pins the numbers themselves.
        return _DEV_FD.sub("/dev/fd/N", text)
    return text


# id, script, stdout normalizer, {filename: normalizer}, stderr substring
CASES = [
    # ---- C082: the consumer opens the handed-out path 6 s later ----------
    ("late_open_write_side",
     f': > got; {BASH} -c \'sleep 6; printf "a\\nb\\nc\\nd\\ne\\n" > "$1"\' '
     '_ >(cat > got; : > flag); echo producer_rc=$?; ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    # ---- C081: both directions name a /dev/fd descriptor -----------------
    ("write_side_path_shape", 'echo >(true)', "devfd", {}, ""),
    ("read_side_path_shape", 'echo <(true)', "devfd", {}, ""),
    ("embedded_read_path_shape", 'echo pre<(true)post', "devfd", {}, ""),
    # NOT normalised: the descriptor NUMBER is compared to bash's, so a policy
    # that hands out the lowest free descriptor instead of the highest free
    # one below 64 fails here even though every byte still arrives.
    ("path_numbers_match_bash",
     'echo <(true); echo >(true); echo <(true) <(true) <(true)',
     "exact", {}, ""),
    ("path_numbers_match_bash_with_high_fds_taken",
     'exec 63>/dev/null 62>/dev/null; echo <(true); echo >(true)',
     "exact", {}, ""),
    ("embedded_write_path_shape", 'echo pre>(true)post', "devfd", {}, ""),
    # ---- the bytes that actually reach each side -------------------------
    ("write_side_bytes",
     'echo hi > >(cat > got; : > flag); ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    ("read_side_bytes", "cat <(printf 'a\\nb\\n')", "exact", {}, ""),
    ("write_side_late_body",
     'echo hi > >(sleep 1; cat > got; : > flag); ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    ("read_side_late_body", 'cat <(sleep 1; echo x)', "exact", {}, ""),
    ("append_to_write_side",
     'echo hi >> >(cat > got; : > flag); ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    ("tee_to_write_side",
     "printf 'a\\nb\\n' | tee >(cat > got; : > flag) > /dev/null; " + BARRIER,
     "exact", {"got": "exact"}, ""),
    # The handed-out path is opened by an EXTERNAL process, which can only
    # reach the descriptor because the shell cleared close-on-exec on it.
    ("external_consumer_opens_the_path",
     f'{BASH} -c \'printf "x\\ny\\n" > "$1"\' _ >(cat > got; : > flag); '
     + BARRIER,
     "exact", {"got": "exact"}, ""),
    # The handed-out descriptor must sit clear of the numbers a consuming
    # command redirects itself, or its own `3>f` replaces the substitution
    # before it opens the path (bash keeps substitution descriptors just
    # below 64 for this reason).
    ("consumer_redirects_fd_3",
     'cat <(echo a) 3>f; echo done', "exact", {}, ""),
    ("consumer_redirects_fd_4",
     'cat <(echo a) 4>f 3>g; echo done', "exact", {}, ""),
    ("external_consumer_redirects_low_fds",
     f'{BASH} -c \'exec 3>/dev/null 4>/dev/null 5>/dev/null; '
     'printf "x\\n" > "$1"\' _ >(cat > got; : > flag); ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    ("many_in_one_command",
     'cat <(echo a) <(echo b) <(echo c)', "exact", {}, ""),
    ("nested_substitution", 'cat <(cat <(echo deep))', "exact", {}, ""),
    ("both_directions_one_command",
     'cat <(printf "one\\ntwo\\n") > >(cat > got; : > flag); ' + BARRIER,
     "exact", {"got": "exact"}, ""),
    # ---- a substitution whose body fails ---------------------------------
    ("body_exits_nonzero", 'cat <(exit 3); echo rc=$?', "exact", {}, ""),
    ("body_command_not_found",
     'cat <(psh_no_such_command_xyz); echo rc=$?', "exact", {},
     "psh_no_such_command_xyz"),
    # ---- permanent (exec) substitutions ----------------------------------
    ("exec_read_side",
     'exec 3< <(printf "x\\ny\\n"); read -r a <&3; read -r b <&3; '
     'echo "$a-$b"; exec 3<&-',
     "exact", {}, ""),
    ("exec_write_side",
     'exec 3> >(cat > got; : > flag); echo hi >&3; exec 3>&-; ' + BARRIER,
     "exact", {"got": "exact"}, ""),
]

# A loop of substitutions must leave the shell's OWN descriptor table exactly
# as it found it (C091's harm class, observed from the shell rather than by
# fault injection). `ls /dev/fd` is measured the same way on both sides, so
# the DELTA is the claim; 40 iterations makes a one-descriptor-per-call leak a
# delta of 40, far outside any noise.
CENSUS_CASES = [
    ("census_read_side", 'f() { cat <(echo x) > /dev/null; }'),
    ("census_write_side", 'f() { echo x > >(cat > /dev/null); }'),
    ("census_redirect_target", 'f() { cat < <(echo x) > /dev/null; }'),
]
CENSUS_SCRIPT = (
    '{sub}\n'
    'before=$(ls /dev/fd | wc -l)\n'
    'i=0; while [ "$i" -lt 40 ]; do f; i=$((i+1)); done\n'
    'after=$(ls /dev/fd | wc -l)\n'
    'echo "delta=$((after - before))"\n'
)


def _run(runner, script, mode, workdir, **kw):
    if mode == "c":
        return runner(["-c", script], cwd=workdir, **kw)
    if mode == "file":
        with open(os.path.join(workdir, "s.sh"), "w") as fh:
            fh.write(script + "\n")
        return runner(["s.sh"], cwd=workdir, **kw)
    return runner(["-s"], stdin_data=script + "\n", cwd=workdir, **kw)


def _observe(runner, script, mode, workdir, files, **kw):
    result = _run(runner, script, mode, workdir, **kw)
    assert is_comparable(result), f"harness failure: {result!r}"
    contents = {}
    for name in files:
        path = os.path.join(workdir, name)
        contents[name] = open(path).read() if os.path.exists(path) else None
    return result, contents


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case_id,script,out_norm,files,err_sub",
                         CASES, ids=[c[0] for c in CASES])
def test_process_substitution_matches_bash(case_id, script, out_norm, files,
                                           err_sub, mode, tmp_path):
    timeout = 40.0 if case_id.startswith("late_open") else 20.0
    psh_dir = tmp_path / "psh"
    bash_dir = tmp_path / "bash"
    psh_dir.mkdir()
    bash_dir.mkdir()

    psh, psh_files = _observe(run_psh, script, mode, str(psh_dir), files,
                              timeout=timeout)
    bash, bash_files = _observe(run_bash, script, mode, str(bash_dir), files,
                                timeout=timeout)

    assert _normalize(psh.stdout, out_norm) == _normalize(bash.stdout, out_norm), (
        f"{case_id}/{mode}: stdout psh={psh.stdout!r} bash={bash.stdout!r}")
    assert psh.returncode == bash.returncode, (
        f"{case_id}/{mode}: rc psh={psh.returncode} bash={bash.returncode}")
    if err_sub:
        assert err_sub in psh.stderr and err_sub in bash.stderr, (
            f"{case_id}/{mode}: psh={psh.stderr!r} bash={bash.stderr!r}")
    else:
        # Both empty: a dropped `[Errno 1] Operation not permitted` from the
        # host's exec flake then identifies itself instead of reading as a
        # behavioural regression.
        assert psh.stderr == "" and bash.stderr == "", (
            f"{case_id}/{mode}: psh={psh.stderr!r} bash={bash.stderr!r}")

    # D3: the bytes that actually reached the substitution, not just a status.
    for name in files:
        assert psh_files[name] == bash_files[name], (
            f"{case_id}/{mode}: {name} psh={psh_files[name]!r} "
            f"bash={bash_files[name]!r}")
        assert psh_files[name] is not None, (
            f"{case_id}/{mode}: {name} was never written")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case_id,sub", CENSUS_CASES,
                         ids=[c[0] for c in CENSUS_CASES])
def test_substitution_loop_leaves_the_fd_table_unchanged(case_id, sub, mode,
                                                         tmp_path):
    script = CENSUS_SCRIPT.format(sub=sub)
    psh_dir = tmp_path / "psh"
    bash_dir = tmp_path / "bash"
    psh_dir.mkdir()
    bash_dir.mkdir()

    psh = _run(run_psh, script, mode, str(psh_dir), timeout=120.0)
    bash = _run(run_bash, script, mode, str(bash_dir), timeout=120.0)
    assert is_comparable(psh) and is_comparable(bash), f"{psh!r} {bash!r}"

    assert psh.stdout == "delta=0\n", (
        f"{case_id}/{mode}: psh leaked descriptors: {psh.stdout!r} "
        f"stderr={psh.stderr!r}")
    assert bash.stdout == psh.stdout, (
        f"{case_id}/{mode}: bash={bash.stdout!r} psh={psh.stdout!r}")
