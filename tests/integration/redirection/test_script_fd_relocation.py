"""
The script-reading descriptor must not collide with user fds (reappraisal #14
H3, then #17 io MED-2; the lazy reader of campaign I2 / #20 H14).

A plain open() landed the script file on fd 3, so a script doing `exec 3>&-`
or the classic `exec 3>&1 1>&2 2>&3 3>&-` stdout/stderr swap clobbered the fd
psh read the script from — at close it raised a spurious
"[Errno 9] Bad file descriptor" and exit 1. The first fix relocated the fd
via F_DUPFD_CLOEXEC to >= 10 — which parked it EXACTLY on bash's `{var}`
named-fd allocation base, so `exec {fd}>/dev/null` returned 11 (bash: 10) and
a script touching fd 10 itself hit the same spurious EBADF.

Campaign I2 (#20 H14) made the SCRIPT-FILE argument LAZY (block-buffered), so
the descriptor is now LIVE for the script's lifetime rather than eagerly read
and closed. It is relocated to a HIGH CLOEXEC slot (F_DUPFD_CLOEXEC from fd
255, bash's script-fd convention): out of the swap idiom's fds 0-9, out of the
`{v}` first-free->=10 numbering (F_DUPFD skips the open slot), and CLOEXEC so
children/exec'd images never inherit it. A temporary redirect to its number
save/restores it; a PERMANENT `exec` redirect to its number relocates the
reader first (cannot clobber — bash owns its fd 255 identically). Every case
below stays bash-verified under the lazy reader.

Permanent-fd / exec redirection in scripts -> always run psh in a subprocess.
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def run_psh_script(tmp_path, script, name="case.sh"):
    path = tmp_path / name
    path.write_text(script)
    return subprocess.run([sys.executable, '-m', 'psh', str(path)],
                          capture_output=True, text=True)


def run_bash_script(tmp_path, script):
    path = tmp_path / "case_bash.sh"
    path.write_text(script)
    return subprocess.run([BASH, str(path)], capture_output=True, text=True)


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


def test_named_fd_allocates_10_in_script_mode(tmp_path):
    # bash's {var} allocation base is 10; the old relocation parked psh's
    # script fd there, so `exec {fd}>/dev/null` answered 11.
    script = 'exec {fd}>/dev/null\necho $fd\nexec {fd}>&-\n'
    psh = run_psh_script(tmp_path, script)
    bash = run_bash_script(tmp_path, script)
    assert psh.stdout == bash.stdout == "10\n"
    assert psh.returncode == bash.returncode == 0


def test_two_named_fds_allocate_10_and_11(tmp_path):
    script = 'exec {a}>/dev/null {b}>/dev/null\necho $a $b\n'
    psh = run_psh_script(tmp_path, script)
    bash = run_bash_script(tmp_path, script)
    assert psh.stdout == bash.stdout == "10 11\n"


def test_script_can_use_fd10_explicitly(tmp_path):
    # `exec 10>f; ...; exec 10>&-` used to exit 1 with a spurious
    # "[Errno 9] Bad file descriptor" (FileInput's own fd sat on 10).
    out = tmp_path / "f10.out"
    script = f'exec 10>{out}\necho ten >&10\nexec 10>&-\ncat {out}\n'
    r = run_psh_script(tmp_path, script)
    assert r.returncode == 0
    assert r.stdout == "ten\n"
    assert "Bad file descriptor" not in r.stderr


def test_sourced_file_touching_fd10(tmp_path):
    inc = tmp_path / "inc10.sh"
    out = tmp_path / "inner10.out"
    inc.write_text(f'exec 10>{out}\necho from-inner >&10\nexec 10>&-\n')
    r = run_psh_script(tmp_path, f'. {inc}\ncat {out}\n')
    assert r.returncode == 0
    assert r.stdout == "from-inner\n"
    assert "Bad file descriptor" not in r.stderr
