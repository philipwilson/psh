"""Batch 6: glob bracket features.

Unit tests for the shared bracket-normalization helper plus filesystem-level
tests for [^...] negation, POSIX character classes, nocaseglob, and globstar.
"""


import pytest

from psh.expansion.glob import normalize_bracket_expressions


class TestNormalizeBracketExpressions:
    def test_caret_negation_to_bang(self):
        assert normalize_bracket_expressions('file[^0-9]') == 'file[!0-9]'

    def test_bang_negation_unchanged(self):
        assert normalize_bracket_expressions('file[!0-9]') == 'file[!0-9]'

    def test_posix_alpha(self):
        assert normalize_bracket_expressions('[[:alpha:]]') == '[a-zA-Z]'

    def test_posix_digit_embedded(self):
        assert normalize_bracket_expressions('*[[:digit:]]*') == '*[0-9]*'

    def test_negated_posix_class(self):
        assert normalize_bracket_expressions('[^[:digit:]]') == '[!0-9]'

    def test_escaped_bracket_not_negated(self):
        assert normalize_bracket_expressions(r'\[^x]') == r'\[^x]'

    def test_no_brackets_unchanged(self):
        assert normalize_bracket_expressions('a^b*c') == 'a^b*c'


@pytest.fixture
def globdir(tmp_path, monkeypatch):
    for name in ('file1', 'file2', 'fileX', 'Foo.TXT', 'bar.txt', 'Baz123'):
        (tmp_path / name).touch()
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'x.txt').touch()
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestGlobBracketsFilesystem:
    def _glob(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return sorted(capsys.readouterr().out.split())

    def test_caret_negation(self, shell, capsys, globdir):
        # file[^0-9] excludes file1/file2, matches fileX
        assert self._glob(shell, capsys, 'echo file[^0-9]') == ['fileX']

    def test_posix_upper(self, shell, capsys, globdir):
        assert self._glob(shell, capsys, 'echo *[[:upper:]]*') == ['Baz123', 'Foo.TXT', 'fileX']

    def test_posix_digit(self, shell, capsys, globdir):
        assert self._glob(shell, capsys, 'echo *[[:digit:]]') == ['Baz123', 'file1', 'file2']

    def test_nocaseglob(self, shell, capsys, globdir):
        got = self._glob(shell, capsys, 'shopt -s nocaseglob; echo f*')
        assert got == ['Foo.TXT', 'file1', 'file2', 'fileX']

    def test_nocaseglob_off_by_default(self, shell, capsys, globdir):
        assert self._glob(shell, capsys, 'echo f*') == ['file1', 'file2', 'fileX']

    def test_globstar(self, shell, capsys, globdir):
        assert self._glob(shell, capsys, 'shopt -s globstar; echo **/*.txt') == ['bar.txt', 'sub/x.txt']

    def test_globstar_off_does_not_recurse(self, shell, capsys, globdir):
        # Without globstar, **/*.txt behaves like */*.txt (only sub/x.txt).
        assert self._glob(shell, capsys, 'echo **/*.txt') == ['sub/x.txt']
