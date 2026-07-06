"""
Conformance tests for the ${x~}/${x~~} case-toggle parameter expansions and
length-safe case mapping (reappraisal #18, T2-D).

`~` toggles the case of the first character (optionally gated by a pattern);
`~~` toggles every matching character — siblings of the ^/^^ upper and ,/,,
lower case-mods. Separately, bash's case-mod maps each codepoint to at most
one codepoint (no ß -> "SS" length growth).

Verified against bash 5.2. The conformance harness pins LC_ALL=C, where bash
case-maps ASCII only and leaves every non-ASCII byte untouched. As of the
locale service (Stage 2) psh case mapping is locale-GATED, so under C it too
maps ASCII only — psh and bash now agree on every codepoint under C. The cases
psh actively maps only in a UTF-8 locale (İ -> i, café -> CAFÉ, Ω -> ω) are
covered against a UTF-8 locale in test_locale_conformance.py (and the pure
mapping in tests/unit/lexer/test_case_mapping.py); the length-safety cases (ß,
ﬀ, ΐ stay put in EVERY locale) are pinned here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestScalarToggle(ConformanceTest):
    def test_toggle_first_lower(self):
        self.assert_identical_behavior('x=hello; echo "${x~}"')

    def test_toggle_first_upper(self):
        self.assert_identical_behavior('x=HELLO; echo "${x~}"')

    def test_toggle_all_mixed(self):
        self.assert_identical_behavior('x=HeLLo123; echo "${x~~}"')

    def test_toggle_first_nonletter(self):
        self.assert_identical_behavior('x=123abc; echo "${x~}"')

    def test_toggle_empty(self):
        self.assert_identical_behavior('x=; echo "[${x~}][${x~~}]"')


class TestToggleWithPattern(ConformanceTest):
    def test_toggle_first_matches(self):
        self.assert_identical_behavior('x=hello; echo "${x~h}"')

    def test_toggle_first_no_match(self):
        self.assert_identical_behavior('x=hello; echo "${x~l}"')

    def test_toggle_all_class(self):
        self.assert_identical_behavior('x=abcABC; echo "${x~~[a-c]}"')

    def test_toggle_all_wildcard(self):
        self.assert_identical_behavior('x=Hello; echo "${x~~?}"')


class TestArrayToggle(ConformanceTest):
    def test_array_at_toggle_first(self):
        self.assert_identical_behavior('a=(foo BAR bAz); echo "${a[@]~}"')

    def test_array_at_toggle_all(self):
        self.assert_identical_behavior('a=(foo BAR bAz); echo "${a[@]~~}"')

    def test_array_star_toggle_all(self):
        self.assert_identical_behavior('a=(foo BAR bAz); echo "${a[*]~~}"')

    def test_array_element_toggle(self):
        self.assert_identical_behavior('a=(hello WORLD); echo "${a[0]~}|${a[1]~~}"')

    def test_assoc_element_toggle(self):
        self.assert_identical_behavior('declare -A m=([k]=Val); echo "${m[k]~~}"')


class TestLengthSafeCaseMapping(ConformanceTest):
    """A codepoint's case mapping stays a single codepoint (no ß -> "SS")."""

    def test_sharp_s_upper(self):
        self.assert_identical_behavior('x=straße; echo "${x^^}"')

    def test_sharp_s_upper_first(self):
        self.assert_identical_behavior('x=aßb; echo "${x^^}"')

    def test_sharp_s_lower_roundtrip(self):
        self.assert_identical_behavior('x=STRAßE; echo "${x,,}"')

    def test_ff_ligature_upper(self):
        self.assert_identical_behavior('x=ﬀ; echo "${x^^}"')

    def test_iota_dialytika_tonos_upper(self):
        self.assert_identical_behavior('x=ΐ; echo "${x^^}"')

    def test_declare_upper_length_safe(self):
        self.assert_identical_behavior('declare -u x=straße; echo "$x"')

    def test_toggle_length_safe(self):
        self.assert_identical_behavior('x=aßB; echo "${x~~}"')
