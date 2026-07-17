"""`source` exit status for a directory / unreadable / binary file.

R18 T2-E (M-, LOW): psh's shared script validator returns 126 for a directory,
unreadable file, or binary — correct for the `psh file` INVOCATION path. bash's
`source` diverges: it returns 1 for a directory or unreadable file, reserving
126 for a binary file. `SourceBuiltin.execute` now remaps the non-binary
failures. Pinned against bash 5.2.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from shell_oracle import resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}

BASH = resolve_bash().path


def _source_rc_psh(path):
    # `-c 'source <path>'` exit status IS source's own status.
    return subprocess.run([sys.executable, '-m', 'psh', '-c', f'source {path}'],
                          capture_output=True, text=True, timeout=10,
                          env=ENV).returncode


def _source_rc_bash(path):
    return subprocess.run([BASH, '-c', f'source {path}'],
                          capture_output=True, text=True, timeout=10).returncode


def test_source_directory_returns_1(tmp_path):
    d = tmp_path / 'adir'
    d.mkdir()
    assert _source_rc_psh(str(d)) == 1


def test_source_unreadable_file_returns_1(tmp_path):
    f = tmp_path / 'noperm.sh'
    f.write_text('echo hi\n')
    f.chmod(0o000)
    try:
        assert _source_rc_psh(str(f)) == 1
    finally:
        f.chmod(0o644)


def test_source_binary_returns_126(tmp_path):
    # A regular file with a NUL before the first newline is "binary".
    f = tmp_path / 'bin.sh'
    f.write_bytes(b'\x7fELF\x00\x00binary\n')
    assert _source_rc_psh(str(f)) == 126


def test_source_nonexistent_returns_1(tmp_path):
    assert _source_rc_psh(str(tmp_path / 'nope.sh')) == 1


@pytest.mark.skipif(not BASH, reason="no bash available")
@pytest.mark.skipif(not os.path.exists('/bin/ls'), reason="no /bin/ls")
def test_source_rcs_match_bash(tmp_path):
    # Directory and unreadable file → 1; a real binary → 126; missing → 1.
    # (A real executable is used for the binary case: psh's and bash's NUL
    # heuristics agree there. They diverge only on tiny hand-crafted NUL
    # files — a binary-DETECTION corner outside this fix's scope.)
    d = tmp_path / 'adir2'
    d.mkdir()
    noperm = tmp_path / 'noperm2.sh'
    noperm.write_text('echo hi\n')
    noperm.chmod(0o000)
    nofile = tmp_path / 'nope2.sh'
    try:
        for path in (str(d), str(noperm), '/bin/ls', str(nofile)):
            assert _source_rc_psh(path) == _source_rc_bash(path), path
    finally:
        noperm.chmod(0o644)
