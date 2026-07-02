"""Regression pins for the `case` subject Word (appraisal #15, Cluster G1).

The subject used to be stored as a flattened string and re-expanded only
when it contained a `$`, so a single-quoted subject was WRONGLY re-expanded
(`case '$x' in '$x')` matched the expanded arm) and a single-quoted command
substitution was EXECUTED. It now carries a Word with per-part quote context
(CaseConditional.subject_word) that the executor expands quote-aware — tilde,
parameter/command/arithmetic expansion, quote removal, but NO word splitting
and NO globbing. All expected values verified against bash 5.2.
"""

import pytest


class TestCaseSubjectQuoting:
    def test_single_quoted_subject_is_literal(self, captured_shell):
        # bash: matches the literal '$x' arm, not the expanded one.
        rc = captured_shell.run_command(
            "x=hello; case '$x' in '$x') echo literal;; hello) echo exp;; esac")
        assert rc == 0
        assert captured_shell.get_stdout() == "literal\n"

    def test_single_quoted_cmdsub_not_executed(self, captured_shell):
        # The single-quoted $(...) must NOT run — it is literal text.
        rc = captured_shell.run_command(
            "case '$(echo hi)' in '$(echo hi)') echo literal;; hi) echo exp;; esac")
        assert rc == 0
        assert captured_shell.get_stdout() == "literal\n"

    def test_double_dollar_single_quoted_no_expand(self, captured_shell):
        rc = captured_shell.run_command(
            "case '$HOME' in '$HOME') echo lit;; *) echo exp;; esac")
        assert rc == 0
        assert captured_shell.get_stdout() == "lit\n"

    def test_composite_quoted_empty_plus_literal(self, captured_shell):
        # "$x"y with x empty -> subject is "y".
        rc = captured_shell.run_command(
            'x=; case "$x"y in y) echo m;; *) echo no;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "m\n"

    def test_backtick_subject_expands(self, captured_shell):
        rc = captured_shell.run_command(
            "case `echo foo` in foo) echo matched;; esac")
        assert rc == 0
        assert captured_shell.get_stdout() == "matched\n"

    def test_tilde_subject_expands(self, captured_shell):
        rc = captured_shell.run_command(
            'case ~ in "$HOME") echo tilde;; *) echo no;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "tilde\n"

    def test_double_quoted_subject_expands(self, captured_shell):
        rc = captured_shell.run_command('x=hi; case "$x" in hi) echo m;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "m\n"

    def test_arithmetic_subject(self, captured_shell):
        rc = captured_shell.run_command('case $((1+1)) in 2) echo two;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "two\n"

    def test_subject_not_globbed(self, captured_shell):
        # The subject value '*' is not pathname-expanded; it stays literal '*'.
        rc = captured_shell.run_command(
            "x='*'; case $x in '*') echo star;; *) echo other;; esac")
        assert rc == 0
        assert captured_shell.get_stdout() == "star\n"

    def test_subject_not_split(self, captured_shell):
        # A subject that expands to "a b" is one word (no field splitting).
        rc = captured_shell.run_command(
            'x="a b"; case $x in "a b") echo m;; *) echo no;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "m\n"

    def test_tilde_only_leading_not_after_colon(self, captured_shell):
        # bash: only a LEADING ~ expands in a case subject; a:~ stays literal.
        rc = captured_shell.run_command(
            'case a:~ in a:~) echo literal;; *) echo other;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "literal\n"

    def test_nested_in_function(self, captured_shell):
        rc = captured_shell.run_command(
            "f() { x=hello; case '$x' in '$x') echo lit;; hello) echo exp;; esac; }; f")
        assert rc == 0
        assert captured_shell.get_stdout() == "lit\n"

    @pytest.mark.parametrize("parser", ["rd"])
    def test_parser_populates_subject_word(self, parser):
        from psh.ast_nodes import CaseConditional, Word
        from psh.lexer import tokenize
        from psh.parser import parse

        ast = parse(tokenize("case '$x' in a) :;; esac"))

        def find(node, seen=None):
            seen = seen or set()
            if id(node) in seen:
                return None
            seen.add(id(node))
            if isinstance(node, CaseConditional):
                return node
            import dataclasses
            if dataclasses.is_dataclass(node):
                for f in dataclasses.fields(node):
                    r = find(getattr(node, f.name), seen)
                    if r is not None:
                        return r
            elif isinstance(node, (list, tuple)):
                for it in node:
                    r = find(it, seen)
                    if r is not None:
                        return r
            return None

        case_node = find(ast)
        assert case_node is not None
        assert isinstance(case_node.subject_word, Word)
        # single-quoted subject: quote_type is the single quote
        assert case_node.subject_word.effective_quote_char == "'"
