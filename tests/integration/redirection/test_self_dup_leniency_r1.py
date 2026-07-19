"""R1 bounce blocker 2: bash's ``n>&n`` self-dup is a success NO-OP.

Bash treats a dup whose source and target are the SAME fd as an unconditional
success, with no validation, no syscall, and no fd state change — even when
fd n is closed or was never opened.  Probe-derived rule (bash 5.2, archived in
R1-probes/bounce-probes.txt):

* judged POST-RESOLUTION: ``x=3; echo hi 3>&$x`` with fd 3 closed succeeds
  (the rule is fd equality after dynamic resolution, not literal spelling);
* every universe: builtin, external, compound, function, ``exec``;
* both directions (``3>&3``, ``3<&3``) and the move form (``3>&3-``);
* a CLOSED fd stays closed — a child still sees it closed, and a builtin
  whose own output fd is self-dup'd while closed still gets bash's
  ``write error: Bad file descriptor`` when it writes (the redirect itself
  succeeds; the WRITE fails);
* an OPEN fd is untouched.

psh's base behavior errored ``n>&n`` on a closed/never-opened fd in every
universe; the old builtin close-DEFERRAL masked exactly one composite spelling
(``3>&- 3>&3``).  The H4 immediate-close fix un-masked it; the ruling is to
implement bash's leniency at the shared dup path, converging the whole class.

All psh runs are ``-m psh -c`` subprocesses (fresh fds, parallel-safe).
"""
import os
import subprocess
import sys
import tempfile

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def run_psh(script, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       cwd=cwd or TREE, env=env, capture_output=True,
                       text=True, timeout=60)
    return p.stdout, p.stderr, p.returncode


# ---- the un-masked composite row (red on the H4 tip) ----

def test_close_then_self_dup_succeeds():
    # bash: `3>&- 3>&3` closes fd 3, then the self-dup no-ops -> hi, rc 0.
    out, err, rc = run_psh("exec 3>/dev/null; echo hi 3>&- 3>&3; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)
    assert "Bad file descriptor" not in err, err


# ---- never-opened rows (red on BASE in every universe) ----

def test_builtin_never_opened_self_dup():
    out, err, rc = run_psh("echo hi 3>&3; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


def test_external_never_opened_self_dup():
    out, err, rc = run_psh("/bin/echo hi 3>&3; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


def test_compound_never_opened_self_dup():
    out, err, rc = run_psh("{ echo hi; } 3>&3; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


def test_function_never_opened_self_dup():
    out, err, rc = run_psh("f(){ echo hi; }; f 3>&3; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


def test_exec_never_opened_self_dup():
    out, err, rc = run_psh("exec 3>&3; echo rc=$?")
    assert out == "rc=0\n", (out, err)


def test_dynamic_self_dup_post_resolution():
    # The rule is post-resolution: x=3 makes `3>&$x` a self-dup -> success.
    out, err, rc = run_psh("x=3; echo hi 3>&$x; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


def test_input_self_dup_never_opened():
    out, err, rc = run_psh("cat /dev/null 3<&3; echo rc=$?")
    assert out == "rc=0\n", (out, err)


def test_move_self_dup_closed():
    # `3>&3-` on a closed fd: dup no-ops; source==dest means nothing closes.
    out, err, rc = run_psh("exec 3>&-; echo hi 3>&3-; echo rc=$?")
    assert out == "hi\nrc=0\n", (out, err)


# ---- fd state is unchanged by the no-op ----

def test_self_dup_closed_stays_closed_for_child():
    # bash: the no-op does NOT open fd 3; the child still sees it closed.
    out, err, rc = run_psh(
        "exec 3>&-; /bin/sh -c 'echo x >&3' 3>&3; echo rc=$?")
    assert out == "rc=1\n", (out, err)
    assert "3" in err and "Bad file descriptor" in err, err


def test_self_dup_open_is_untouched():
    d = tempfile.mkdtemp()
    f = os.path.join(d, "f")
    out, err, rc = run_psh(f"exec 3>{f}; echo hi 3>&3 >&3; exec 3>&-; cat {f}")
    assert out == "hi\n", (out, err)


def test_builtin_output_self_dup_closed_write_fails():
    # `exec 1>&-; echo hi 1>&1`: the redirect SUCCEEDS (no bad-fd redirect
    # abort naming '1:'), echo runs, and its WRITE fails like bash's.
    out, err, rc = run_psh("exec 1>&-; echo hi 1>&1")
    assert "write error" in err, (out, err)
    assert "hi" not in out, (out, err)


def test_exec_output_self_dup_closed_succeeds():
    out, err, rc = run_psh("exec 1>&-; exec 1>&1; echo rc=$? >&2")
    assert err == "rc=0\n", (out, err)
