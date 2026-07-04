"""Child processes inherit redirect fds (reappraisal #18 T1-6, H5).

When Python's ``open()`` for a redirect happened to land exactly on the target
fd, the fd-preserving shortcut skipped ``dup2`` — but ``dup2`` is what clears
``O_CLOEXEC`` (Python opens fds non-inheritable by default). So the fd stayed
CLOEXEC and a forked child couldn't inherit it: ``cat /dev/fd/3 3<data`` saw
EBADF where bash reads the file. The fix clears CLOEXEC in that shortcut so it
is behaviorally identical to the ``dup2`` path.

These run psh in a SUBPROCESS (external children + real fds; this directory is
auto-marked ``serial`` by path). Every expected value is bash 5.2's output for
the same script. PYTHONPATH pins THIS checkout (see run_psh).
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_psh(script, cwd):
    env = {**os.environ, 'PYTHONPATH': str(_REPO_ROOT)}
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, cwd=cwd, timeout=10, env=env)


def write(cwd, name, content):
    with open(os.path.join(cwd, name), 'w') as f:
        f.write(content)


def read(cwd, name):
    with open(os.path.join(cwd, name)) as f:
        return f.read()


class TestChildInheritsInputFd:
    def test_external_reads_dev_fd_3(self, temp_dir):
        write(temp_dir, 'data', 'hello-from-fd3\n')
        result = run_psh('cat /dev/fd/3 3<data', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'hello-from-fd3\n'
        assert result.stderr == ''

    def test_external_reads_two_inherited_fds(self, temp_dir):
        write(temp_dir, 'a', 'aaa\n')
        write(temp_dir, 'b', 'bbb\n')
        result = run_psh('paste /dev/fd/3 /dev/fd/4 3<a 4<b', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'aaa\tbbb\n'

    def test_exec_opened_input_fd_inherited(self, temp_dir):
        write(temp_dir, 'data', 'hello-from-fd3\n')
        result = run_psh('exec 3<data; cat /dev/fd/3', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'hello-from-fd3\n'

    def test_reopen_stdin_after_close_is_inherited(self, temp_dir):
        # `exec <&-; exec <data; cat`: the reopened stdin (fd 0) must carry
        # into the forked cat.
        write(temp_dir, 'data', 'hello-from-fd3\n')
        result = run_psh('exec <&-; exec <data; cat', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'hello-from-fd3\n'


class TestChildInheritsOutputFd:
    def test_exec_opened_output_fd_inherited(self, temp_dir):
        result = run_psh("exec 3>o3; sh -c 'echo written >&3'", temp_dir)
        assert result.returncode == 0
        assert read(temp_dir, 'o3') == 'written\n'


class TestNamedFdStillWorks:
    """The `{var}>` (F_DUPFD) path never hit the shortcut — pin it stays sound."""

    def test_named_output_fd_child_inherits(self, temp_dir):
        result = run_psh('exec {v}>o; sh -c "echo kid >&$v"; cat o', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'kid\n'
        assert read(temp_dir, 'o') == 'kid\n'

    def test_named_input_fd_read(self, temp_dir):
        write(temp_dir, 'data', 'hello-from-fd3\n')
        result = run_psh(
            'exec {v}<data; read line <&$v; echo "got:$line"', temp_dir)
        assert result.returncode == 0
        assert result.stdout == 'got:hello-from-fd3\n'
