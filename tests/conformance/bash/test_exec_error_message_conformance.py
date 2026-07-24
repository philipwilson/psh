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

from shell_oracle import is_comparable, run_bash, run_psh


def _run(runner, cmd, cwd):
    r = runner(['-c', cmd], cwd=cwd)
    assert is_comparable(r), r
    return r


class TestExecErrorMessages:
    def test_permission_denied(self, tmp_path):
        f = tmp_path / 'noexec.sh'
        f.write_text('#!/bin/sh\necho hi\n')
        os.chmod(f, 0o644)  # not executable
        psh = _run(run_psh, './noexec.sh', str(tmp_path))
        bash = _run(run_bash, './noexec.sh', str(tmp_path))
        assert psh.returncode == bash.returncode == 126
        assert 'Permission denied' in psh.stderr
        assert '[Errno' not in psh.stderr   # no Python repr leak

    def test_is_a_directory(self, tmp_path):
        d = tmp_path / 'adir'
        d.mkdir()
        psh = _run(run_psh, './adir', str(tmp_path))
        bash = _run(run_bash, './adir', str(tmp_path))
        assert psh.returncode == bash.returncode == 126
        assert 'Is a directory' in psh.stderr
        assert '[Errno' not in psh.stderr

    def test_command_not_found_unaffected(self, tmp_path):
        psh = _run(run_psh, 'nosuchcmd_xyz', str(tmp_path))
        bash = _run(run_bash, 'nosuchcmd_xyz', str(tmp_path))
        assert psh.returncode == bash.returncode == 127
        assert 'command not found' in psh.stderr
