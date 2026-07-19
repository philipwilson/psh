"""R1: source-ordered redirect application — fd closes are NOT deferred (#20 H4).

Base defect (5989ed9e): ``IOManager.setup_builtin_redirections`` deferred every
fd-level close (``>&-``/``<&-`` and the source-close of a move) until after all
other redirects were applied.  A later ``n>&m`` therefore duplicated a
descriptor that source order had already closed, so bash's "Bad file
descriptor" abort never fired for a builtin.

Bash 5.2 applies redirections strictly left-to-right and aborts the command on
the first failure.  The fd-universe paths (external command in a forked child,
in-process compound, ``exec``) already did this; only the builtin stream
universe deferred.  These pins drive the SAME close-then-dup pattern across
every consumer (builtin no-output, builtin output, external, compound,
function) — the mode-blind lesson: the divergence lived in exactly one universe.

All cases run psh in a fresh ``-m psh -c`` subprocess (the child owns the fds;
no in-process fd rewrite, so parallel-safe).  Expected values are bash-5.2
verified (see tmp/boundary-ledgers/R1-probes/probe2-base-5989ed9e.txt).

DISCRIMINATING PRECONDITION (accidentally-green defense): the ``exec
3>/dev/null`` prelude makes fd 3 OPEN before each close-then-dup row, so the
``4>&3`` failure is attributable ONLY to the preceding source-ordered ``3>&-``
— never to fd 3 having simply never been opened (a never-opened ``4>&3`` fails
for that independent reason, and ``n>&n`` self-dups are lenient anyway — see
test_self_dup_leniency_r1.py).  A row that dropped the prelude could go green
without exercising the ordering at all.
"""
import os
import subprocess
import sys

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def run_psh(script):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       cwd=TREE, env=env, capture_output=True, text=True,
                       timeout=60)
    return p.stdout, p.stderr, p.returncode


# ---- H4 core: close-then-dup must abort (bad fd), like bash ----

def test_colon_close1_then_dup_closed_is_bad_fd():
    # `: 1>&- 2>&1` — close fd 1, then dup the now-closed fd 1 -> bad fd abort.
    out, err, rc = run_psh(": 1>&- 2>&1; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "1: Bad file descriptor" in err, err


def test_colon_close3_then_dup_closed_is_bad_fd():
    out, err, rc = run_psh("exec 3>/dev/null; : 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "3: Bad file descriptor" in err, err


def test_echo_close3_then_dup_closed_aborts_before_run():
    # The strongest row: `echo hi 3>&- 4>&3` must NOT print hi (redirect
    # aborts before the builtin runs). Base printed "hi" rc=0.
    out, err, rc = run_psh("exec 3>/dev/null; echo hi 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "hi" not in out, out
    assert "3: Bad file descriptor" in err, err


def test_printf_close3_then_dup_closed_aborts_before_run():
    out, err, rc = run_psh("exec 3>/dev/null; printf hi 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "hi" not in out, out
    assert "3: Bad file descriptor" in err, err


def test_echo_close1_then_dup_closed_aborts_before_run():
    # `echo hi 1>&- 2>&1`: bash aborts the redirect (fd 1 bad) and never runs
    # echo. Output must be only rc=1; no write-error from a run echo.
    out, err, rc = run_psh("echo hi 1>&- 2>&1; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "write error" not in (out + err), (out, err)
    assert "1: Bad file descriptor" in err, err


def test_external_close3_then_dup_closed_is_bad_fd():
    out, err, rc = run_psh("exec 3>/dev/null; /bin/echo hi 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "3: Bad file descriptor" in err, err


def test_compound_close3_then_dup_closed_is_bad_fd():
    out, err, rc = run_psh(
        "exec 3>/dev/null; { echo hi; } 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "3: Bad file descriptor" in err, err


def test_function_close3_then_dup_closed_is_bad_fd():
    out, err, rc = run_psh(
        "exec 3>/dev/null; f(){ echo hi; }; f 3>&- 4>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "3: Bad file descriptor" in err, err


# ---- Controls: dup-BEFORE-close and the relocation case must stay correct ----

def test_control_dup_before_close_succeeds():
    # `echo hi 4>&3 3>&-`: dup fd 3 (open) to fd 4, THEN close fd 3 -> ok.
    out, err, rc = run_psh("exec 3>/dev/null; echo hi 4>&3 3>&-; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)
    assert err == "" or "Bad file descriptor" not in err, err


def test_control_close_low_then_open_relocates():
    # `echo hi 1>&- 2>ff`: close fd 1, open ff for fd 2 (relocated off fd 1);
    # echo's own stdout stays closed -> write error, ff empty. Immediate close
    # must NOT corrupt this (relocation covers the freed-low-fd concern).
    import tempfile
    d = tempfile.mkdtemp()
    ff = os.path.join(d, "ff")
    out, err, rc = run_psh(f"echo hi 1>&- 2>{ff}; echo rc=$?")
    # rc reported 1; echo's stdout (fd 1) is closed so "hi" is never written;
    # echo's stderr (fd 2) -> ff carries the write-error diagnostic. Immediate
    # close must NOT corrupt this (relocation covers the freed-low-fd concern).
    assert out == "rc=1\n", (out, err)
    with open(ff) as fh:
        ff_text = fh.read()
    assert "write error" in ff_text, ff_text
    assert "hi" not in ff_text, ff_text


def test_control_dup_before_close_2to1_then_close():
    # `echo hi 2>&1 1>&-`: dup fd 1 (open) to fd 2, then close fd 1. echo
    # writes to closed fd 1 -> write error, rc 1 (bash-identical).
    out, err, rc = run_psh("echo hi 2>&1 1>&-; echo rc=$?")
    assert "rc=1" in out, (out, err)
    assert "write error" in (out + err), (out, err)


def test_control_move_form_close_source():
    # `echo hi 3>&1-`: move fd 1 into fd 3, closing fd 1. echo -> closed fd 1.
    out, err, rc = run_psh("exec 3>/dev/null; echo hi 3>&1-; echo rc=$?")
    assert "rc=1" in out, (out, err)
    assert "write error" in (out + err), (out, err)


def test_control_multiple_opens_same_fd_last_wins():
    # `echo hi >a >b`: a truncated empty, b gets hi (both opened, last dup wins).
    import tempfile
    d = tempfile.mkdtemp()
    a = os.path.join(d, "a")
    b = os.path.join(d, "b")
    out, err, rc = run_psh(f"echo hi >{a} >{b}")
    with open(a) as fh:
        assert fh.read() == "", "first target truncated empty"
    with open(b) as fh:
        assert fh.read() == "hi\n", "last target wins"
