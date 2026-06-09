"""
Tests for heredocs larger than the kernel pipe buffer.

Regression guard: heredoc/here-string content used to be written in full
into an os.pipe() before any reader existed, deadlocking the shell for
bodies past the pipe capacity (~64KB). Content now goes through an
anonymous temp file, like bash.
"""

import subprocess
import sys

import pytest


def run_psh(script, timeout=15):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, timeout=timeout)


class TestLargeHeredocs:
    @pytest.mark.parametrize('size', [1000, 130000, 300000])
    def test_heredoc_size_to_builtin(self, size):
        body = 'x' * size
        script = f"wc -c <<'EOF'\n{body}\nEOF"
        result = run_psh(script)
        assert result.returncode == 0
        assert int(result.stdout.split()[0]) == size + 1  # body + newline

    def test_large_heredoc_to_external_command(self):
        body = 'y' * 130000
        script = f"/usr/bin/wc -c <<'EOF'\n{body}\nEOF"
        result = run_psh(script)
        assert result.returncode == 0
        assert int(result.stdout.split()[0]) == 130001

    def test_large_heredoc_content_integrity(self):
        """The content must arrive intact, not just the right size."""
        lines = [f'line-{i:06d}' for i in range(8000)]  # ~88KB
        body = '\n'.join(lines)
        script = f"tail -1 <<'EOF'\n{body}\nEOF"
        result = run_psh(script)
        assert result.stdout.strip() == 'line-007999'

    def test_small_heredoc_expansion_still_works(self):
        result = run_psh('x=val; cat <<EOF\ngot $x\nEOF')
        assert result.stdout == 'got val\n'

    def test_quoted_delimiter_still_literal(self):
        result = run_psh("x=val; cat <<'EOF'\ngot $x\nEOF")
        assert result.stdout == 'got $x\n'

    def test_large_herestring(self):
        body = 'z' * 130000
        result = run_psh(f'wc -c <<<"{body}"')
        assert result.returncode == 0
        assert int(result.stdout.split()[0]) == 130001
