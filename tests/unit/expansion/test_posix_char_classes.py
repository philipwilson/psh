"""POSIX character classes punct/cntrl/graph/print (reappraisal #16 H6).

Before the fix these four classes were left untranslated, so the literal
``[:punct:]`` text reached Python ``re`` / stdlib ``fnmatch`` as a nested set:
it matched the wrong thing AND leaked ``FutureWarning: Possible nested set``
to stderr in default mode. bash 5.2 (C locale) semantics, probe-verified:

- ``punct`` = 0x21-0x2f, 0x3a-0x40, 0x5b-0x60, 0x7b-0x7e
- ``graph`` = 0x21-0x7e
- ``print`` = 0x20-0x7e
- ``cntrl`` = 0x00-0x1f and 0x7f

The fix reaches every pattern site: ``[[ == ]]``, ``case``, prefix/suffix
removal, and pathname globbing.
"""

import subprocess
import sys

import pytest


class TestPosixClassMatchingBracket:
    """[[ char == [[:class:]] ]] for the four newly-supported classes."""

    @pytest.mark.parametrize("ch,cls,rc", [
        ("!", "punct", 0), ("~", "punct", 0), ("@", "punct", 0),
        ("a", "punct", 1), ("5", "punct", 1),
        ("a", "graph", 0), ("5", "graph", 0), ("!", "graph", 0),
        ("~", "graph", 0), (" ", "graph", 1),
        ("a", "print", 0), (" ", "print", 0), ("~", "print", 0),
    ])
    def test_bracket(self, captured_shell, ch, cls, rc):
        got = captured_shell.run_command(f'[[ "{ch}" == [[:{cls}:]] ]]')
        assert got == rc
        assert captured_shell.get_stderr() == ""

    def test_negated_class(self, captured_shell):
        # 'a' is not punct -> [^[:punct:]] matches it.
        assert captured_shell.run_command('[[ "a" == [^[:punct:]] ]]') == 0
        assert captured_shell.run_command('[[ "!" == [^[:punct:]] ]]') == 1
        assert captured_shell.get_stderr() == ""


class TestPosixClassCase:
    def test_case_punct(self, captured_shell):
        rc = captured_shell.run_command(
            'case "!" in [[:punct:]]) echo Y;; *) echo N;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "Y\n"
        assert captured_shell.get_stderr() == ""

    def test_case_graph_space_excluded(self, captured_shell):
        rc = captured_shell.run_command(
            'case " " in [[:graph:]]) echo Y;; *) echo N;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "N\n"
        assert captured_shell.get_stderr() == ""


class TestPosixClassRemoval:
    def test_prefix_removal_strips_punct(self, captured_shell):
        captured_shell.run_command('v="!x"; echo "${v#[[:punct:]]}"')
        assert captured_shell.get_stdout() == "x\n"
        assert captured_shell.get_stderr() == ""

    def test_prefix_removal_no_strip_when_not_class(self, captured_shell):
        captured_shell.run_command('v="ax"; echo "${v#[[:punct:]]}"')
        assert captured_shell.get_stdout() == "ax\n"
        assert captured_shell.get_stderr() == ""

    def test_suffix_removal_strips_graph(self, captured_shell):
        captured_shell.run_command('v="ab~"; echo "${v%[[:graph:]]}"')
        assert captured_shell.get_stdout() == "ab\n"
        assert captured_shell.get_stderr() == ""


class TestNoFutureWarning:
    """No Python FutureWarning may leak to stderr for any class/construct.

    Uses a subprocess so the real interpreter stderr is inspected (warnings
    bypass the in-process capture).
    """

    @pytest.mark.parametrize("script", [
        '[[ "!" == [[:punct:]] ]]',
        '[[ "a" == [[:graph:]] ]]',
        '[[ "a" == [[:print:]] ]]',
        'case "!" in [[:cntrl:]]) :;; esac',
        'v="!x"; echo "${v#[[:punct:]]}"',
        'v="a~"; echo "${v%[[:print:]]}"',
    ])
    def test_no_warning(self, script):
        r = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', script],
            capture_output=True, text=True)
        assert "FutureWarning" not in r.stderr
        assert "nested set" not in r.stderr


class TestPosixClassPathnameGlob:
    """POSIX classes must reach the fnmatch/glob.glob pathname path too."""

    def _files(self, shell):
        shell.run_command('touch bang a Z 5 tilde at')
        # rename to the actual punctuation characters
        shell.run_command('mv bang "!"; mv tilde "~"; mv at "@"')

    def test_punct_glob(self, shell, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._files(shell)
        capsys.readouterr()
        shell.run_command('echo [[:punct:]]')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["!", "@", "~"]

    def test_alpha_glob_unaffected(self, shell, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._files(shell)
        capsys.readouterr()
        shell.run_command('echo [[:alpha:]]')
        out = capsys.readouterr().out.strip().split()
        assert sorted(out) == ["Z", "a"]
