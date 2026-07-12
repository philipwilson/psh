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


class TestPosixClassMembership(ConformanceTest):
    """POSIX [:class:] membership is locale-sensitive across ALL match sites
    (design §2a-2c). The host-libc iswctype backend makes assert_identical valid
    on macOS AND the Linux nightly. Under C, classes are ASCII-only (unchanged);
    under UTF-8, é is [:alpha:], ٣ is [:digit:] on this host, etc.
    """

    # [[ string == [[:class:]] ]]
    def test_alpha_eacute_c(self):
        self.assert_identical_behavior('[[ é == [[:alpha:]] ]]; echo $?', env=C)

    def test_alpha_eacute_utf8(self):
        self.assert_identical_behavior('[[ é == [[:alpha:]] ]]; echo $?', env=UTF8)

    def test_alpha_cjk_utf8(self):
        self.assert_identical_behavior('[[ 中 == [[:alpha:]] ]]; echo $?', env=UTF8)

    def test_upper_Eacute_utf8(self):
        self.assert_identical_behavior('[[ É == [[:upper:]] ]]; echo $?', env=UTF8)

    def test_lower_eacute_utf8(self):
        self.assert_identical_behavior('[[ é == [[:lower:]] ]]; echo $?', env=UTF8)

    def test_upper_eacute_negative_utf8(self):
        # é is lower, not upper — no-match in both.
        self.assert_identical_behavior('[[ é == [[:upper:]] ]]; echo $?', env=UTF8)

    def test_digit_arabic_utf8(self):
        self.assert_identical_behavior('[[ ٣ == [[:digit:]] ]]; echo $?', env=UTF8)

    def test_digit_fullwidth_utf8(self):
        self.assert_identical_behavior('[[ ３ == [[:digit:]] ]]; echo $?', env=UTF8)

    def test_alnum_arabic_utf8(self):
        self.assert_identical_behavior('[[ ٣ == [[:alnum:]] ]]; echo $?', env=UTF8)

    def test_punct_laquo_utf8(self):
        self.assert_identical_behavior('[[ « == [[:punct:]] ]]; echo $?', env=UTF8)

    def test_negated_class_utf8(self):
        self.assert_identical_behavior(
            '[[ é == [^[:digit:]] ]]; echo $?', env=UTF8)

    # case
    def test_case_alpha_c(self):
        self.assert_identical_behavior(
            'case é in [[:alpha:]]) echo yes;; *) echo no;; esac', env=C)

    def test_case_alpha_utf8(self):
        self.assert_identical_behavior(
            'case é in [[:alpha:]]) echo yes;; *) echo no;; esac', env=UTF8)

    def test_case_digit_arabic_utf8(self):
        self.assert_identical_behavior(
            'case ٣ in [[:digit:]]) echo yes;; *) echo no;; esac', env=UTF8)

    # ${var#pat} / ${var##pat*}
    def test_param_strip_alpha_c(self):
        self.assert_identical_behavior('x=éxyz; echo "${x#[[:alpha:]]}"', env=C)

    def test_param_strip_alpha_utf8(self):
        self.assert_identical_behavior('x=éxyz; echo "${x#[[:alpha:]]}"', env=UTF8)

    def test_param_strip_all_alpha_utf8(self):
        self.assert_identical_behavior('x=éé9; echo "${x##[[:alpha:]]*}"', env=UTF8)

    # =~ (ERE) honours the locale too
    def test_ere_alpha_c(self):
        self.assert_identical_behavior('[[ é =~ ^[[:alpha:]]$ ]]; echo $?', env=C)

    def test_ere_alpha_utf8(self):
        self.assert_identical_behavior('[[ é =~ ^[[:alpha:]]$ ]]; echo $?', env=UTF8)

    # pathname expansion (self-contained corpus)
    def test_glob_alpha_class_utf8(self):
        self.assert_identical_behavior(f"{MKFILES} echo [[:alpha:]]*", env=UTF8)

    def test_glob_digit_class_utf8(self):
        self.assert_identical_behavior(f"{MKFILES} echo [[:digit:]]*", env=UTF8)

    def test_glob_lower_class_utf8(self):
        self.assert_identical_behavior(f"{MKFILES} echo [[:lower:]]*", env=UTF8)

    def test_glob_alpha_class_c(self):
        self.assert_identical_behavior(f"{MKFILES} echo [[:alpha:]]*", env=C)


class TestRangesAndGlobasciiranges(ConformanceTest):
    """Bracket RANGES [a-z] stay ASCII in every locale (globasciiranges on,
    bash 5 default), and `shopt globasciiranges` is recognized (design §2d)."""

    def test_range_eacute_not_in_az_utf8(self):
        self.assert_identical_behavior('[[ é == [a-z] ]]; echo $?', env=UTF8)

    def test_range_B_not_in_az_utf8(self):
        self.assert_identical_behavior('[[ B == [a-z] ]]; echo $?', env=UTF8)

    def test_shopt_globasciiranges_query(self):
        # bash reports it `on`; psh used to error "invalid shell option name".
        self.assert_identical_behavior('shopt globasciiranges', env=C)

    def test_shopt_set_globasciiranges_ok(self):
        self.assert_identical_behavior(
            'shopt -s globasciiranges; echo $?', env=C)


class TestDynamicLocaleReactivity(ConformanceTest):
    """LC_ALL/LC_CTYPE/LC_COLLATE/LANG are REACTIVE special variables: assigning,
    unsetting, or laying one over a command re-resolves the effective locale
    mid-session, like bash (design §2g, Stage 4). Each row runs psh vs the SAME
    live bash on this host, so class-membership/collation/case answers are
    host-faithful on both the macOS gate and the Linux nightly. `en_US.UTF-8`
    (é as a letter, é↑É case, a<B collation) is platform-stable."""

    # --- assignment reacts, per name and per surface ---
    def test_assign_lc_all_reacts_ctype(self):
        self.assert_identical_behavior(
            "LC_ALL=en_US.UTF-8; [[ é == [[:alpha:]] ]]; echo $?", env=C)

    def test_assign_lc_all_reacts_collate(self):
        self.assert_identical_behavior(
            "LC_ALL=en_US.UTF-8; [[ a < B ]]; echo $?", env=C)

    def test_assign_lc_all_reacts_case(self):
        self.assert_identical_behavior(
            'LC_ALL=en_US.UTF-8; x=é; echo "${x^^}"', env=C)

    def test_export_lc_all_reacts(self):
        self.assert_identical_behavior(
            "export LC_ALL=en_US.UTF-8; [[ é == [[:alpha:]] ]]; echo $?", env=C)

    def test_assign_lc_ctype_alone_reacts(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LC_CTYPE=en_US.UTF-8; [[ é == [[:alpha:]] ]]; echo $?",
            env=C)

    def test_assign_lc_collate_alone_reacts(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LC_COLLATE=en_US.UTF-8; [[ a < B ]]; echo $?", env=C)

    def test_assign_lang_alone_reacts_ctype(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LANG=en_US.UTF-8; [[ é == [[:alpha:]] ]]; echo $?",
            env=C)

    def test_assign_lang_alone_reacts_collate(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LANG=en_US.UTF-8; [[ a < B ]]; echo $?", env=C)

    # --- unset reverts (the symmetric half of every assign pin) ---
    def test_unset_lc_all_reverts_to_c(self):
        self.assert_identical_behavior(
            "LC_ALL=en_US.UTF-8; unset LC_ALL; [[ é == [[:alpha:]] ]]; echo $?",
            env=C)

    def test_unset_lang_reverts_from_utf8_start(self):
        self.assert_identical_behavior(
            "unset LANG; [[ é == [[:alpha:]] ]]; echo $?", env=UTF8)

    def test_assign_lc_ctype_c_reverts_from_utf8_start(self):
        self.assert_identical_behavior(
            "LC_CTYPE=C; [[ é == [[:alpha:]] ]]; echo $?", env=UTF8)

    def test_assign_lc_collate_c_reverts_from_utf8_start(self):
        self.assert_identical_behavior(
            "LC_COLLATE=C; [[ a < B ]]; echo $?", env=UTF8)

    # --- precedence: LC_ALL > LC_category > LANG, re-applied on each change ---
    def test_lc_all_c_overrides_lc_ctype_utf8(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LC_CTYPE=en_US.UTF-8; LC_ALL=C; "
            "[[ é == [[:alpha:]] ]]; echo $?", env=C)

    def test_lc_ctype_c_overrides_lang_utf8(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LANG=en_US.UTF-8; LC_CTYPE=C; "
            "[[ é == [[:alpha:]] ]]; echo $?", env=C)

    # --- category independence: a ctype change leaves collation, and vice versa ---
    def test_lc_ctype_change_leaves_collation(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LC_CTYPE=en_US.UTF-8; [[ a < B ]]; echo $?", env=C)

    def test_lc_collate_change_leaves_ctype(self):
        self.assert_identical_behavior(
            "unset LC_ALL; LC_COLLATE=en_US.UTF-8; [[ é == [[:alpha:]] ]]; echo $?",
            env=C)

    # --- non-exported assignment still changes the shell's OWN behavior, and is
    #     not passed to children (LC_CTYPE is absent from the pinned ambient) ---
    def test_unexported_assignment_reacts_but_not_exported(self):
        self.assert_identical_behavior(
            'unset LC_ALL; LC_CTYPE=en_US.UTF-8; '
            '[[ é == [[:alpha:]] ]] && echo react=yes; '
            'env | grep -c "^LC_CTYPE=" || true', env=C)

    # --- temp-env overlay `LC_ALL=C cmd`: declare -u case-maps through the
    #     service, so the prefix is observable and MUST revert after ---
    def test_tempenv_prefix_up_case_map(self):
        self.assert_identical_behavior(
            'LC_ALL=en_US.UTF-8 declare -u x=café; echo "$x"', env=C)

    def test_tempenv_prefix_down_then_revert(self):
        self.assert_identical_behavior(
            'LC_ALL=en_US.UTF-8; LC_ALL=C declare -u a=café; '
            'declare -u b=café; echo "$a $b"', env=C)
