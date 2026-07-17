"""Non-seekable script sources must not be consumed by the binary sniff
(reappraisal #15 I2).

is_binary_file used to open and read 1KB of the script before FileInput
re-opened it: for pipes/FIFOs/process substitutions the content was consumed
and the script silently no-oped rc=0 (or deadlocked, for a FIFO whose writer
was gone). It also counted every byte >= 0x80 as non-printable, so a
CJK-comment UTF-8 script was rejected as "binary" rc=126.

Now only regular files are sniffed, and the binary test is bash's rule: a NUL
byte before the first newline. Pinned against bash 5.2
(tmp/truth_table_r15_i.py).
"""
import os
import subprocess
import sys
from pathlib import Path

from shell_oracle import resolve_bash

BASH = resolve_bash().path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}


def run_psh(*args, stdin_input=None, stdin_file=None, cwd=None):
    kwargs = dict(capture_output=True, text=True, timeout=10, cwd=cwd, env=ENV)
    argv = [sys.executable, '-m', 'psh', *args]
    if stdin_file is not None:
        with open(stdin_file) as f:
            return subprocess.run(argv, stdin=f, **kwargs)
    return subprocess.run(argv, input=stdin_input or '', **kwargs)


class TestNonSeekableSources:
    def test_process_substitution_script_operand(self):
        # The <(...) fd comes from an OUTER shell; psh must not pre-read it.
        result = subprocess.run(
            [BASH, '-c', f'{sys.executable} -m psh <(echo "echo hello")'],
            capture_output=True, text=True, timeout=10, env=ENV)
        assert result.returncode == 0
        assert result.stdout == 'hello\n'
        assert result.stderr == ''

    def test_piped_dev_stdin_script(self):
        result = run_psh('/dev/stdin', stdin_input='echo hi\n')
        assert result.returncode == 0
        assert result.stdout == 'hi\n'

    def test_source_piped_dev_stdin(self):
        result = run_psh('-c', 'source /dev/stdin', stdin_input='echo srcd\n')
        assert result.returncode == 0
        assert result.stdout == 'srcd\n'

    def test_source_process_substitution(self):
        # The completion-loading idiom: source <(...) inside psh itself.
        result = run_psh('-c', 'source <(echo "echo pshello")')
        assert result.returncode == 0
        assert result.stdout == 'pshello\n'

    def test_fifo_as_script(self, tmp_path):
        fifo = str(tmp_path / 'fifo')
        os.mkfifo(fifo)
        writer = subprocess.Popen([BASH, '-c', f'echo "echo fifod" > {fifo}'])
        try:
            result = run_psh(fifo)
        finally:
            try:
                writer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                writer.kill()
        assert result.returncode == 0
        assert result.stdout == 'fifod\n'

    def test_source_fifo(self, tmp_path):
        fifo = str(tmp_path / 'fifo')
        os.mkfifo(fifo)
        writer = subprocess.Popen([BASH, '-c', f'echo "echo sfifod" > {fifo}'])
        try:
            result = run_psh('-c', f'source {fifo}')
        finally:
            try:
                writer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                writer.kill()
        assert result.returncode == 0
        assert result.stdout == 'sfifod\n'

    def test_dev_stdin_from_regular_file(self, tmp_path):
        # On macOS /dev/stdin opens as a dup() SHARING the fd-0 offset, so
        # even a seekable sniff must rewind or the real open starts at 1KB.
        script = tmp_path / 's.sh'
        script.write_text('echo viafile\n')
        result = run_psh('/dev/stdin', stdin_file=str(script))
        assert result.returncode == 0
        assert result.stdout == 'viafile\n'


class TestBinaryDetection:
    def test_cjk_heavy_script_is_not_binary(self, tmp_path):
        script = tmp_path / 'cjk.sh'
        script.write_text('# 这是一个很长的中文注释，用来测试非ASCII内容。\n' * 20
                          + 'echo done\n', encoding='utf-8')
        result = run_psh(str(script))
        assert result.returncode == 0
        assert result.stdout == 'done\n'
        assert result.stderr == ''

    def test_nul_in_first_line_is_binary_126(self, tmp_path):
        binary = tmp_path / 'bin1'
        binary.write_bytes(b'\x7fELF\x00\x00\x01junk')
        result = run_psh(str(binary))
        assert result.returncode == 126
        assert 'cannot execute binary file' in result.stderr

    def test_nul_after_first_newline_is_not_binary(self, tmp_path):
        # bash's rule: only a NUL BEFORE the first newline marks a binary.
        mixed = tmp_path / 'mixed.sh'
        mixed.write_bytes(b'echo textish\n\x00\x00\x00')
        result = run_psh(str(mixed))
        assert result.returncode != 126
        assert result.stdout == 'textish\n'


class TestValidationErrors:
    def test_missing_script_127(self, tmp_path):
        result = run_psh(str(tmp_path / 'nope.sh'))
        assert result.returncode == 127
        assert 'No such file or directory' in result.stderr

    def test_directory_126(self, tmp_path):
        result = run_psh(str(tmp_path))
        assert result.returncode == 126
        assert 'Is a directory' in result.stderr

    def test_unreadable_126(self, tmp_path):
        script = tmp_path / 'noread.sh'
        script.write_text('echo x\n')
        os.chmod(script, 0)
        try:
            result = run_psh(str(script))
        finally:
            os.chmod(script, 0o644)
        assert result.returncode == 126
        assert 'Permission denied' in result.stderr
