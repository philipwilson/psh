"""`psh FILE` treats a `#!...` first line as a comment, not a dispatch.

Pins H4 (reappraisal #7): when a shell is invoked to interpret a file
(`psh script.sh`), POSIX/bash/dash treat the shebang as an ordinary
comment and run the file as shell. psh used to re-dispatch the file to the
interpreter named in the shebang (so a `#!/usr/bin/python3` script was fed
to python3, producing a SyntaxError). The kernel handles `#!` only when a
file is exec'd directly as a command — which psh still supports via the
external-command path (`psh -c './x.sh'`), and that path is exercised here
too to show it is independent of this change.
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    os.chmod(p, 0o755)
    return str(p)


def run_psh_file(path):
    return subprocess.run([sys.executable, '-m', 'psh', path],
                          capture_output=True, text=True)


def run_bash_file(path):
    return subprocess.run([BASH, path], capture_output=True, text=True)


class TestShebangIsCommentForExplicitFile:
    def test_python_shebang_runs_as_shell(self, tmp_path):
        """A `#!/usr/bin/python3` shebang is a comment; the body runs as
        shell, matching bash (no SyntaxError, no python dispatch)."""
        path = _write(tmp_path, 'x.sh', '#!/usr/bin/python3\necho hi\n')
        psh = run_psh_file(path)
        assert psh.returncode == 0
        assert psh.stdout == 'hi\n'
        assert 'SyntaxError' not in psh.stderr
        assert psh.stdout == run_bash_file(path).stdout

    def test_cat_shebang_does_not_dispatch_to_cat(self, tmp_path):
        """A `#!/bin/cat` shebang must NOT echo the file contents; the body
        runs as shell."""
        path = _write(tmp_path, 'y.sh', '#!/bin/cat\necho catshebang\n')
        psh = run_psh_file(path)
        assert psh.returncode == 0
        assert psh.stdout == 'catshebang\n'
        assert psh.stdout == run_bash_file(path).stdout

    def test_no_shebang_runs_normally(self, tmp_path):
        path = _write(tmp_path, 'z.sh', 'echo noshebang\n')
        psh = run_psh_file(path)
        assert psh.returncode == 0
        assert psh.stdout == 'noshebang\n'

    def test_env_psh_shebang_runs_as_shell(self, tmp_path):
        path = _write(tmp_path, 'w.sh', '#!/usr/bin/env psh\necho pshscript\n')
        psh = run_psh_file(path)
        assert psh.returncode == 0
        assert psh.stdout == 'pshscript\n'

    def test_shebang_line_args_are_comment(self, tmp_path):
        """Even with interpreter args, the whole first line is a comment."""
        path = _write(tmp_path, 'a.sh', '#!/bin/sh -e\necho body\n')
        psh = run_psh_file(path)
        assert psh.returncode == 0
        assert psh.stdout == 'body\n'


class TestExecPathStillRespectsKernelShebang:
    """The independent exec path (`psh -c './x.sh'`) still honors the
    shebang via the kernel — H4 only changed the explicit-FILE path."""

    @pytest.mark.serial
    def test_exec_path_honors_cat_shebang(self, tmp_path):
        _write(tmp_path, 'y.sh', '#!/bin/cat\necho catshebang\n')
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', './y.sh'],
            cwd=str(tmp_path), capture_output=True, text=True)
        # The kernel runs /bin/cat on the file, so the file CONTENTS are
        # echoed (shebang line included) — proving the exec path still
        # dispatches via the shebang, unlike the explicit-FILE path.
        assert result.returncode == 0
        assert result.stdout == '#!/bin/cat\necho catshebang\n'
