"""R1: redirect diagnostics carry the one location prefix (diagnostic source
computed once).

Base defect (5989ed9e): ``format_redirect_error`` HARDCODES a bare ``psh: ``
prefix, bypassing ``ShellState.error_location_prefix()`` — the single source of
truth every other runtime diagnostic uses.  So a redirect-setup error from the
external-child / compound / simple-command / subshell paths (and the errno-set
builtin path) lacked bash's ``line N:`` while builtin write/read/noclobber
errors carried it — the same fact spelled two ways.

Bash 5.2 prints ``<$0>: line N: <name>: <strerror>`` for every redirect error.
Routing ``format_redirect_error`` through ``error_location_prefix()`` makes the
diagnostic uniform (``-c`` -> ``psh: line N:``; script -> ``NAME: line N:``).

Bash-5.2 verified (tmp/boundary-ledgers/R1-probes/*).  The pins assert the
``line N:`` location is present (the fixed fact) and the message text; the
argv0 token itself (``psh``/``bash``/script name) is expected to differ.
"""
import os
import subprocess
import sys
import tempfile

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def run_psh_c(script):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       cwd=TREE, env=env, capture_output=True, text=True,
                       timeout=60)
    return p.stdout, p.stderr, p.returncode


def run_psh_script(body):
    env = dict(os.environ)
    env["PYTHONPATH"] = TREE
    env["PSH_STRICT_ERRORS"] = "0"
    d = tempfile.mkdtemp()
    path = os.path.join(d, "s.sh")
    with open(path, "w") as fh:
        fh.write(body)
    p = subprocess.run([sys.executable, "-m", "psh", path],
                       cwd=d, env=env, capture_output=True, text=True,
                       timeout=60)
    return p.stdout, p.stderr, p.returncode


def test_missing_input_file_has_line_prefix():
    out, err, rc = run_psh_c("cat <nope")
    assert "line 1: nope: No such file or directory" in err, err


def test_missing_input_builtin_has_line_prefix():
    out, err, rc = run_psh_c("read x <nope")
    assert "line 1: nope: No such file or directory" in err, err


def test_bad_fd_dup_source_has_line_prefix():
    out, err, rc = run_psh_c("cat <&9")
    assert "line 1: 9: Bad file descriptor" in err, err


def test_write_to_closed_fd_has_line_prefix():
    out, err, rc = run_psh_c("exec 3>&-; /bin/echo x >&3")
    assert "line 1: 3: Bad file descriptor" in err, err


def test_compound_bad_fd_has_line_prefix():
    out, err, rc = run_psh_c("exec 3>/dev/null; { echo hi; } 3>&- 4>&3")
    assert "line 1: 3: Bad file descriptor" in err, err


def test_failed_exec_redirect_has_line_prefix():
    out, err, rc = run_psh_c("exec 3>/no/such/dir/x")
    assert "line 1: /no/such/dir/x: No such file or directory" in err, err


def test_c1_expanded_input_procsub_filename_has_line_prefix():
    # C1: the expanded '<(echo evil)' is a FILENAME; ENOENT diagnostic carries
    # the location, and never runs `echo evil`.
    out, err, rc = run_psh_c("x='<(echo evil)'; cat < \"$x\"")
    assert "line 1: <(echo evil): No such file or directory" in err, err
    assert "evil" not in out, out


def test_multiline_c_reports_correct_line():
    out, err, rc = run_psh_c("echo a\ncat <nope")
    assert out == "a\n", (out, err)
    assert "line 2: nope: No such file or directory" in err, err


def test_script_mode_uses_scriptname_and_line():
    out, err, rc = run_psh_script("echo a\ncat <nope\necho b\n")
    assert "s.sh: line 2: nope: No such file or directory" in err, err
    assert out == "a\nb\n", (out, err)
