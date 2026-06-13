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
    def test_eof_partial_line_succeeds(self):
        """psh quirk: newline delimiter with partial input and no trailing
        newline keeps the data AND exits 0 (bash would exit 1). Only a
        truly-empty EOF reports exit 1 (see below)."""
        r = _psh('read v; echo "rc=$? [$v]"', 'abc')
        assert r.stdout == "rc=0 [abc]\n"

    def test_eof_empty_exit_1(self):
        r = _psh('read v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_plain_custom_delim_eof_empty_exit_1(self):
        """Plain -d (no -n/-s) with empty input reports EOF (exit 1), like the
        newline case — it routes through _read_normal."""
        r = _psh('read -d : v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=1 []\n"

    def test_n_custom_delim_eof_no_data_succeeds(self):
        """Quirk: -n with a custom delimiter and empty input exits 0 (not 1),
        routing through the _read_special branch which returns '' for a
        non-newline delimiter rather than None."""
        r = _psh('read -n 3 -d : v; echo "rc=$? [$v]"', '')
        assert r.stdout == "rc=0 []\n"

    def test_custom_delim_partial_eof_succeeds(self):
        r = _psh('read -d : v; echo "rc=$? [$v]"', 'foo')
        assert r.stdout == "rc=0 [foo]\n"

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

    def test_timeout_partial_eof_succeeds(self):
        """Quirk: under -t, once input is ready the plain (no -n) path reads to
        EOF and a partial line still exits 0."""
        r = _psh('read -t 5 v; echo "rc=$? [$v]"', 'ab')
        assert r.stdout == "rc=0 [ab]\n"

    def test_backslash_newline_drops_remainder(self):
        """psh quirk: a trailing backslash-newline is consumed as line
        continuation by _process_escapes, but read does NOT fetch the next
        line at the fd level, so the remainder after the newline is dropped."""
        r = _psh('read v; echo "rc=$? [$v]"', 'foo\\\nbar\n')
        assert r.stdout == "rc=0 [foo]\n"

    def test_raw_mode_preserves_backslash(self):
        r = _psh('read -r v; echo "rc=$? [$v]"', 'a\\tb\n')
        assert r.stdout == "rc=0 [a\\tb]\n"
