"""An unterminated heredoc is delimited by end-of-file, like bash.

Reappraisal #17 lexer MED-1: psh used to DROP the whole command silently
(no output, no warning, exit 0) when EOF arrived inside a heredoc body —
worse than bash, which uses everything gathered as the body, prints

    NAME: line M: warning: here-document at line N delimited by end-of-file
    (wanted `EOF')

to stderr (M = the EOF line, N = the line the heredoc's body gathering
began), and RUNS the command with exit status from the command itself.

For script files both shells print the script path as NAME, so stderr can
be compared byte-for-byte (the scripts are invoked by identical relative
paths). For -c/stdin bash prints "bash:" and psh prints "psh:"; those
cases compare stdout/exit and the warning suffix.

Truth-tabled against bash 5.2 (tmp/probes-r17t2-input/probe_unterm*.sh).
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _run_both(tmp_path, script_text, name="case.sh"):
    (tmp_path / name).write_text(script_text)
    psh = subprocess.run([sys.executable, '-m', 'psh', name],
                         capture_output=True, text=True, cwd=tmp_path,
                         timeout=15)
    bash = subprocess.run([BASH, name], capture_output=True, text=True,
                          cwd=tmp_path, timeout=15)
    return psh, bash


def _assert_identical(psh, bash):
    assert psh.stdout == bash.stdout
    assert psh.stderr == bash.stderr
    assert psh.returncode == bash.returncode


class TestUnterminatedHeredocScriptFiles:
    def test_basic_content_to_eof_with_warning(self, tmp_path):
        psh, bash = _run_both(tmp_path, 'cat <<EOF\nhello\nworld\n')
        _assert_identical(psh, bash)
        assert psh.stdout == 'hello\nworld\n'
        assert ("case.sh: line 3: warning: here-document at line 1 "
                "delimited by end-of-file (wanted `EOF')") in psh.stderr
        assert psh.returncode == 0

    def test_warning_reports_heredoc_start_line(self, tmp_path):
        psh, bash = _run_both(tmp_path, 'echo start\n\ncat <<EOF\nhello\n')
        _assert_identical(psh, bash)
        assert 'here-document at line 3' in psh.stderr

    def test_dash_heredoc_space_indented_delimiter_is_body(self, tmp_path):
        # <<- strips TABS only: a space-indented "EOF" line is body, so the
        # heredoc runs to EOF (it used to vanish silently, taking every
        # following command with it).
        psh, bash = _run_both(tmp_path,
                              'cat <<-EOF\n\thello\n  EOF\necho after\n')
        _assert_identical(psh, bash)
        assert psh.stdout == 'hello\n  EOF\necho after\n'

    def test_two_heredocs_second_unterminated(self, tmp_path):
        # A terminated, B not: B's body runs to EOF; the warning reports the
        # line where B's gathering began (A's terminator line — bash rule).
        psh, bash = _run_both(tmp_path, 'cat <<A <<B\nbody1\nA\nbody2\n')
        _assert_identical(psh, bash)
        assert psh.stdout == 'body2\n'
        assert "here-document at line 3 delimited by end-of-file (wanted `B')" \
            in psh.stderr

    def test_two_heredocs_both_unterminated(self, tmp_path):
        # First pending gets the gathered lines, second gets an empty body;
        # one warning per heredoc.
        psh, bash = _run_both(tmp_path, 'cat <<A <<B\nbody1\n')
        _assert_identical(psh, bash)
        assert psh.stdout == ''
        assert "(wanted `A')" in psh.stderr
        assert "(wanted `B')" in psh.stderr

    def test_exit_status_comes_from_the_command(self, tmp_path):
        psh, bash = _run_both(tmp_path, 'grep -q zzz <<EOF\nhello\n')
        _assert_identical(psh, bash)
        assert psh.returncode == 1

    def test_no_body_at_all(self, tmp_path):
        psh, bash = _run_both(tmp_path, 'cat <<EOF')
        _assert_identical(psh, bash)
        assert psh.stdout == ''
        assert 'delimited by end-of-file' in psh.stderr
        assert psh.returncode == 0

    def test_following_command_on_same_line_still_runs(self, tmp_path):
        psh, bash = _run_both(tmp_path, 'cat <<EOF; echo hi\n')
        _assert_identical(psh, bash)
        assert psh.stdout == 'hi\n'

    def test_unterminated_in_sourced_file(self, tmp_path):
        (tmp_path / 'inner.sh').write_text('cat <<EOF\ninner-body\n')
        psh, bash = _run_both(tmp_path,
                              '. ./inner.sh\necho after-source\n')
        _assert_identical(psh, bash)
        assert psh.stdout == 'inner-body\nafter-source\n'
        assert "inner.sh: line 2: warning: here-document at line 1" \
            in psh.stderr


class TestUnterminatedHeredocOtherModes:
    @pytest.mark.parametrize("mode", ["dash_c", "stdin"])
    def test_warning_and_content(self, mode):
        cmd = 'cat <<EOF\nhello'
        if mode == "dash_c":
            psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                                 capture_output=True, text=True, timeout=15)
            bash = subprocess.run([BASH, '-c', cmd],
                                  capture_output=True, text=True, timeout=15)
        else:
            psh = subprocess.run([sys.executable, '-m', 'psh'], input=cmd,
                                 capture_output=True, text=True, timeout=15)
            bash = subprocess.run([BASH], input=cmd,
                                  capture_output=True, text=True, timeout=15)
        assert psh.stdout == bash.stdout == 'hello\n'
        assert psh.returncode == bash.returncode == 0
        # bash prefixes "bash:", psh "psh:" — compare the suffix.
        suffix = ("line 2: warning: here-document at line 1 delimited by "
                  "end-of-file (wanted `EOF')")
        assert suffix in psh.stderr
        assert suffix in bash.stderr

    def test_noexec_validate_still_warns_rc0(self, tmp_path):
        # bash -n warns too (the parser reads the heredoc); psh --validate
        # mirrors it.
        script = tmp_path / 'v.sh'
        script.write_text('cat <<EOF\nhello\n')
        psh = subprocess.run(
            [sys.executable, '-m', 'psh', '--validate', str(script)],
            capture_output=True, text=True, timeout=15)
        assert psh.returncode == 0
        assert 'delimited by end-of-file' in psh.stderr
