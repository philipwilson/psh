"""Conformance tests: a lowercase keyword spelled as a plain argument.

Pins H1 (reappraisal #7): `echo if then` must print `if then`, not raise a
parse error. A reserved word is only a keyword at COMMAND position; once it
appears as an argument it is an ordinary word, and the word AFTER it must
NOT be promoted to a keyword either. psh used to keep "command position"
alive whenever it saw a WORD whose *value* was `if`/`while`/`until` — even
when that word was an argument — so the following `then`/`fi`/`do` was
normalized into a keyword token and the parser choked.

The fix must NOT break real keyword recognition in genuine command
position; the regression cases below pin that.
"""



from conformance_framework import ConformanceTest


class TestKeywordAsArgument(ConformanceTest):
    """Lowercase keyword spellings are plain words in argument position."""

    def test_if_then_as_arguments(self):
        self.assert_identical_behavior('echo if then')

    def test_if_fi_as_arguments(self):
        self.assert_identical_behavior('echo if fi')

    def test_while_do_done_as_arguments(self):
        self.assert_identical_behavior('echo while do done')

    def test_keyword_after_first_arg(self):
        self.assert_identical_behavior('echo a if then')

    def test_many_keywords_as_arguments(self):
        self.assert_identical_behavior('echo while until do done fi')

    def test_closers_as_arguments(self):
        self.assert_identical_behavior('echo do done esac fi')

    def test_branch_words_as_arguments(self):
        self.assert_identical_behavior('echo then else elif')

    def test_keyword_after_double_dash(self):
        """`cat -- if then` — the keywords are operands, both shells try to
        open files named `if` and `then` and fail identically."""
        self.assert_identical_behavior('cat -- if then')

    def test_keyword_value_via_variable(self):
        self.assert_identical_behavior('x=if; echo $x then')


class TestRealKeywordRecognitionUnaffected(ConformanceTest):
    """The H1 fix must leave genuine command-position keywords intact."""

    def test_if_statement(self):
        self.assert_identical_behavior('if true; then echo y; fi')

    def test_while_loop(self):
        self.assert_identical_behavior('while false; do :; done; echo ok')

    def test_until_loop(self):
        self.assert_identical_behavior('until true; do :; done; echo ok')

    def test_for_loop(self):
        self.assert_identical_behavior('for i in 1 2; do echo $i; done')

    def test_case_statement(self):
        self.assert_identical_behavior('case x in x) echo y;; esac')

    def test_nested_if_in_condition(self):
        self.assert_identical_behavior(
            'if if true; then true; fi; then echo z; fi')

    def test_keyword_after_separator(self):
        self.assert_identical_behavior('echo a; if true; then echo b; fi')

    def test_keyword_after_and_and(self):
        self.assert_identical_behavior('true && if true; then echo a; fi')

    def test_keyword_after_pipe(self):
        self.assert_identical_behavior('if echo a | grep a; then echo p; fi')

    def test_loop_into_pipe(self):
        self.assert_identical_behavior('for i in a b; do echo $i; done | cat')

    def test_double_bracket_after_while(self):
        self.assert_identical_behavior(
            'while [[ -n "" ]]; do :; done; echo wok')
