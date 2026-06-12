"""Conformance tests: grammar boundaries tightened to match bash.

Covers three boundaries (all probed against bash 5.2):
1. `case` takes exactly one subject word before `in` (which may itself be
   spelled `in`); newlines are allowed before `in` but not after `case`.
2. Quotes/expansions inside non-assignment bracket words keep their normal
   meaning; only confirmed `NAME[...]=` subscripts collect them literally.
3. Misplaced case terminators (`;;` outside case) are syntax errors.

Error messages differ between shells, so error cases compare exit status
and stdout only; success cases require identical behavior.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestCaseSubjectConformance(ConformanceTest):
    """`case` subject parsing matches bash."""

    def test_single_subject_forms_identical(self):
        self.assert_identical_behavior('case a in a) echo hi;; esac')
        self.assert_identical_behavior('case "a b" in "a b") echo hi;; esac')
        self.assert_identical_behavior('case a"b"c in abc) echo hi;; esac')
        self.assert_identical_behavior(
            'x="a b"; case $x in "a b") echo match;; *) echo nomatch;; esac')
        self.assert_identical_behavior(
            'case $(echo a b) in "a b") echo hi;; esac')

    def test_in_as_subject_identical(self):
        self.assert_identical_behavior('case in in in) echo hi;; esac')
        self.assert_identical_behavior('case if in if) echo hi;; esac')

    def test_newlines_before_in_identical(self):
        self.assert_identical_behavior('case a\nin a) echo hi;; esac')
        self.assert_identical_behavior('case a\n\n\nin a) echo hi;; esac')

    def test_empty_case_identical(self):
        self.assert_identical_behavior('case a in esac')

    def test_for_loop_variable_named_in_identical(self):
        self.assert_identical_behavior('for in in 1 2; do echo $in; done')

    def test_malformed_case_headers_rejected_like_bash(self):
        """Both shells reject these with a syntax error and no stdout."""
        for command in (
            'case a b in a) echo hi;; esac',
            'case a b c in a) echo hi;; esac',
            'case a; in a) echo hi;; esac',
            'case\na in a) echo hi;; esac',
            'case a esac',
            'case in a) echo hi;; esac',
            'case a in esac) echo hi;; esac',
        ):
            psh_result = self.framework.run_in_psh(command)
            bash_result = self.framework.run_in_bash(command)
            assert bash_result.exit_code != 0, f"bash accepted: {command}"
            assert psh_result.exit_code != 0, f"psh accepted: {command}"
            assert psh_result.stdout == bash_result.stdout == '', command


class TestBracketWordQuoteConformance(ConformanceTest):
    """Quotes/expansions in bracket words match bash."""

    def test_quoted_bracket_words_identical(self):
        # Words chosen so the glob pattern can never match a file.
        self.assert_identical_behavior('echo zqz["ok"]')
        self.assert_identical_behavior('echo zqz[b"c"d]e')
        self.assert_identical_behavior('echo ["a"]zqz')
        self.assert_identical_behavior('echo zqz[\\"]')

    def test_expansions_in_bracket_words_identical(self):
        self.assert_identical_behavior('v=abc; echo zqz[$v]')
        self.assert_identical_behavior('echo zqz[$((1+1))]')

    def test_array_assignment_subscripts_identical(self):
        self.assert_identical_behavior('a[0]=v; echo ${a[0]}')
        self.assert_identical_behavior(
            'declare -A h; h["key"]=v; echo ${h["key"]}')
        self.assert_identical_behavior(
            'declare -A h; h["k 1"]=v; echo "${h["k 1"]}"')
        self.assert_identical_behavior(
            'a[$(echo 1)]=y; echo ${a[1]}')
        self.assert_identical_behavior(
            'a[$(echo 1 + 1)]=y; echo ${a[2]}')

    def test_unterminated_quote_in_bracket_word_rejected_like_bash(self):
        for command in (
            'echo zqz["unterminated',
            "echo zqz['unterm",
            'echo arr["x$USER]',
        ):
            psh_result = self.framework.run_in_psh(command)
            bash_result = self.framework.run_in_bash(command)
            assert bash_result.exit_code != 0, f"bash accepted: {command}"
            assert psh_result.exit_code != 0, f"psh accepted: {command}"
            assert psh_result.stdout == bash_result.stdout == '', command


class TestMisplacedCaseTerminatorConformance(ConformanceTest):
    """`;;` / `;&` / `;;&` outside case are syntax errors in both shells."""

    def test_misplaced_terminators_rejected_like_bash(self):
        for command in (
            'echo a ;; echo b',
            ';; echo b',
            'echo a ;& echo b',
            'echo a ;;& echo b',
            'if true; then echo a ;; fi',
        ):
            psh_result = self.framework.run_in_psh(command)
            bash_result = self.framework.run_in_bash(command)
            assert bash_result.exit_code != 0, f"bash accepted: {command}"
            assert psh_result.exit_code != 0, f"psh accepted: {command}"
            assert psh_result.stdout == bash_result.stdout == '', command

    def test_terminators_inside_case_identical(self):
        self.assert_identical_behavior('case x in x) echo ok;; esac')
        self.assert_identical_behavior(
            'case x in x) echo a;& y) echo b;; esac')
        self.assert_identical_behavior(
            'case x in x) echo a;;& *) echo b;; esac')
