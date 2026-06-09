"""
Tests that external-command redirections are applied exactly once.

Regression guards (verified against bash 5.2): the parent used to apply
with_redirections AND the forked child applied setup_child_redirections
over the same list, so:
- `cmd 2>&1 >f` resolved 2>&1 against the already-redirected fd 1, sending
  stderr into f (bash: to the original stdout);
- command substitutions in heredoc bodies and redirect targets executed
  TWICE (verified by side-effect counting).
"""

import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


class TestDupOrdering:
    def test_2to1_before_file_redirect_goes_to_original_stdout(self, tmp_path):
        """`ls /bad 2>&1 >f`: stderr follows the ORIGINAL stdout, f empty."""
        result = run_psh('ls /nonexistent_zz 2>&1 >o.txt', cwd=tmp_path)
        # stderr was duplicated onto original stdout, so the message arrives
        # on the process's stdout stream, not in the file.
        assert 'No such file' in result.stdout
        assert (tmp_path / 'o.txt').read_text() == ''

    def test_file_then_2to1_both_into_file(self, tmp_path):
        result = run_psh('ls /nonexistent_zz >o.txt 2>&1', cwd=tmp_path)
        assert result.stdout == ''
        assert 'No such file' in (tmp_path / 'o.txt').read_text()


class TestCommandSubstitutionRunsOnce:
    def test_heredoc_body_command_sub_once(self, tmp_path):
        run_psh('cat <<EOF >/dev/null\n$(echo once >> side.txt)\nEOF',
                cwd=tmp_path)
        assert (tmp_path / 'side.txt').read_text() == 'once\n'

    def test_redirect_target_command_sub_once(self, tmp_path):
        run_psh('/bin/echo hi > $(echo once >> side.txt; echo t.txt)',
                cwd=tmp_path)
        assert (tmp_path / 'side.txt').read_text() == 'once\n'
        assert (tmp_path / 't.txt').read_text() == 'hi\n'


class TestExternalRedirectionBasics:
    def test_output_redirect(self, tmp_path):
        run_psh('/bin/echo out > b1.txt', cwd=tmp_path)
        assert (tmp_path / 'b1.txt').read_text() == 'out\n'

    def test_stderr_suppression(self):
        result = run_psh('/bin/ls /nonexistent_zz 2>/dev/null; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr == ''

    def test_stdin_redirect(self, tmp_path):
        (tmp_path / 'in.txt').write_text('line1\nline2\n')
        result = run_psh('/usr/bin/head -1 < in.txt', cwd=tmp_path)
        assert result.stdout == 'line1\n'

    def test_process_substitution_target(self):
        result = run_psh('/bin/cat <(echo procsub)')
        assert result.stdout == 'procsub\n'

    def test_noclobber_respected_in_child(self, tmp_path):
        result = run_psh(
            'set -C; echo x > nc.txt; /bin/echo y > nc.txt 2>/dev/null; '
            'echo rc=$?; cat nc.txt', cwd=tmp_path)
        assert result.stdout == 'rc=1\nx\n'

    def test_heredoc_to_external_in_pipeline(self):
        result = run_psh('/usr/bin/tr a-z A-Z <<EOF | /usr/bin/wc -c\nhello\nEOF')
        assert result.stdout.strip() == '6'
