"""
The script-reading descriptor must not collide with user fds (reappraisal #14 H3).

A plain open() landed the script file on fd 3, so a script doing `exec 3>&-`
or the classic `exec 3>&1 1>&2 2>&3 3>&-` stdout/stderr swap clobbered the fd
psh read the script from — at close it raised a spurious
"[Errno 9] Bad file descriptor" and exit 1. bash keeps its script fd >= 10;
FileInput now relocates via F_DUPFD_CLOEXEC. Verified against bash 5.2.

Permanent-fd / exec redirection in scripts -> always run psh in a subprocess.
"""

import subprocess
import sys


def run_psh_script(tmp_path, script, name="case.sh"):
    path = tmp_path / name
    path.write_text(script)
    return subprocess.run([sys.executable, '-m', 'psh', str(path)],
                          capture_output=True, text=True)


def run_bash_script(tmp_path, script):
    path = tmp_path / "case_bash.sh"
    path.write_text(script)
    return subprocess.run(['bash', str(path)], capture_output=True, text=True)


def test_exec_close_fd3_in_script(tmp_path):
    r = run_psh_script(tmp_path, 'exec 3>&-\necho hi\n')
    assert r.stdout == "hi\n"
    assert r.stderr == ""
    assert r.returncode == 0


def test_stdout_stderr_swap_idiom(tmp_path):
    script = 'exec 3>&1 1>&2 2>&3 3>&-\necho to-stderr\necho to-stdout\n'
    r = run_psh_script(tmp_path, script)
    assert r.returncode == 0
    assert "Bad file descriptor" not in r.stderr
    # stdout and stderr are swapped: both echoes land on the swapped channels.
    assert "to-stderr" in (r.stdout + r.stderr)


def test_exec_fd3_to_file_then_close(tmp_path):
    out = tmp_path / "out3.txt"
    script = f'exec 3>{out}\necho hi >&3\nexec 3>&-\ncat {out}\n'
    r = run_psh_script(tmp_path, script)
    assert r.returncode == 0
    assert r.stdout == "hi\n"
    assert "Bad file descriptor" not in r.stderr


def test_open_fd3_for_read(tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("the-line\n")
    script = f'exec 3<{data}\nread line <&3\necho "got: $line"\nexec 3<&-\n'
    r = run_psh_script(tmp_path, script)
    assert r.returncode == 0
    assert r.stdout == "got: the-line\n"


def test_matches_bash_swap_idiom(tmp_path):
    script = 'exec 3>&1 1>&2 2>&3 3>&-\necho A\necho B\n'
    psh = run_psh_script(tmp_path, script)
    bash = run_bash_script(tmp_path, script)
    assert psh.returncode == bash.returncode
    assert psh.stdout == bash.stdout
    assert psh.stderr == bash.stderr


def test_sourced_file_exec_close_fd3(tmp_path):
    inc = tmp_path / "inc.sh"
    inc.write_text('exec 3>&-\n')
    r = run_psh_script(tmp_path, f'. {inc}\necho after\n')
    assert r.returncode == 0
    assert r.stdout == "after\n"
    assert "Bad file descriptor" not in r.stderr
