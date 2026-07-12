"""Case statement subject parsing: exactly one word before `in`.

bash takes exactly one word (possibly composite) between `case` and `in`;
`case a b in ...` is a syntax error near `b`. The subject may itself be
spelled `in` or `esac` (`case in in in) ... esac` is valid bash), and
newlines are allowed between the subject and `in` but not between `case`
and the subject. All behaviors below were probed against bash 5.2.
"""


import pytest

from psh.lexer import tokenize
from psh.parser import ParseError, parse


def parse_str(text):
    return parse(list(tokenize(text)))


class TestCaseSubjectRejected:
    """Malformed case headers raise bash-shaped syntax errors."""

    def test_two_words_before_in(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token 'b'"):
            parse_str("case a b in a) echo hi;; esac")

    def test_three_words_before_in(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token 'b'"):
            parse_str("case a b c in a) echo hi;; esac")

    def test_operator_as_subject(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token ';;'"):
            parse_str("case ;; in x) echo hi;; esac")

    def test_semicolon_after_subject(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token ';'"):
            parse_str("case a; in a) echo hi;; esac")

    def test_redirect_as_subject(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token '>'"):
            parse_str("case >f in x) echo hi;; esac")

    def test_newline_after_case_keyword(self):
        # bash: syntax error near unexpected token `newline'
        with pytest.raises(ParseError, match="syntax error near unexpected token 'newline'"):
            parse_str("case\na in a) echo hi;; esac")

    def test_missing_in_keyword(self):
        with pytest.raises(ParseError, match="syntax error near unexpected token 'esac'"):
            parse_str("case a esac")

    def test_eof_after_subject(self):
        with pytest.raises(ParseError, match="syntax error: unexpected end of file"):
            parse_str("case a")

    def test_missing_subject_entirely(self):
        # `case in a) ...` — bash takes `in` as the subject, then errors
        # at `a` because the `in` keyword is missing.
        with pytest.raises(ParseError, match="syntax error near unexpected token 'a'"):
            parse_str("case in a) echo hi;; esac")

    def test_esac_as_first_pattern_rejected(self):
        # bash: `esac` right after `in` closes the case, so the dangling
        # `)` is a syntax error (probed: bash errors near `)`).
        with pytest.raises(ParseError):
            parse_str("case a in esac) echo hi;; esac")


class TestCaseSubjectAccepted:
    """Valid single-word subjects parse (shapes verified against bash)."""

    @pytest.mark.parametrize("text", [
        'case a in a) echo hi;; esac',
        'case "a b" in "a b") echo hi;; esac',     # quoted, one word
        'case a"b"c in abc) echo hi;; esac',       # composite
        'case $x in a) echo hi;; esac',            # variable
        'case $(echo a b) in x) echo hi;; esac',   # command substitution
        'case in in in) echo hi;; esac',           # `in` as subject (valid bash)
        'case if in if) echo hi;; esac',           # keyword spelling as subject
        'case a\nin a) echo hi;; esac',            # newline before `in`
        'case a\n\n\nin a) echo hi;; esac',        # multiple newlines before `in`
        'case a in esac',                          # empty case (valid bash)
        'case a in (esac) echo hi;; esac',         # esac allowed in (pattern)
    ])
    def test_accepted(self, text):
        assert parse_str(text) is not None


class TestCaseSubjectBehavior:
    """End-to-end behavior matches bash (probed)."""

    def test_in_as_subject_matches(self, captured_shell):
        rc = captured_shell.run_command('case in in in) echo hi;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_subject_not_word_split(self, captured_shell):
        # bash does NOT word-split the case subject.
        rc = captured_shell.run_command(
            'x="a b"; case $x in "a b") echo match;; *) echo nomatch;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "match\n"

    def test_newline_before_in_runs(self, captured_shell):
        rc = captured_shell.run_command('case a\nin a) echo hi;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_empty_case_runs(self, captured_shell):
        rc = captured_shell.run_command('case a in esac')
        assert rc == 0
        assert captured_shell.get_stdout() == ""

    def test_for_loop_variable_named_in(self, captured_shell):
        # Same lexer rule: the word right after `for` is the variable,
        # never the `in` keyword (`for in in 1 2` is valid bash).
        rc = captured_shell.run_command('for in in 1 2; do echo $in; done')
        assert rc == 0
        assert captured_shell.get_stdout() == "1\n2\n"
