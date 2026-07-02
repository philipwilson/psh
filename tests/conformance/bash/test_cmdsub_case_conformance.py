"""Conformance tests: grammar-aware command-substitution extents.

A command substitution may contain an unmatched `)` — in case patterns
(`$(case x in x) ...;; esac)`), comments, and heredoc bodies — and bash
finds the real closer by re-invoking its parser (xparse_dolparen). PSH
matches via the grammar-aware extent scanner (find_command_substitution_end
in psh/lexer/pure_helpers.py); these tests pin identical bash behavior for
the forms the user guide claims (Ch. 6 / Ch. 17 command substitution).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestCasePatternsInCommandSub(ConformanceTest):
    """Bare `pattern)` case forms inside $(...) behave like bash."""

    def test_bare_case_pattern_in_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case x in x) echo inner;; esac)')

    def test_multi_branch_and_alternation(self):
        self.assert_identical_behavior(
            'echo $(case b in a) echo A;; b) echo B;; c) echo C;; esac)')
        self.assert_identical_behavior(
            'echo $(case y in x|y) echo XY;; esac)')

    def test_fallthrough_operators_in_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case x in x) echo one;;& *) echo two;; esac)')
        self.assert_identical_behavior(
            'echo $(case x in x) echo one;& y) echo two;; esac)')

    def test_nested_and_quoted_contexts(self):
        self.assert_identical_behavior(
            'echo $(echo $(case x in x) echo i;; esac))')
        self.assert_identical_behavior(
            'echo "$(case x in x) echo dq;; esac)"')
        self.assert_identical_behavior(
            'for f in $(case x in x) echo a b;; esac); do echo "<$f>"; done')

    def test_case_keyword_only_at_command_position(self):
        # `case` as an argument is not a keyword; the first ')' closes.
        self.assert_identical_behavior('echo $(echo case in x)')


class TestHiddenParensInCommandSub(ConformanceTest):
    """Parens in comments and heredoc bodies do not close $(...)."""

    def test_comment_hides_paren(self):
        self.assert_identical_behavior('echo $(# comment with )\necho hi)')

    def test_heredoc_body_paren(self):
        self.assert_identical_behavior('echo $(cat <<EOF\n)\nEOF\n)')

    def test_quoted_delimiter_heredoc_body(self):
        self.assert_identical_behavior('echo $(cat <<"EOF"\na ) b\nEOF\n)')

    def test_multiline_case_in_cmdsub(self):
        self.assert_identical_behavior('echo $(case x in\nx) echo nl;;\nesac)')


class TestTrickyCmdsubBodies(ConformanceTest):
    """Grammar-drift battery (2026-06-12 reassessment, Risk #4): tricky
    $(...) bodies probed against bash 5.2 before being added here."""

    def test_function_def_with_brace_body_in_cmdsub(self):
        self.assert_identical_behavior('echo $(f() { echo fn; }; f)')

    def test_function_def_with_subshell_body_in_cmdsub(self):
        self.assert_identical_behavior('echo $(g() ( echo sub ); g)')

    def test_process_substitution_inside_cmdsub(self):
        self.assert_identical_behavior('echo $(cat <(echo procsub))')

    def test_case_cmdsub_inside_heredoc_body(self):
        self.assert_identical_behavior(
            'cat <<EOF\n$(case x in x) echo in-heredoc;; esac)\nEOF')

    def test_heredoc_inside_case_body_inside_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case x in x) cat <<H\nbody ) text\nH\n;; esac)')

    def test_double_quoted_pattern_containing_paren(self):
        self.assert_identical_behavior(
            'echo $(case "x)" in "x)") echo qpat;; esac)')

    def test_single_quoted_paren_pattern(self):
        self.assert_identical_behavior(
            "echo $(case ')' in ')') echo paren-pat;; esac)")

    def test_cmdsub_in_case_subject_inside_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case $(echo x) in x) echo nested-subj;; esac)')

    def test_extglob_pattern_in_cmdsub_case(self):
        # shopt on its own line: bash -c parses incrementally, so extglob
        # is active when the second line (and its $() body) is parsed.
        self.assert_identical_behavior(
            'shopt -s extglob\n'
            'echo $(case x in @(x|y)) echo extglob;; esac)')

    def test_arithmetic_with_keyword_named_variables(self):
        """`case`/`esac` as arithmetic variable names are not keywords."""
        self.assert_identical_behavior('case=5; echo $(( case + 1 ))')
        self.assert_identical_behavior('echo $(esac=2; echo $(( esac * 2 )))')

    def test_ternary_arithmetic_inside_cmdsub(self):
        self.assert_identical_behavior('echo $(echo $((2 > 1 ? 10 : 20)))')
        self.assert_identical_behavior(
            'echo $(if ((1 < 2)); then echo arith-cmd; fi)')

    def test_case_via_variable_is_not_keyword(self):
        """`case` arriving by expansion is a plain word: first `)` closes."""
        self.assert_identical_behavior(
            'v="case"; echo $($v 2>/dev/null; echo after)')

    def test_explicit_index_array_initializer_in_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(arr=([0]=q); echo ${arr[0]})')


class TestArithCmdsubDisambiguation(ConformanceTest):
    """POSIX `$((` disambiguation: arithmetic only when a matching `))`
    closes it; otherwise re-read as `$(` + subshell (reappraisal #15 A4,
    probe battery tmp/truth_a4.py vs bash 5.2)."""

    def test_subshell_fallback(self):
        self.assert_identical_behavior('echo $((echo a); echo b)')
        self.assert_identical_behavior('echo $((echo one two) | wc -w)')
        self.assert_identical_behavior('x=$((echo u); echo host); echo $x')

    def test_fallback_in_quoted_and_nested_contexts(self):
        self.assert_identical_behavior('echo "$((echo a); echo b)"')
        self.assert_identical_behavior('echo $(echo $((echo a); echo b))')
        self.assert_identical_behavior(
            'unset v; echo "${v:-$((echo a); echo b)}"')

    def test_matching_close_parens_stay_arithmetic(self):
        self.assert_identical_behavior('echo $((1+2)) $(( (1+2) * 3 ))')
        self.assert_identical_behavior('echo $(( $((1+1)) + 1 ))')
        self.assert_identical_behavior('echo $((ls))')  # unset var -> 0
        self.assert_identical_behavior('echo $( (echo x) )')


class TestCmdsubParseErrorBoundaries(ConformanceTest):
    """Unclosed $(...) at EOF: both shells fail with status 2; the stderr
    wording differs (bash: "unexpected EOF while looking for matching `)'",
    psh: "unclosed command substitution"), so compare exit codes only."""

    def _assert_both_fail_rc2(self, command: str):
        result = self.check_behavior(command)
        assert result.psh_result.exit_code == 2, (
            f"psh rc={result.psh_result.exit_code} for: {command}\n"
            f"stderr: {result.psh_result.stderr}")
        assert result.bash_result.exit_code == 2, (
            f"bash rc={result.bash_result.exit_code} for: {command}")
        assert result.psh_result.stderr and result.bash_result.stderr

    def test_unclosed_case_inside_cmdsub_at_eof(self):
        self._assert_both_fail_rc2('echo $(case x in x) echo hi;;')

    def test_unclosed_case_header_inside_cmdsub_at_eof(self):
        self._assert_both_fail_rc2('echo $(case x in')

    def test_bare_unclosed_cmdsub_at_eof(self):
        self._assert_both_fail_rc2('echo $(')
