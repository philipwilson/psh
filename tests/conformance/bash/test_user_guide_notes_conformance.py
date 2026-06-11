"""Conformance tests backing user-guide inline notes.

The 2026-06-11 reappraisal (H3) found several user-guide chapters claiming
features were "not supported" when they actually work. The notes were
corrected to document the features as supported; this file pins each of
those corrected claims to bash so the guide cannot rot silently again.

Covered claims (chapter: feature):
- ch10: ``!`` pipeline negation, ``|&``, ``PIPESTATUS``
- ch09: ``>|`` force clobber, ``exec 3<> file`` read-write descriptors
- ch07: bitwise compound assignment operators
- ch05/ch16: ``${!var}`` indirection, ``${!prefix*}`` name matching,
  ``${array[@]#pattern}`` element-wise pattern removal
- ch08: ``$"..."`` locale translation quoting
- ch11: ``[[ ! ... ]]`` negation (BASH_REMATCH groups are already covered
  by test_edge_cases.py)
- ch16: ``read -n`` / ``read -t`` / ``read -s``
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestPipelineNotes(ConformanceTest):
    def test_pipeline_negation_of_success(self):
        self.assert_identical_behavior('! true; echo $?')

    def test_pipeline_negation_of_failure(self):
        self.assert_identical_behavior('! false; echo $?')

    def test_pipeline_negation_in_if(self):
        self.assert_identical_behavior('if ! false; then echo ran; fi')

    def test_pipe_both_shorthand(self):
        self.assert_identical_behavior('{ echo out; echo err >&2; } |& sort')

    def test_pipestatus_array(self):
        self.assert_identical_behavior(
            'true | false | true; echo "${PIPESTATUS[@]}"')


class TestRedirectionNotes(ConformanceTest):
    def test_force_clobber_overrides_noclobber(self):
        self.assert_identical_behavior(
            'f=$(mktemp); set -o noclobber; '
            'echo forced >| "$f" && cat "$f"; rm -f "$f"')

    def test_read_write_descriptor(self):
        self.assert_identical_behavior(
            'f=$(mktemp); printf "l1\\nl2\\n" > "$f"; exec 3<> "$f"; '
            'read a <&3; read b <&3; echo "$a/$b"; exec 3>&-; rm -f "$f"')


class TestArithmeticAssignmentNotes(ConformanceTest):
    def test_bitwise_and_assign(self):
        self.assert_identical_behavior('x=12; ((x&=10)); echo $x')

    def test_bitwise_or_assign(self):
        self.assert_identical_behavior('x=12; ((x|=3)); echo $x')

    def test_bitwise_xor_assign(self):
        self.assert_identical_behavior('x=12; ((x^=10)); echo $x')

    def test_shift_left_assign(self):
        self.assert_identical_behavior('x=3; ((x<<=2)); echo $x')

    def test_shift_right_assign(self):
        self.assert_identical_behavior('x=12; ((x>>=2)); echo $x')


class TestParameterExpansionNotes(ConformanceTest):
    def test_indirect_expansion(self):
        self.assert_identical_behavior('foo=bar; bar=baz; echo "${!foo}"')

    def test_variable_name_prefix_matching(self):
        self.assert_identical_behavior(
            'MYV_A=1; MYV_B=2; OTHER=3; echo "${!MYV_*}"')

    def test_array_pattern_removal_suffix(self):
        self.assert_identical_behavior('arr=(a.txt b.txt); echo "${arr[@]%.txt}"')

    def test_array_pattern_removal_prefix(self):
        self.assert_identical_behavior('arr=(x/y/c a/b/z); echo "${arr[@]##*/}"')


class TestQuotingNotes(ConformanceTest):
    def test_locale_translation_quoting_literal(self):
        self.assert_identical_behavior('echo $"hello world"')

    def test_locale_translation_quoting_expands(self):
        self.assert_identical_behavior('x=v; echo $"val: $x"')


class TestDoubleBracketNegationNotes(ConformanceTest):
    def test_negated_unary_test(self):
        self.assert_identical_behavior(
            '[[ ! -f /nonexistent_psh_conformance ]] && echo ok')

    def test_negated_condition_with_and(self):
        self.assert_identical_behavior('[[ ! -z x && -n x ]] && echo ok')


class TestReadOptionNotes(ConformanceTest):
    def test_read_n_char_count(self):
        self.assert_identical_behavior('echo abcdef | { read -n 3 v; echo "$v"; }')

    def test_read_t_timeout(self):
        self.assert_identical_behavior('echo hi | { read -t 5 v; echo "$v"; }')

    def test_read_s_silent(self):
        self.assert_identical_behavior('echo secret | { read -s v; echo "$v"; }')
