"""
Tests for quote preservation alongside process substitutions.

Regression guard (verified against bash 5.2): when any argument was a
process substitution, ALL words were rebuilt from plain strings, discarding
quote context — a quoted "*" then glob-expanded and a quoted "$x" with
spaces split. The command node was also mutated in place.
"""

import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


class TestProcessSubQuotePreservation:
    def test_quoted_star_not_globbed(self, tmp_path):
        (tmp_path / 'f1.txt').touch()
        (tmp_path / 'f2.txt').touch()
        result = run_psh('echo "*" <(echo hi)', cwd=tmp_path)
        assert result.stdout.startswith('* /dev/fd/')
        assert 'f1.txt' not in result.stdout

    def test_quoted_variable_not_split(self):
        result = run_psh('x="a b"; printf "[%s]\\n" "$x" <(echo hi)')
        lines = result.stdout.splitlines()
        assert lines[0] == '[a b]'
        assert lines[1].startswith('[/dev/fd/')

    def test_single_quoted_dollar_stays_literal(self):
        result = run_psh("printf '[%s]\\n' '$HOME' <(echo hi)")
        assert result.stdout.splitlines()[0] == '[$HOME]'

    def test_substitution_content_readable(self):
        result = run_psh('cat <(echo procsub)')
        assert result.stdout == 'procsub\n'

    def test_two_substitutions(self):
        result = run_psh('diff <(echo a) <(echo a) && echo same')
        assert result.stdout == 'same\n'

    def test_loop_recreates_substitutions(self):
        """The AST must not be mutated: each iteration gets a fresh fd."""
        result = run_psh('for i in 1 2 3; do cat <(echo $i); done')
        assert result.stdout == '1\n2\n3\n'

    def test_quoted_array_fields_with_procsub(self):
        """Multi-field expansion still works next to a process sub."""
        result = run_psh('a=(1 "2 3"); printf "[%s]\\n" "${a[@]}" <(echo hi)')
        lines = result.stdout.splitlines()
        assert lines[0] == '[1]'
        assert lines[1] == '[2 3]'
        assert lines[2].startswith('[/dev/fd/')
