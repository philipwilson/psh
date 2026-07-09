"""Regression tests for the unified read character-loop (read_builtin._read_chars).

These pin the non-obvious behaviours that the three original read variants
(_read_normal / _read_special / _read_with_timeout) did NOT share, so a future
refactor of the single shared loop cannot silently change them. Each case was
verified against bash where bash has a defined answer; psh-specific quirks are
labelled as such. Subprocess is used so real OS pipes drive the fd-level paths.
"""
import subprocess
import sys
import time


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

    # --- backslash-into-EOF: raw EOF (Case A) keeps bash's dangling marker,
    #     but a newline-terminated record (Case B) is an ordinary continuation
    #     with NO marker. The two are distinguished ONLY by whether a delimiter
    #     followed the backslash. Probed vs bash 5.2.26.

    def test_backslash_raw_eof_keeps_trailing_space(self):
        """Case A: trailing backslash at RAW EOF (no newline after it). bash
        keeps a dangling marker so the last field's trailing space survives IFS
        trimming (x=`a `)."""
        r = _psh('read x; echo "rc=$? [$x]"', 'a \\')
        assert r.stdout == "rc=1 [a ]\n"

    def test_backslash_newline_eof_strips_trailing_space(self):
        """Case B: a record ending `\\` then a NORMAL trailing newline into EOF
        is an ordinary continuation with NO marker — the trailing space is
        stripped (x=`a`), matching bash. Regression pin: keeping the marker here
        wrongly produced `a `."""
        r = _psh('read x; echo "rc=$? [$x]"', 'a \\\n')
        assert r.stdout == "rc=1 [a]\n"

    def test_backslash_newline_eof_multivar_strips(self):
        """Case B multi-var: the last field's trailing space is stripped
        (y=`b`), unlike Case A raw-EOF which keeps it."""
        r = _psh('read x y; echo "[$x][$y]"', 'a b \\\n')
        assert r.stdout == "[a][b]\n"

    def test_backslash_newline_eof_array_no_spurious_element(self):
        """Case B array-length regression pin: `read -a` over a
        newline-terminated `a b \\` yields a 2-element array (a, b) with NO
        spurious trailing element — the buggy marker made it length 3."""
        r = _psh('read -a arr; echo "${#arr[@]}"', 'a b \\\n')
        assert r.stdout == "2\n"

    def test_backslash_raw_eof_array_keeps_marker_element(self):
        """Case A array (contrast): raw-EOF `a b \\` keeps the dangling marker,
        so `read -a` produces a 3-element array — the element COUNT matches bash
        (bash's 3rd element is its CTLESC leak; psh's is an empty string)."""
        r = _psh('read -a arr; echo "${#arr[@]}"', 'a b \\')
        assert r.stdout == "3\n"


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


class TestReadTimeoutDeadline:
    """reappraisal #18 T1-7: `read -t` enforces its deadline across the WHOLE
    read, not just the wait for the first byte. A slow producer delivers a
    partial chunk then stalls far past the budget; the read must time out on
    schedule (exit 142) with the partial input saved, matching bash."""

    def _feed_then_stall(self, first, stall_secs):
        """Popen a producer that writes ``first`` then stalls; return its
        stdout pipe for use as another process's stdin."""
        src = (f'import sys,time; sys.stdout.write({first!r}); '
               f'sys.stdout.flush(); time.sleep({stall_secs}); '
               f'sys.stdout.write("TAIL\\n"); sys.stdout.flush()')
        return subprocess.Popen([sys.executable, '-c', src],
                                stdout=subprocess.PIPE)

    def test_deadline_bounds_whole_read_after_first_byte(self):
        feeder = self._feed_then_stall("abc", 5)
        try:
            t0 = time.time()
            r = subprocess.run(
                [sys.executable, '-m', 'psh', '-c',
                 'read -t 0.5 x; echo "rc=$? [$x]"'],
                stdin=feeder.stdout, capture_output=True, text=True,
                timeout=10)
            elapsed = time.time() - t0
        finally:
            feeder.kill()
        # Partial input saved, timeout exit code, and — crucially — the read
        # returned on its ~0.5s deadline, NOT after the producer's 5s stall.
        assert r.stdout == "rc=142 [abc]\n"
        assert elapsed < 3.0, f"read -t abandoned its deadline ({elapsed:.2f}s)"

    def test_deadline_partial_splits_across_vars(self):
        feeder = self._feed_then_stall("aa bb c", 5)
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'psh', '-c',
                 'read -t 0.5 x y z; echo "rc=$? [$x][$y][$z]"'],
                stdin=feeder.stdout, capture_output=True, text=True,
                timeout=10)
        finally:
            feeder.kill()
        assert r.stdout == "rc=142 [aa][bb][c]\n"
