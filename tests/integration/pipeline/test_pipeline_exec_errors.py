"""Exec failures inside pipelines (bash-pinned).

Regression: a command-not-found in a pipeline printed a raw Python OSError
(`psh: nosuchcmd: [Errno 2] No such file or directory: b'...'`) because the
in-pipeline inline-exec branch lacked the fork path's FileNotFoundError /
PermissionError handling. Both paths now share report_exec_failure():
"command not found" + 127 for a missing command, the OS error + 126
otherwise.

bash reference behavior (verified):
- `nosuchcmd | cat; echo $?`  → stderr "...: command not found", rc 0
  (the pipeline's status is cat's)
- `cat /dev/null | nosuchcmd; echo $?` → rc 127
- non-executable file in a pipeline → "Permission denied", rc 126

Run via subprocess: pipelines fork, and the failing child writes to fd 2.
"""

import os
import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True, cwd=cwd)


class TestPipelineCommandNotFound:
    def test_not_found_first_message_and_status(self):
        result = run_psh('nosuchcmd_zz123 | cat; echo rc=$?')
        assert 'psh: line 1: nosuchcmd_zz123: command not found' in result.stderr
        assert '[Errno' not in result.stderr
        # The pipeline's exit status is cat's (0), like bash
        assert result.stdout == 'rc=0\n'

    def test_not_found_last_exits_127(self):
        result = run_psh('cat /dev/null | nosuchcmd_zz123; echo rc=$?')
        assert 'psh: line 1: nosuchcmd_zz123: command not found' in result.stderr
        assert '[Errno' not in result.stderr
        assert result.stdout == 'rc=127\n'

    def test_pipeline_message_matches_single_command_message(self):
        """The in-pipeline diagnostic must be identical to psh's own
        non-pipeline command-not-found message."""
        single = run_psh('nosuchcmd_zz123')
        piped = run_psh('nosuchcmd_zz123 | cat')
        assert single.stderr == piped.stderr
        assert single.returncode == 127


class TestPipelineNotExecutable:
    def test_non_executable_in_pipeline_exits_126(self, tmp_path):
        script = tmp_path / 'notexec.sh'
        script.write_text('#!/bin/sh\necho hi\n')
        os.chmod(script, 0o644)
        result = run_psh('cat /dev/null | ./notexec.sh; echo rc=$?',
                         cwd=tmp_path)
        assert result.stdout == 'rc=126\n'
        assert 'Permission denied' in result.stderr
        assert 'Traceback' not in result.stderr

    def test_non_executable_pipeline_message_matches_single(self, tmp_path):
        script = tmp_path / 'notexec.sh'
        script.write_text('#!/bin/sh\necho hi\n')
        os.chmod(script, 0o644)
        single = run_psh('./notexec.sh', cwd=tmp_path)
        piped = run_psh('cat /dev/null | ./notexec.sh', cwd=tmp_path)
        assert single.returncode == 126
        assert piped.returncode == 126
        assert single.stderr == piped.stderr
