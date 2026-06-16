"""Regression tests for the unified read character-loop (read_builtin._read_chars).

These pin the non-obvious behaviours that the three original read variants
(_read_normal / _read_special / _read_with_timeout) did NOT share, so a future
refactor of the single shared loop cannot silently change them. Each case was
verified against bash where bash has a defined answer; psh-specific quirks are
labelled as such. Subprocess is used so real OS pipes drive the fd-level paths.
"""
import subprocess
import sys


def _psh(script, stdin):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        input=stdin, capture_output=True, text=True)


class TestUnifiedReadQuirks:
    def test_eof_partial_line_reports_failure(self):
        """R13.B: newline delimiter with a partial last line (no trailing
        newline) keeps the data but exits 1, matching bash — EOF before the
        delimiter is a read failure even though the variable is assigned."""
        r = _psh('read v; echo "rc=$? [$v]"', 'abc')
        assert r.stdout == "rc=1 [abc]\n"

    def test_eof_empty_exit_1(self):
        r = _psh('read v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_empty_eof_clears_variable(self):
        """R13.B: at empty EOF read still ASSIGNS (clears) the variable and
        exits 1 (bash); previously psh left a preset value untouched."""
        r = _psh('v=PRESET; read v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_partial_multivar_reports_failure(self):
        """R13.B: a partial last line splits across the variables but exits 1."""
        r = _psh('read x y; echo "rc=$? [$x][$y]"', 'a b')
        assert r.stdout == "rc=1 [a][b]\n"

    def test_plain_custom_delim_eof_empty_exit_1(self):
        """Plain -d (no -n/-s) with empty input reports EOF (exit 1), like the
        newline case — it routes through _read_normal."""
        r = _psh('read -d : v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_n_custom_delim_eof_no_data_reports_failure(self):
        """R13.B: -n with a custom delimiter and empty input now exits 1
        (EOF before the delimiter / char limit), matching bash. Previously a
        psh quirk returned 0 for a non-newline delimiter."""
        r = _psh('read -n 3 -d : v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_custom_delim_partial_eof_reports_failure(self):
        """R13.B: custom delimiter, partial input, EOF before delimiter →
        keep data, exit 1 (bash)."""
        r = _psh('read -d : v; echo "rc=$? [$v]"', 'foo')
        assert r.stdout == "rc=1 [foo]\n"

    def test_n_limit_stops_exactly(self):
        r = _psh('read -n 2 v; echo "rc=$? [$v]"', 'abcd')
        assert r.stdout == "rc=0 [ab]\n"

    def test_n_zero_reads_nothing_succeeds(self):
        r = _psh('read -n 0 v; echo "rc=$? [$v]"', 'abc')
        assert r.stdout == "rc=0 []\n"

    def test_n_with_custom_delim_stops_at_delim(self):
        r = _psh('read -n 10 -d : v; echo "rc=$? [$v]"', 'ab:cd')
        assert r.stdout == "rc=0 [ab]\n"

    def test_n_newline_delim_eof_empty_exit_1(self):
        """-n with newline delimiter and immediate EOF still reports EOF (1)."""
        r = _psh('read -n 3 v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_silent_non_tty_reads_line(self):
        r = _psh('read -s v; echo "rc=$? [$v]"', 'secret\n')
        assert r.stdout == "rc=0 [secret]\n"

    def test_timeout_data_in_time(self):
        r = _psh('read -t 5 v; echo "rc=$? [$v]"', 'hi\n')
        assert r.stdout == "rc=0 [hi]\n"

    def test_timeout_n_data_in_time(self):
        r = _psh('read -t 5 -n 2 v; echo "rc=$? [$v]"', 'abcd\n')
        assert r.stdout == "rc=0 [ab]\n"

    def test_timeout_partial_eof_reports_failure(self):
        """R13.B: under -t, once input is ready the plain (no -n) path reads to
        EOF; a partial line keeps the data but exits 1 (bash) — timeout 142 is
        reserved for the budget actually expiring."""
        r = _psh('read -t 5 v; echo "rc=$? [$v]"', 'ab')
        assert r.stdout == "rc=1 [ab]\n"

    def test_backslash_newline_line_continuation(self):
        """A trailing backslash-newline is line continuation (bash): both are
        removed and reading continues onto the next line (foo + bar)."""
        r = _psh('read v; echo "rc=$? [$v]"', 'foo\\\nbar\n')
        assert r.stdout == "rc=0 [foobar]\n"

    def test_raw_mode_preserves_backslash(self):
        r = _psh('read -r v; echo "rc=$? [$v]"', 'a\\tb\n')
        assert r.stdout == "rc=0 [a\\tb]\n"


class TestReadFdAndPoll:
    """R14.A: `read -u FD` reads from a file descriptor; `read -t 0` polls."""

    def test_read_u_from_file_fd(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("line-from-fd\nsecond\n")
        r = _psh(f'exec 3< {f}; read -u 3 x; read -u 3 y; echo "$x/$y"', '')
        assert r.stdout == "line-from-fd/second\n"

    def test_read_u_redirect_on_command(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("via-redirect\n")
        r = _psh(f'read -u 3 x 3< {f}; echo "[$x]"', '')
        assert r.stdout == "[via-redirect]\n"

    def test_read_u_invalid_spec_rc1(self):
        r = _psh('read -u abc x', '')
        assert r.returncode == 1
        assert 'invalid file descriptor specification' in r.stderr

    def test_read_u_unopened_fd_rc1(self):
        r = _psh('read -u 9 x', '')
        assert r.returncode == 1
        assert 'invalid file descriptor' in r.stderr

    def test_read_t0_input_available(self):
        # Data on stdin -> poll succeeds, reads nothing (x stays empty).
        r = _psh('read -t 0 x; echo "rc=$? [$x]"', 'data-here')
        assert r.stdout == "rc=0 []\n"

    def test_read_t0_eof_is_readable(self):
        # /dev/null is at EOF, which select reports readable -> rc 0 (bash).
        r = _psh('read -t 0 x </dev/null; echo "rc=$?"', '')
        assert r.stdout == "rc=0\n"
