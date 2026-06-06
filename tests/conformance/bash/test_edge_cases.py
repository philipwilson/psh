"""Edge-case conformance tests.

The curated conformance suite skews to common cases; this file pushes toward the
edges (quoting/word-splitting, arithmetic bases & operators, parameter-expansion
operators, globbing, brace expansion) where shells most often diverge.

Multi-match glob cases run under LC_ALL=C so sort order is byte-collation in
both shells.

Cases that currently diverge from bash are gathered in TestEdgeKnownGaps and
marked xfail; they will XPASS (and should be un-marked) once implemented.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest

C = {"LC_ALL": "C"}


class TestEdgeQuotingWordSplitting(ConformanceTest):
    def test_star_join_default_ifs(self):
        self.assert_identical_behavior('set -- a b c; printf "[%s]" "$*"')

    def test_star_join_custom_ifs(self):
        self.assert_identical_behavior('IFS=,; set -- a b c; echo "$*"')

    def test_at_join_null_ifs(self):
        self.assert_identical_behavior('IFS=; set -- a b c; printf "[%s]" "$@"')

    def test_unquoted_split_collapses_whitespace(self):
        self.assert_identical_behavior('x="  a  b  "; printf "[%s]" $x')

    def test_empty_expansion_concatenated(self):
        self.assert_identical_behavior('printf "[%s]" "${x-}"a')

    def test_quoted_at_preserves_words(self):
        self.assert_identical_behavior(
            'set -- "a b" c; for w in "$@"; do printf "<%s>" "$w"; done'
        )

    def test_at_slice_from_offset(self):
        self.assert_identical_behavior('set -- a b c d; echo "${@:2}"')

    def test_at_slice_with_length(self):
        self.assert_identical_behavior('set -- a b c d; echo "${@:2:2}"')

    def test_at_slice_variable_offset(self):
        self.assert_identical_behavior('set -- a b c d; n=3; echo "${@:n}"')

    def test_at_slice_negative_offset(self):
        self.assert_identical_behavior('set -- a b c d; echo "${@: -2}"')

    def test_at_slice_offset_zero_includes_dollar_zero(self):
        # ${@:0} includes $0; only the count/structure is checked, not $0's
        # value (which differs between shells), so compare the element count.
        self.assert_identical_behavior('set -- a b c d; set -- ${@:0}; echo "$#"')

    def test_star_slice_custom_ifs(self):
        self.assert_identical_behavior('set -- a b c d; IFS=,; echo "${*:2:2}"')


class TestEdgeArithmetic(ConformanceTest):
    def test_binary_base(self):
        self.assert_identical_behavior('echo $((2#1010))')

    def test_hex_base(self):
        self.assert_identical_behavior('echo $((16#ff))')

    def test_explicit_decimal_base(self):
        self.assert_identical_behavior('echo $((10#08))')

    def test_left_shift(self):
        self.assert_identical_behavior('echo $((1<<10))')

    def test_bitwise_not(self):
        self.assert_identical_behavior('echo $((~0))')

    def test_modulo_negative_operands(self):
        self.assert_identical_behavior('echo $((5%-3)) $((-5%3))')

    def test_power_zero(self):
        self.assert_identical_behavior('echo $((2**0))')

    def test_comma_operator(self):
        self.assert_identical_behavior('echo $(( a=3, b=4, a+b ))')

    def test_ternary(self):
        self.assert_identical_behavior('echo $(( 1 ? 2 : 3 ))')

    def test_post_increment_sequencing(self):
        self.assert_identical_behavior('i=5; echo $((i++, i)); echo $i')


class TestEdgeParameterExpansion(ConformanceTest):
    def test_substitute_all(self):
        self.assert_identical_behavior('x=abcabc; echo "${x//a/X}"')

    def test_substitute_all_delete(self):
        self.assert_identical_behavior('x=aXbXc; echo "${x//X}"')

    def test_substring_offset(self):
        self.assert_identical_behavior('x=hello; echo "${x:2}"')

    def test_substring_negative_offset(self):
        self.assert_identical_behavior('x=hello; echo "${x: -2}"')

    def test_length(self):
        self.assert_identical_behavior('x=hello; echo "${#x}"')

    def test_case_modification(self):
        self.assert_identical_behavior('x=HeLLo; echo "${x,,}" "${x^^}"')

    def test_prefix_suffix_removal(self):
        self.assert_identical_behavior('x=path/to/file; echo "${x##*/}" "${x%/*}"')

    def test_anchored_replacement(self):
        self.assert_identical_behavior('x=foobar; echo "${x/#foo/X}" "${x/%bar/Y}"')

    def test_assign_default(self):
        self.assert_identical_behavior('unset x; echo "${x:=def}" "$x"')

    def test_array_keys(self):
        self.assert_identical_behavior('arr=(x y z); echo "${!arr[@]}"')

    def test_array_slice(self):
        self.assert_identical_behavior('arr=(a b c d); echo "${arr[@]:1:2}"')

    def test_array_slice_negative_offset(self):
        self.assert_identical_behavior('arr=(a b c d); echo "${arr[@]: -2}"')

    def test_array_star_slice_custom_ifs(self):
        self.assert_identical_behavior('arr=(a b c d); IFS=,; echo "${arr[*]:1:2}"')

    def test_array_element_default_with_subscript(self):
        # Regression: ${arr[0]:-def} must still parse as default-value, not a
        # slice, even though the parameter carries an array subscript.
        self.assert_identical_behavior('arr=("" b); echo "${arr[0]:-def}"')

    def test_array_element_substring(self):
        self.assert_identical_behavior('arr=(hello world); echo "${arr[0]:1:3}"')


class TestEdgeGlobbing(ConformanceTest):
    def test_bracket_class(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch a1 a2 b1; echo a[12]', env=C
        )

    def test_hidden_files_excluded(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch .h v; echo *', env=C
        )

    def test_nomatch_is_literal(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch f.txt; echo *.txt nomatch*', env=C
        )

    def test_question_mark(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch ab ac xy; echo a?', env=C
        )


class TestEdgeBraceExpansion(ConformanceTest):
    def test_numeric_step(self):
        self.assert_identical_behavior('echo {1..5..2}')

    def test_char_step(self):
        self.assert_identical_behavior('echo {a..e..2}')

    def test_zero_padded_step(self):
        self.assert_identical_behavior('echo {00..10..5}')

    def test_cross_product(self):
        self.assert_identical_behavior('echo a{b,c}{d,e}')

    def test_list_and_sequence(self):
        self.assert_identical_behavior('echo {a,b}{1..2}')


class TestEdgePrintf(ConformanceTest):
    def test_percent_q_space(self):
        self.assert_identical_behavior('printf "%q\\n" "a b"')

    def test_percent_q_special(self):
        self.assert_identical_behavior('printf "%q\\n" "a*b?c;d"')

    def test_percent_q_empty(self):
        self.assert_identical_behavior('printf "[%q]\\n" ""')

    def test_percent_q_safe_passthrough(self):
        self.assert_identical_behavior('printf "%q\\n" abc123_./')

    def test_percent_q_control_char(self):
        self.assert_identical_behavior('printf "%q\\n" "$(printf "a\\tb")"')

    def test_percent_b_escapes(self):
        self.assert_identical_behavior('printf "%b\\n" "a\\tb"')

    def test_percent_b_cycle(self):
        self.assert_identical_behavior('printf "%b\\n" "a\\tb" "c\\td"')

    def test_percent_b_plain(self):
        self.assert_identical_behavior('printf "%b\\n" hello')


class TestEdgeRegex(ConformanceTest):
    def test_capture_groups(self):
        self.assert_identical_behavior(
            '[[ abc123 =~ ([a-z]+)([0-9]+) ]] && echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}"'
        )

    def test_full_match(self):
        self.assert_identical_behavior('[[ foobar =~ o+ ]] && echo "[${BASH_REMATCH[0]}]"')

    def test_group_count(self):
        self.assert_identical_behavior('[[ a1b2 =~ ([a-z])([0-9]) ]]; echo "${#BASH_REMATCH[@]}"')

    def test_alternation(self):
        self.assert_identical_behavior('[[ cat =~ ^(cat|dog)$ ]] && echo "${BASH_REMATCH[1]}"')

    def test_anchors(self):
        self.assert_identical_behavior('[[ foobar =~ ^foo ]] && echo anchored')

    def test_variable_regex(self):
        self.assert_identical_behavior('re="([0-9]+)"; [[ x42 =~ $re ]] && echo "${BASH_REMATCH[1]}"')

    def test_no_match_clears_rematch(self):
        self.assert_identical_behavior(
            '[[ abc =~ ([0-9]+) ]]; echo "n=${#BASH_REMATCH[@]} v=[${BASH_REMATCH[0]}]"'
        )


class TestEdgeTraps(ConformanceTest):
    """EXIT trap behavior across non-interactive entry points."""

    def test_exit_trap_runs_in_c_mode(self):
        self.assert_identical_behavior('trap "echo bye" EXIT; echo hi')

    def test_exit_trap_runs_once_with_explicit_exit(self):
        self.assert_identical_behavior('trap "echo bye" EXIT; echo hi; exit 3')

    def test_exit_trap_preserves_exit_code(self):
        self.assert_identical_behavior('trap "echo bye" EXIT; false')
