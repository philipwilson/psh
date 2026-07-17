"""`set -u` violation exit code: 127 for -c, 1 for a script file (Tier 3, M13).

bash exits 127 on a ``set -u`` unbound-variable abort ONLY for ``-c``; a script
file (and a non-interactive shell otherwise) exits 1. psh used 127 for the
script-file case too. The exit code is now command-mode-dependent.

(The remaining sub-issue — a piped-stdin shell should ABORT on the violation
rather than continue — is tracked separately; this pins the exit code.)
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def run_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def run_bash_c(cmd):
    return subprocess.run([BASH, '-c', cmd], capture_output=True, text=True)


def run_script(tmp_path, body):
    script = tmp_path / "s.sh"
    script.write_text(body)
    return subprocess.run([sys.executable, '-m', 'psh', str(script)],
                          capture_output=True, text=True)


def run_bash_script(tmp_path, body):
    script = tmp_path / "b.sh"
    script.write_text(body)
    return subprocess.run([BASH, str(script)], capture_output=True, text=True)


def test_dash_c_exits_127():
    r = run_c('set -u; echo $UNSET_VAR; echo AFTER')
    assert r.returncode == 127
    assert "AFTER" not in r.stdout            # aborts
    assert "unbound variable" in r.stderr


def test_dash_c_matches_bash():
    cmd = 'set -u; echo $UNSET_VAR'
    assert run_c(cmd).returncode == run_bash_c(cmd).returncode == 127


def test_script_file_exits_1(tmp_path):
    r = run_script(tmp_path, 'set -u\necho $UNSET_VAR\necho AFTER\n')
    assert r.returncode == 1                  # NOT 127
    assert "AFTER" not in r.stdout            # aborts
    assert "unbound variable" in r.stderr


def test_script_file_matches_bash(tmp_path):
    body = 'set -u\necho $UNSET_VAR\n'
    assert run_script(tmp_path, body).returncode == \
        run_bash_script(tmp_path, body).returncode == 1


def test_set_u_with_defined_variable_ok():
    r = run_c('set -u; x=5; echo $x')
    assert r.returncode == 0
    assert r.stdout == "5\n"
