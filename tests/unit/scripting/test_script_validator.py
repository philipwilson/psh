"""Unit tests for ScriptValidator.is_binary_file (reappraisal #15 I2).

Binary means a NUL byte before the first newline (bash's rule); only regular
files are sniffed — pipes/FIFOs/devices must never be opened here, since
reading them would consume script bytes the real open is about to read.
"""
import os
import threading


def is_binary(shell, path) -> bool:
    return shell.script_manager.script_validator.is_binary_file(str(path))


class TestBinaryRule:
    def test_nul_in_first_line_is_binary(self, shell, tmp_path):
        p = tmp_path / 'bin'
        p.write_bytes(b'\x7fELF\x00\x00junk')
        assert is_binary(shell, p) is True

    def test_nul_after_first_newline_is_not_binary(self, shell, tmp_path):
        p = tmp_path / 'mixed.sh'
        p.write_bytes(b'echo hi\n\x00\x00')
        assert is_binary(shell, p) is False

    def test_plain_script_is_not_binary(self, shell, tmp_path):
        p = tmp_path / 's.sh'
        p.write_text('echo hi\n')
        assert is_binary(shell, p) is False

    def test_high_bytes_are_not_binary(self, shell, tmp_path):
        # UTF-8 (CJK) and Latin-1 content must run; >=0x80 is not a marker.
        p = tmp_path / 'cjk.sh'
        p.write_bytes('# 中文注释\n'.encode('utf-8') * 50 + b'echo done\n')
        assert is_binary(shell, p) is False
        p.write_bytes(b'# caf\xe9 latin-1\necho ok\n')
        assert is_binary(shell, p) is False

    def test_empty_file_is_not_binary(self, shell, tmp_path):
        p = tmp_path / 'empty.sh'
        p.write_bytes(b'')
        assert is_binary(shell, p) is False


class TestNonRegularFilesAreNotSniffed:
    def test_fifo_is_not_opened(self, shell, tmp_path):
        # Opening a writer-less FIFO would block forever; the validator must
        # answer from stat() alone. Run in a daemon thread so a regression
        # fails the test instead of hanging the suite.
        fifo = tmp_path / 'f'
        os.mkfifo(fifo)
        result = {}
        t = threading.Thread(target=lambda: result.update(v=is_binary(shell, fifo)),
                             daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), 'is_binary_file opened (blocked on) a FIFO'
        assert result['v'] is False

    def test_missing_file_reports_binary(self, shell, tmp_path):
        # Unreadable/unstatable falls back to True (validate_script_file has
        # already produced the right diagnostic for real error paths).
        assert is_binary(shell, tmp_path / 'nope') is True
