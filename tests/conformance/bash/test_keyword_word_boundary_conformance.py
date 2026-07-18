"""Conformance: reserved words are recognized only as COMPLETE unquoted words.

Boundary campaign S1 (complete lexical words before keyword classification),
all rows probed against bash 5.2.26:

1. A keyword spelling GLUED to an adjacent expansion/quote (``then$x``,
   ``do$x``, ``then""``) is one word, never a keyword — the construct is
   missing its keyword and both shells report a syntax error. (This retires
   psh's old keyword-prefix promotion, reappraisal #20 medium finding 1.)
2. A quoted or escaped keyword spelling (``"if"``, ``\\if``, ``i\\f``,
   ``$'if'``) is a command word, never a reserved word.
3. Bare command-position ``in`` is a SYNTAX error (bash and dash), unlike the
   other keyword spellings it previously fell through to command lookup
   (reappraisal #20 medium finding 2). Subject/header/pattern exceptions
   (``for in in ...``, ``case in in (in) ...``) still parse.
4. The for/select subject may be any word; NAME validity is checked at
   execution (``not a valid identifier``, status 1, execution continues).
5. Reserved words after a REDIRECTION are not at command start (bash runs
   ``>/dev/null in`` as command ``in`` -> 127).

Error messages differ between shells, so error rows compare exit status and
stdout (and require stderr on both sides); success rows require identical
behavior. Both parsers are exercised for representative rows via
``--parser combinator`` subprocess runs; -c / script / stdin input modes are
exercised for two representative rows (same grammar path, different drivers).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from conformance_framework import ConformanceTest

_REPO = Path(__file__).resolve().parents[3]


class _KeywordBoundaryBase(ConformanceTest):
    """Shared error-row helper: same rc, same stdout, stderr on both sides."""

    def assert_same_error_class(self, command: str):
        psh_result = self.framework.run_in_psh(command)
        bash_result = self.framework.run_in_bash(command)
        assert bash_result.exit_code != 0, f"bash accepted: {command}"
        assert psh_result.exit_code == bash_result.exit_code, (
            f"exit codes differ for {command!r}: "
            f"psh={psh_result.exit_code} bash={bash_result.exit_code}")
        assert psh_result.stdout == bash_result.stdout, command
        assert psh_result.stderr and bash_result.stderr, command


class TestGluedKeywordPrefixConformance(_KeywordBoundaryBase):
    """A keyword glued to an expansion/quote is one word (syntax error)."""

    def test_glued_keyword_rows_syntax_error(self):
        for command in (
            'if true; then$x echo hi; fi',
            'x=Y; if true; then$x echo hi; fi',
            'for i in 1 2; do$x echo $i; done',
            'if true; then${x}echo A; fi',
            'if true; then"" echo hi; fi',
            "if true; then'' echo hi; fi",
            'if$x true; then echo hi; fi',
            'while$x true; do echo hi; done',
            'case$x a in a) echo y;; esac',
            'for i in 1; do echo $i; done$(true)',
        ):
            self.assert_same_error_class(command)

    def test_glued_closer_expands_to_command_lookup(self):
        # `fi$x` / `esac$x` / `in$x` are words: they EXPAND (x unset) and run
        # as commands -> 127 in both shells, NOT a syntax error (discriminates
        # word-first classification from any keyword-prefix scheme).
        for command in ('fi$x', 'esac$x', 'in$x'):
            self.assert_same_error_class(command)

    def test_for_case_header_glue_rejected(self):
        self.assert_same_error_class('for i in$x 1 2; do echo $i; done')
        self.assert_same_error_class('case a in$x a) :;; esac')


class TestQuotedEscapedKeywordConformance(_KeywordBoundaryBase):
    """Quoted/escaped keyword spellings are command words, never keywords."""

    def test_quoted_keywords_are_command_words(self):
        # All run command lookup (127), not keyword grammar.
        for command in (
            '"if" true', "'if' true", '\\if true', 'i\\f true',
            "$'if' true", '"i"f true', '"fi"', '"in"', "'in'", '\\in',
            "i'n'",
        ):
            self.assert_same_error_class(command)

    def test_quoted_then_do_break_their_constructs(self):
        for command in (
            'if true; "then" echo hi; fi',
            'if true; \\then echo hi; fi',
            'if true; th\\en echo hi; fi',
            'for i in 1; "do" echo $i; done',
            'for i "in" 1 2; do echo $i; done',
        ):
            self.assert_same_error_class(command)

    def test_keywords_as_arguments_identical(self):
        self.assert_identical_behavior('echo if then fi in do done esac')
        self.assert_identical_behavior('echo time')

    def test_line_continuation_inside_keyword_is_keyword(self):
        # Line continuation is removed BEFORE lexing in both shells, so the
        # spelling is complete and unquoted: it IS the keyword.
        self.assert_identical_behavior('i\\\nf true; then echo hi; fi')
        self.assert_identical_behavior('if true; th\\\nen echo hi; fi')


class TestBareInSyntaxErrorConformance(_KeywordBoundaryBase):
    """Bare command-position `in` is a syntax error (bash/dash rule)."""

    def test_bare_in_rejected_everywhere(self):
        for command in (
            'in', 'in x y', 'true; in', 'true | in', 'in | true',
            '(in)', '{ in; }', 'if in; then :; fi', 'true && in',
            '! in', 'time in', 'true\nin', 'in >/dev/null',
        ):
            self.assert_same_error_class(command)

    def test_legitimate_in_sites_identical(self):
        self.assert_identical_behavior('in=5; echo $in')
        self.assert_identical_behavior('echo in')
        self.assert_identical_behavior('for in in a b; do echo $in; done')
        self.assert_identical_behavior('for in in in; do echo "$in"; done')
        self.assert_identical_behavior('case in in in) echo y;; esac')
        self.assert_identical_behavior('case in in (in) echo y;; esac')
        self.assert_identical_behavior('case in in\nin) echo y;; esac')
        self.assert_identical_behavior('for in do echo x; done')
        self.assert_identical_behavior('for x\nin a b\ndo echo $x\ndone')

    def test_redirection_prefixed_in_is_command_word(self):
        # A redirection before the word means the word is NOT the command
        # start, so `in` is not reserved: bash runs it (127).
        self.assert_same_error_class('>/dev/null in')


class TestLoopSubjectWordConformance(_KeywordBoundaryBase):
    """for/select subjects: any word parses; NAME validity is at execution."""

    def test_invalid_subjects_error_and_continue(self):
        # rc 1 (not a syntax-error 2), stderr diagnostic, and execution
        # CONTINUES with the next statement (`echo after` runs, final rc 0).
        for command in (
            'for "in" in a; do echo $in; done',
            'for "x" in a; do :; done; echo after',
            'for x"y" in a; do :; done; echo after',
            'v=i; for $v in a; do echo hi; done',
            'for $(echo q) in a; do :; done; echo after',
            'select "x" in a; do :; done; echo after',
        ):
            psh_result = self.framework.run_in_psh(command)
            bash_result = self.framework.run_in_bash(command)
            assert psh_result.exit_code == bash_result.exit_code, (
                f"exit codes differ for {command!r}: "
                f"psh={psh_result.exit_code} bash={bash_result.exit_code}")
            assert psh_result.stdout == bash_result.stdout, command
            assert psh_result.stderr and bash_result.stderr, command
            assert "not a valid identifier" in psh_result.stderr, command

    def test_keyword_spelled_subject_is_a_name(self):
        self.assert_identical_behavior('for if in a b; do echo $if; done')


class TestCasePatternKeywordConformance(_KeywordBoundaryBase):
    """Keyword-typed case patterns parse (patterns after ;; / ( / newline)."""

    def test_keyword_patterns_identical(self):
        self.assert_identical_behavior('case if in a) :;; if) echo y;; esac')
        self.assert_identical_behavior('case time in a) :;; time) echo t;; esac')
        self.assert_identical_behavior('x=in; case $x in a) :;; in) echo i;; esac')
        self.assert_identical_behavior('case if in\nif) echo y;; esac')
        self.assert_identical_behavior('case if in "if") echo k;; esac')


class TestKeywordBoundaryModesAndParsers(_KeywordBoundaryBase):
    """Mode variation (-c/script/stdin) and combinator-parser representatives."""

    def _psh(self, argv_extra, stdin_data=None):
        return subprocess.run(
            [sys.executable, "-m", "psh", *argv_extra],
            input=stdin_data, capture_output=True, text=True, cwd=_REPO)

    def test_bare_in_all_input_modes(self):
        # -c mode is covered above; script and stdin drive the same grammar.
        assert self._psh(["-c", "in"]).returncode == 2
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            f.write("in\n")
            f.flush()
            r = self._psh([f.name])
            assert r.returncode == 2 and r.stdout == "" and r.stderr
        r = self._psh([], stdin_data="in\n")
        assert r.returncode == 2 and r.stdout == "" and r.stderr

    def test_glued_then_all_input_modes(self):
        cmd = "if true; then$x echo hi; fi"
        assert self._psh(["-c", cmd]).returncode == 2
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            f.write(cmd + "\n")
            f.flush()
            r = self._psh([f.name])
            assert r.returncode == 2 and r.stdout == ""
        r = self._psh([], stdin_data=cmd + "\n")
        assert r.returncode == 2 and r.stdout == ""

    def test_combinator_parser_parity_representatives(self):
        rows = [
            ("in", 2, ""),
            ("if true; then$x echo hi; fi", 2, ""),
            ('"if" true', 127, ""),
            ("for in in a b; do echo $in; done", 0, "a\nb\n"),
            ("case in in (in) echo y;; esac", 0, "y\n"),
            ('case if in a) :;; if) echo y;; esac', 0, "y\n"),
            ('for "x" in a; do :; done; echo after', 0, "after\n"),
        ]
        for cmd, rc, out in rows:
            r = self._psh(["--parser", "combinator", "-c", cmd])
            assert (r.returncode, r.stdout) == (rc, out), (
                f"combinator: {cmd!r} -> rc={r.returncode} out={r.stdout!r}")

    def test_validate_mode_rejects_bare_in(self):
        r = self._psh(["--validate", "-c", "in"])
        assert r.returncode != 0
