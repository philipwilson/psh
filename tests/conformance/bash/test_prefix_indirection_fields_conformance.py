"""Conformance tests for the quoted ${!prefix@} field-splitting form.

Pins bug M2 (reappraisal #7): ``"${!prefix@}"`` must produce one field per
matching variable name (like ``"$@"``), while ``"${!prefix*}"`` stays a
single IFS-joined field. psh previously produced a single space-joined
field for the quoted @-form.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestPrefixIndirectionFields(ConformanceTest):
    """${!prefix@} (fields) vs ${!prefix*} (scalar)."""

    def test_quoted_at_form_field_splits(self):
        self.assert_identical_behavior(
            'x1=a; x2=b; printf "[%s]" "${!x@}"')

    def test_quoted_at_form_field_count(self):
        self.assert_identical_behavior(
            'x1=a; x2=b; set -- "${!x@}"; echo $#')

    def test_quoted_star_form_single_field(self):
        self.assert_identical_behavior(
            'x1=a; x2=b; printf "[%s]" "${!x*}"')

    def test_quoted_star_form_custom_ifs(self):
        self.assert_identical_behavior(
            'IFS=,; x1=a; x2=b; printf "[%s]" "${!x*}"')

    def test_unquoted_at_form_word_splits(self):
        self.assert_identical_behavior(
            'x1=a; x2=b; printf "[%s]" ${!x@}')

    def test_for_loop_over_quoted_at(self):
        self.assert_identical_behavior(
            'm1=x; m2=y; m3=z; for v in "${!m@}"; do echo "$v"; done')

    def test_no_match_prefix_no_fields(self):
        self.assert_identical_behavior(
            'set -- "${!zzz@}"; echo $#')

    def test_affix_distribution(self):
        self.assert_identical_behavior(
            'x1=a; x2=b; printf "[%s]" "pre${!x@}post"')

    def test_indirect_single_unaffected(self):
        self.assert_identical_behavior(
            'foo=bar; bar=val; echo "${!foo}"')

    def test_array_keys_unaffected(self):
        self.assert_identical_behavior(
            'declare -a arr=(x y z); echo "${!arr[@]}"')


class TestIndirectionToArrayTarget(ConformanceTest):
    """``"${!ref}"`` where ref names an ``[@]`` array produces that array's
    FIELDS (one per element), not a single IFS-joined string (reappraisal #14).
    A ``[*]`` target keeps scalar IFS-join semantics."""

    def test_quoted_at_target_field_splits(self):
        self.assert_identical_behavior(
            'a=(p q r); ref="a[@]"; printf "[%s]" "${!ref}"')

    def test_quoted_at_target_field_count(self):
        self.assert_identical_behavior(
            'a=(1 2 3); ref="a[@]"; set -- "${!ref}"; echo "$#"')

    def test_quoted_at_target_preserves_spaces(self):
        self.assert_identical_behavior(
            'a=("a b" c); ref="a[@]"; set -- "${!ref}"; echo "$# [$1] [$2]"')

    def test_star_target_single_field(self):
        self.assert_identical_behavior(
            'a=(p q r); ref="a[*]"; printf "[%s]" "${!ref}"')

    def test_star_target_custom_ifs(self):
        self.assert_identical_behavior(
            'IFS=-; a=(p q r); ref="a[*]"; echo "${!ref}"')

    def test_specific_index_target(self):
        self.assert_identical_behavior(
            'a=(p q r); ref="a[1]"; echo "${!ref}"')

    def test_empty_array_target(self):
        self.assert_identical_behavior(
            'a=(); ref="a[@]"; set -- "${!ref}"; echo "$#"')

    def test_unquoted_at_target_word_splits(self):
        self.assert_identical_behavior(
            'a=(p q r); ref="a[@]"; set -- ${!ref}; echo "$#"')

    def test_scalar_target_unaffected(self):
        self.assert_identical_behavior(
            'x=hi; ref=x; printf "[%s]" "${!ref}"')
