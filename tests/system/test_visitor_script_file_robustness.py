"""Analysis modes (`--validate` &c.) must read a script FILE like the executor.

Scripting appraisal 2026-07-07, finding #2. The analysis-mode file reader used a
bare ``open(path, 'r')`` (UTF-8-strict) and returned a flat ``1`` for a missing
file, diverging from the execution path in two ways:

  * (2a) a non-UTF-8-but-VALID script that ``psh script`` runs fine crashed the
    analysis with ``UnicodeDecodeError`` ("Error processing script: ...", rc 1);
  * (2b) a missing file returned 1 instead of the execution path's / ``bash -n``'s
    127 (and a directory/unreadable/binary file 126).

Both are fixed by routing the file read through the SAME pre-flight
``validate_script_file`` and ``FileInput`` (``errors='surrogateescape'``) the
executor uses. These drive the real CLI in a subprocess.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = str(Path(__file__).resolve().parents[2])
PSH = [sys.executable, "-m", "psh"]
MODES = ["--validate", "--format", "--metrics", "--security", "--lint"]


def _env():
    return dict(os.environ, PYTHONPATH=REPO_ROOT)


def _run(argv, cwd=None):
    return subprocess.run(argv, capture_output=True, cwd=cwd or REPO_ROOT,
                          env=_env(), timeout=20)


class TestNonUtf8ScriptValidates:
    def test_validate_non_utf8_but_valid(self, tmp_path):
        """A script with a raw non-UTF-8 byte executes fine, so --validate must
        accept it (rc 0), not crash with a decode error."""
        script = tmp_path / "s.sh"
        script.write_bytes(b"echo caf\xe9\n")
        # It executes cleanly...
        run = _run(PSH + [str(script)])
        assert run.returncode == 0, run.stderr
        # ...so --validate accepts it, no traceback, no decode error.
        val = _run(PSH + ["--validate", str(script)])
        assert val.returncode == 0, val.stderr
        assert b"Traceback" not in val.stderr
        assert b"codec can't decode" not in val.stderr
        assert b"No issues found" in val.stdout

    @pytest.mark.parametrize("mode", MODES)
    def test_all_modes_no_decode_crash(self, mode, tmp_path):
        """No analysis mode crashes on a non-UTF-8-but-valid script."""
        script = tmp_path / "s.sh"
        script.write_bytes(b"echo caf\xe9\n")
        r = _run(PSH + [mode, str(script)])
        assert b"Traceback" not in r.stderr, r.stderr
        assert b"codec can't decode" not in r.stderr, r.stderr


class TestAnalysisFileInvocationCodes:
    """--validate's file-invocation codes must match the execution path."""

    def test_missing_file_is_127(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.sh")
        exe = _run(PSH + [missing])
        val = _run(PSH + ["--validate", missing])
        assert exe.returncode == 127
        assert val.returncode == 127
        assert b"No such file or directory" in val.stderr

    def test_directory_is_126(self, tmp_path):
        d = str(tmp_path)
        exe = _run(PSH + [d])
        val = _run(PSH + ["--validate", d])
        assert exe.returncode == 126
        assert val.returncode == 126
        assert b"Is a directory" in val.stderr

    def test_valid_file_still_validates(self, tmp_path):
        script = tmp_path / "ok.sh"
        script.write_text("echo hi\nif true; then echo ok; fi\n")
        r = _run(PSH + ["--validate", str(script)])
        assert r.returncode == 0
        assert b"No issues found" in r.stdout
