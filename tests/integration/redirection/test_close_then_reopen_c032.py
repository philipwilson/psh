"""C032: a per-command redirect list CAN close then reopen fd 1/2.

Defect (v0.780.0): ``IOManager._swap_closed_output_streams`` scans the redirect
list as a WHOLE, after ``apply_redirections`` has already applied it in source
order, and installed the opaque ``_ClosedStream`` (write -> EBADF) for ANY
``1>&-``/``2>&-`` in the list.  A LATER reopen of the same fd was therefore
severed at the stream level although the fd universe had honoured it:

    { echo hi; } 1>&- 1>f      # bash 5.3.15: rc 0, f == "hi\n"
                               # psh (base):  rc 1, f == "",
                               #              "echo: write error: Bad file descriptor"

Silent data loss in EVERY in-process compound (brace group, function, ``if``,
``while``, ``until``, ``for``, ``case``) for both fd 1 and fd 2.

INVARIANT PINNED HERE: the stream half of a close applied by a LIST-WIDE scan
follows the fd NUMBER and lets the settled fd universe decide.  EBADF is the
answer only when the fd is still closed at the END of the list.

Every row asserts the ACTUAL TARGET (D3) — the bytes in the file the reopen
points at — not merely a return code, and runs in all three input modes
(``-c``, script file, stdin).  Expectations verified against bash 5.3.15;
the differential rows live in
``tests/conformance/bash/test_close_then_reopen_conformance.py``.
"""
import os
import re

import pytest

from shell_oracle import is_comparable, run_psh

# A shell diagnostic carries a shell-and-mode-specific location prefix
# ("psh: line 1: " under -c/stdin, "s.sh: line 1: " under a script file).  Rows
# whose expected text is DIAG-marked pin the shell's ANSWER plus the presence
# of SOME prefix, never the shell's identity.
DIAG = "\x00DIAG\x00"
_DIAG_RE = re.compile(r"^\S+: line \d+: cd: /nonexistent_zz: "
                      r"No such file or directory\n\Z")

# (id, script, {filename: expected contents}, expected rc,
#  expected stderr substring or "" for none, expected stdout)
CASES = [
    # --- rows a-g of the inventory: the reopen must win ---
    ("brace_fd1_file",
     '{ echo hi; } 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("function_fd1_file",
     'g() { echo hi; }; g 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("if_fd1_file",
     'if true; then echo hi; fi 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("while_fd1_file",
     'i=0; while [ $i -lt 1 ]; do echo hi; i=1; done 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("until_fd1_file",
     'i=0; until [ $i -gt 0 ]; do echo hi; i=1; done 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("for_fd1_file",
     'for x in 1; do echo hi; done 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("case_fd1_file",
     'case x in x) echo hi;; esac 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("nested_brace_fd1_file",
     '{ { echo hi; } 1>&- 1>f; }',
     {"f": "hi\n"}, 0, "", ""),
    ("append_target",
     '{ echo hi; } 1>&- 1>>f',
     {"f": "hi\n"}, 0, "", ""),
    ("printf_builtin",
     '{ printf "hi\\n"; } 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    ("external_command",
     '{ /bin/echo hi; } 1>&- 1>f',
     {"f": "hi\n"}, 0, "", ""),
    # close -> dup: fd 1 becomes fd 2's target, so the body lands on stderr
    ("brace_fd1_dup_to_2",
     '{ echo hi; } 1>&- 1>&2',
     {}, 0, "hi\n", ""),
    # --- fd 2: a builtin's own diagnostic must reach the reopened target ---
    ("brace_fd2_cd_diagnostic",
     '{ cd /nonexistent_zz; } 2>&- 2>f',
     {"f": DIAG}, 1, "", ""),
    ("function_fd2_cd_diagnostic",
     'g() { cd /nonexistent_zz; }; g 2>&- 2>f',
     {"f": DIAG}, 1, "", ""),
    # fd 2 closed then dup'd onto fd 1 -> the diagnostic comes out on stdout
    ("brace_fd2_dup_to_1",
     '{ cd /nonexistent_zz; } 2>&- 2>&1',
     {}, 1, "", DIAG),
    # both fds closed and both reopened in one list
    ("both_fds_reopened",
     '{ echo out; echo err >&2; } 1>&- 2>&- 1>o 2>e',
     {"o": "out\n", "e": "err\n"}, 0, "", ""),
    # --- the fd is still closed at the END of the list: EBADF stays correct ---
    ("reverse_order_still_ebadf",
     '{ echo hi; } 1>f 1>&-',
     {"f": ""}, 1, "write error: Bad file descriptor", ""),
    ("close_reopen_close_still_ebadf",
     '{ echo hi; } 1>&- 1>f 1>&-',
     {"f": ""}, 1, "write error: Bad file descriptor", ""),
    ("close_only_still_ebadf",
     '{ echo hi; } 1>&-',
     {}, 1, "write error: Bad file descriptor", ""),
    # --- restore: the displaced stream comes back, unharmed, afterwards ---
    ("restore_after_reopen",
     '{ echo hi; } 1>&- 1>f; echo after',
     {"f": "hi\n"}, 0, "", "after\n"),
    ("restore_after_ebadf",
     '{ echo hi; } 1>&-; echo back',
     {}, 0, "write error: Bad file descriptor", "back\n"),
    ("function_reusable_after_reopen",
     'g() { echo in; }; g 1>&- 1>f; g',
     {"f": "in\n"}, 0, "", "in\n"),
    # --- a body redirect must not be able to steal the reopened low fd ---
    ("body_open_cannot_steal_fd1",
     'printf "L\\n" > src; { read v < src; echo "got=$v"; } 1>&- 1>f',
     {"f": "got=L\n", "src": "L\n"}, 0, "", ""),
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
    "case_id,script,files,rc,err_sub,expected_out",
    CASES, ids=[c[0] for c in CASES])
def test_close_then_reopen(case_id, script, files, rc, err_sub, expected_out,
                           mode, tmp_path):
    workdir = str(tmp_path)
    result = _run(script, mode, workdir)
    assert is_comparable(result), f"{case_id}/{mode}: harness failure {result}"

    assert result.returncode == rc, (
        f"{case_id}/{mode}: rc {result.returncode} != {rc}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    if expected_out == DIAG:
        assert _DIAG_RE.match(result.stdout), (
            f"{case_id}/{mode}: stdout {result.stdout!r} is not cd's diagnostic")
    else:
        assert result.stdout == expected_out, (
            f"{case_id}/{mode}: stdout {result.stdout!r} != {expected_out!r}")
    if err_sub:
        assert err_sub in result.stderr, (
            f"{case_id}/{mode}: {err_sub!r} not in stderr {result.stderr!r}")
    else:
        assert result.stderr == "", (
            f"{case_id}/{mode}: unexpected stderr {result.stderr!r}")

    # D3: the pin asserts the ACTUAL target -- the bytes in the reopened file.
    for name, expected in files.items():
        path = os.path.join(workdir, name)
        assert os.path.exists(path), f"{case_id}/{mode}: {name} was never created"
        with open(path) as fh:
            got = fh.read()
        if expected == DIAG:
            assert _DIAG_RE.match(got), (
                f"{case_id}/{mode}: {name} = {got!r} is not cd's diagnostic")
        else:
            assert got == expected, (
                f"{case_id}/{mode}: {name} = {got!r} != {expected!r}")


@pytest.mark.parametrize("mode", MODES)
def test_stdout_stream_object_is_restored(mode, tmp_path):
    """Two compounds in a row: the second still writes to the real stdout.

    A restore that left the fd-following stream installed would make the
    SECOND compound write through a stale fd number.
    """
    script = ('{ echo one; } 1>&- 1>f1; '
              '{ echo two; } 1>&- 1>f2; '
              'echo three')
    workdir = str(tmp_path)
    result = _run(script, mode, workdir)
    assert is_comparable(result), result
    assert (result.returncode, result.stdout, result.stderr) == (0, "three\n", "")
    with open(os.path.join(workdir, "f1")) as fh:
        assert fh.read() == "one\n"
    with open(os.path.join(workdir, "f2")) as fh:
        assert fh.read() == "two\n"
