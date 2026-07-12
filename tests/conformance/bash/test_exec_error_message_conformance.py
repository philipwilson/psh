"""
Conformance tests for exec-failure diagnostics.

psh leaked Python's OSError repr — `psh: ./x: [Errno 13] Permission denied:
'./x'` — where bash prints the bare strerror `./x: Permission denied`
(reappraisal #13 MED). It also reported a directory target as "Permission
denied" (macOS exec returns EACCES) where bash reports "Is a directory".

Compared by exit code + stderr substring: the `bash: line N:` prefix differs
from psh's `psh:` by design, and psh must NOT leak the `[Errno N] ...: '...'`
Python repr.

Verified against bash 5.2.
"""

import os
import subprocess
import sys

from conformance_framework import find_bash


def _run(shell_argv, cmd, cwd):
    return subprocess.run(shell_argv + ['-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


class TestExecErrorMessages:
    def test_permission_denied(self, tmp_path):
        f = tmp_path / 'noexec.sh'
        f.write_text('#!/bin/sh\necho hi\n')
        os.chmod(f, 0o644)  # not executable
        psh = _run([sys.executable, '-m', 'psh'], './noexec.sh', str(tmp_path))
        bash = _run([find_bash()], './noexec.sh', str(tmp_path))
        assert psh.returncode == bash.returncode == 126
        assert 'Permission denied' in psh.stderr
        assert '[Errno' not in psh.stderr   # no Python repr leak

    def test_is_a_directory(self, tmp_path):
        d = tmp_path / 'adir'
        d.mkdir()
        psh = _run([sys.executable, '-m', 'psh'], './adir', str(tmp_path))
        bash = _run([find_bash()], './adir', str(tmp_path))
        assert psh.returncode == bash.returncode == 126
        assert 'Is a directory' in psh.stderr
        assert '[Errno' not in psh.stderr

    def test_command_not_found_unaffected(self, tmp_path):
        psh = _run([sys.executable, '-m', 'psh'], 'nosuchcmd_xyz', str(tmp_path))
        bash = _run([find_bash()], 'nosuchcmd_xyz', str(tmp_path))
        assert psh.returncode == bash.returncode == 127
        assert 'command not found' in psh.stderr
