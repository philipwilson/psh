"""Combinator-parser parity regressions (ground-up reappraisal, v0.276.0).

The 2026-06-10 reappraisal found the combinator parser had drifted behind
two recursive-descent fixes from v0.266–v0.269:

1. Function-definition trailing redirects were applied at *definition*
   time instead of at each call (``f() { ...; } > file`` created the file
   immediately and ``f`` wrote to stdout).
2. Case patterns lost their quote context, so quoted glob characters
   stayed active (``case ab in "a*")`` wrongly matched).

These tests run the same scripts under bash, psh --parser rd, and
psh --parser combinator and require all three to agree.
"""

import subprocess
import sys

PSH = [sys.executable, '-m', 'psh']


def run_bash(cmd, cwd=None):
    return subprocess.run(['bash', '-c', cmd], capture_output=True,
                          text=True, cwd=cwd)


def run_psh(cmd, parser, cwd=None):
    return subprocess.run(PSH + ['--parser', parser, '-c', cmd],
                          capture_output=True, text=True, cwd=cwd)


def assert_three_way(cmd, cwd=None):
    """bash, rd, and combinator must produce identical stdout and rc."""
    bash = run_bash(cmd, cwd=cwd)
    rd = run_psh(cmd, 'rd', cwd=cwd)
    comb = run_psh(cmd, 'combinator', cwd=cwd)
    assert rd.stdout == bash.stdout, (
        f"rd vs bash for {cmd!r}: {rd.stdout!r} != {bash.stdout!r}")
    assert comb.stdout == bash.stdout, (
        f"combinator vs bash for {cmd!r}: {comb.stdout!r} != {bash.stdout!r}")
    assert rd.returncode == bash.returncode
    assert comb.returncode == bash.returncode


class TestCasePatternQuoteContext:
    """Quoted case-pattern text must match literally; unquoted globs stay active."""

    def test_quoted_glob_is_literal(self):
        assert_three_way(
            'case "ab" in "a*") echo literal;; a*) echo glob;; esac')

    def test_quoted_glob_matches_itself(self):
        assert_three_way(
            'case "a*" in "a*") echo literal;; *) echo other;; esac')

    def test_quoted_variable_pattern_is_literal(self):
        assert_three_way(
            'x=foo; case foo in "$x") echo var-literal;; *) echo other;; esac')

    def test_unquoted_glob_still_active(self):
        assert_three_way('case abc in a?c) echo glob;; *) echo no;; esac')

    def test_alternation_mixed_quoting(self):
        assert_three_way(
            'case "x*" in a|"x*") echo second;; *) echo other;; esac')


class TestKeywordSpelledArgumentInBody:
    """An argument that merely spells like a terminator keyword is a word.

    The R9.C3 recursion-based compound-body parser fixed a slicer bug: the old
    token-slicer matched ``done``/``fi`` by value across the whole body span, so
    ``echo done`` inside a loop body was mis-detected as the loop terminator.
    The recursion only checks for terminators at statement-start position, so
    such arguments are consumed as plain words — matching bash and rd.
    """

    def test_done_as_argument_in_while_body(self):
        assert_three_way('while true; do echo done; break; done')

    def test_done_as_argument_in_for_body(self):
        assert_three_way('for i in 1 2; do echo done; done')

    def test_fi_as_argument_in_then_body(self):
        assert_three_way('if true; then echo fi; fi')

    def test_keyword_argument_in_nested_body(self):
        assert_three_way('for i in 1; do if true; then echo done; fi; done')

    def test_esac_as_argument_in_case_body(self):
        assert_three_way('case x in a) echo esac;; *) echo other;; esac')


class TestFunctionDefinitionRedirects:
    """Redirects on a definition apply at each call, not at definition."""

    def test_posix_function_redirect_applies_per_call(self, tmp_path):
        cmd = ('f() { echo hi; } > out.txt; '
               'ls out.txt 2>/dev/null && echo created-at-def; '
               'f; cat out.txt')
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout
        assert comb.returncode == bash.returncode

    def test_keyword_function_redirect_applies_per_call(self, tmp_path):
        cmd = 'function g { echo kw; } > out.txt; g; cat out.txt'
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout
        assert comb.returncode == bash.returncode

    def test_definition_without_redirect_unaffected(self):
        assert_three_way('f() { echo plain; }; f; f')

    def test_redirect_accumulates_appends(self, tmp_path):
        cmd = ('f() { echo line; } >> log.txt; f; f; '
               'wc -l < log.txt | tr -d " "')
        bash_dir = tmp_path / 'bash'
        comb_dir = tmp_path / 'comb'
        bash_dir.mkdir()
        comb_dir.mkdir()
        bash = run_bash(cmd, cwd=bash_dir)
        comb = run_psh(cmd, 'combinator', cwd=comb_dir)
        assert comb.stdout == bash.stdout
