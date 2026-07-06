r"""Conformance tests for the central locale service (LC_CTYPE / LC_COLLATE).

psh reads the effective locale from the environment at startup
(``psh/core/locale_service.py``) and honours it for collation (Stage 1), case
conversion (Stage 2), and POSIX character-class membership (Stage 3). These
tests pin an explicit locale in the subprocess env (the framework defaults to
``LC_ALL=C``; passing ``env=`` overrides it for BOTH shells) and assert psh
matches the SAME live bash under the SAME locale. Because the class-membership
backend is the host libc's own ``iswctype`` (via ctypes), assert_identical is
valid on both the macOS gate and the Linux nightly.

The order-of-evidence for every row here is the design's bash truth table
(docs/architecture/locale_service_design_2026-07-06.md §2) re-verified live.
"""

UTF8 = {'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8'}
C = {'LC_ALL': 'C', 'LANG': 'C'}
# A self-contained corpus of oddly-named files (no e/E case-collision — APFS is
# case-insensitive) created before globbing, so each subprocess is hermetic.
MKFILES = "> a; > B; > e; > z; > é; > 3; > ٣; > _x;"

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestCollationOrdering(ConformanceTest):
    """Glob results are ordered by LC_COLLATE, like bash (design §2c)."""

    def test_glob_star_order_c_locale(self):
        # C locale: codepoint (byte) order — psh's historical behaviour.
        self.assert_identical_behavior(f"{MKFILES} echo *", env=C)

    def test_glob_star_order_utf8_locale(self):
        # en_US.UTF-8: dictionary collation (é next to e, a before B).
        self.assert_identical_behavior(f"{MKFILES} echo *", env=UTF8)


class TestBracketComparisonCollation(ConformanceTest):
    """`[[ < ]]` / `[[ > ]]` honour LC_COLLATE (design §2f)."""

    def test_a_lt_B_c(self):
        self.assert_identical_behavior("[[ a < B ]]; echo $?", env=C)

    def test_a_lt_B_utf8(self):
        # true under en_US.UTF-8 (a sorts before B), false under C.
        self.assert_identical_behavior("[[ a < B ]]; echo $?", env=UTF8)

    def test_B_lt_a_utf8(self):
        self.assert_identical_behavior("[[ B < a ]]; echo $?", env=UTF8)

    def test_eacute_lt_f_utf8(self):
        self.assert_identical_behavior("[[ é < f ]]; echo $?", env=UTF8)

    def test_gt_operator_utf8(self):
        self.assert_identical_behavior("[[ B > a ]]; echo $?", env=UTF8)


class TestTestBuiltinComparisonIsByteOrder(ConformanceTest):
    r"""`test`/`[` `<`/`>` use BYTE order in EVERY locale — UNLIKE `[[ < ]]`.

    bash's `[ a \< B ]` is false under both C and en_US.UTF-8 (verified live),
    so psh keeps codepoint order for the test builtin while `[[ < ]]` collates.
    """

    def test_bracket_byte_order_c(self):
        self.assert_identical_behavior("[ a \\< B ]; echo $?", env=C)

    def test_bracket_byte_order_utf8(self):
        self.assert_identical_behavior("[ a \\< B ]; echo $?", env=UTF8)

    def test_test_builtin_byte_order_utf8(self):
        self.assert_identical_behavior("test a \\< B; echo $?", env=UTF8)


class TestCaseConversionLocaleGated(ConformanceTest):
    """^^ / ,, / @U / @L / @u / declare -u|-l are locale-gated (design §2e).

    Under C, bash case-maps ASCII only (café -> CAFé); under UTF-8 it maps
    Unicode (café -> CAFÉ). psh reproduces both. The ß -> "SS" length bug on
    @U is fixed (ß stays ß in every locale, as bash does).
    """

    # ${x^^} / ${x,,}
    def test_upper_cafe_c(self):
        self.assert_identical_behavior('x=café; echo "${x^^}"', env=C)

    def test_upper_cafe_utf8(self):
        self.assert_identical_behavior('x=café; echo "${x^^}"', env=UTF8)

    def test_lower_CAFE_c(self):
        self.assert_identical_behavior('x=CAFÉ; echo "${x,,}"', env=C)

    def test_lower_CAFE_utf8(self):
        self.assert_identical_behavior('x=CAFÉ; echo "${x,,}"', env=UTF8)

    def test_upper_omega_utf8(self):
        self.assert_identical_behavior('x=ω; echo "${x^^}"', env=UTF8)

    def test_upper_omega_c(self):
        self.assert_identical_behavior('x=ω; echo "${x^^}"', env=C)

    # ${x@U} / @L / @u — the ß length-safety fix
    def test_at_U_sharp_s_c(self):
        self.assert_identical_behavior('x=ß; echo "${x@U}"', env=C)

    def test_at_U_sharp_s_utf8(self):
        self.assert_identical_behavior('x=ß; echo "${x@U}"', env=UTF8)

    def test_at_U_cafe_c(self):
        self.assert_identical_behavior('x=café; echo "${x@U}"', env=C)

    def test_at_U_cafe_utf8(self):
        self.assert_identical_behavior('x=café; echo "${x@U}"', env=UTF8)

    def test_at_u_eacute_c(self):
        self.assert_identical_behavior('x=é; echo "${x@u}"', env=C)

    def test_at_u_eacute_utf8(self):
        self.assert_identical_behavior('x=é; echo "${x@u}"', env=UTF8)

    def test_at_L_cafe_utf8(self):
        self.assert_identical_behavior('x=CAFÉ; echo "${x@L}"', env=UTF8)

    # declare -u / -l
    def test_declare_upper_cafe_c(self):
        self.assert_identical_behavior('declare -u x=café; echo "$x"', env=C)

    def test_declare_upper_cafe_utf8(self):
        self.assert_identical_behavior('declare -u x=café; echo "$x"', env=UTF8)

    def test_declare_lower_CAFE_utf8(self):
        self.assert_identical_behavior('declare -l x=CAFÉ; echo "$x"', env=UTF8)

    # array element folding
    def test_array_upper_utf8(self):
        self.assert_identical_behavior(
            'a=(café naïve); echo "${a[@]^^}"', env=UTF8)
