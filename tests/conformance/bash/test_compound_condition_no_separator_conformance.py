r"""Conformance: `(( ))` / `[[ ]]` condition header followed DIRECTLY by then/do.

bash accepts an arithmetic command or `[[ ]]` test used as a condition header
with no separator before the `then`/`do` keyword (`if ((1)) then …`,
`while ((x)) do …`, `for ((;;)) do …`, `if [[ a = a ]] then …`). psh used to
reject these: `DOUBLE_RPAREN`/`DOUBLE_RBRACKET` were missing from the lexer's
`RESET_TO_COMMAND_POSITION`, so the following `then`/`do` was lexed as a plain
WORD. Regression pin for reappraisal #10 R12.A (fixed by adding the two
compound-closer token types to that set).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestCompoundConditionNoSeparatorConformance(ConformanceTest):
    """`then`/`do` may follow `))`/`]]` with no intervening separator."""

    def test_arith_if_then_no_separator(self):
        self.assert_identical_behavior('if ((1)) then echo yes; fi')

    def test_arith_while_do_no_separator(self):
        self.assert_identical_behavior(
            'i=0; while ((i<2)) do echo $i; ((i++)); done')

    def test_cstyle_for_do_no_separator(self):
        self.assert_identical_behavior('for ((n=0;n<2;n++)) do echo n$n; done')

    def test_dbracket_if_then_no_separator(self):
        self.assert_identical_behavior('if [[ x = x ]] then echo eq; fi')

    def test_dbracket_while_do_no_separator(self):
        self.assert_identical_behavior(
            'i=0; while [[ $i != 2 ]] do echo $i; i=$((i+1)); done')

    # The separator forms must keep working unchanged.
    def test_arith_if_then_with_separator_still_works(self):
        self.assert_identical_behavior('if ((1)); then echo yes; fi')

    def test_dbracket_and_chain_still_works(self):
        self.assert_identical_behavior('[[ x = x ]] && echo and')
