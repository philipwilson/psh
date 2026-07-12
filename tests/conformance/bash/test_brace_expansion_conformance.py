"""
Brace expansion conformance tests (bash compatibility).

Pins two behaviors verified against bash:

1. Char-range backslash: a cross-case character range that spans the backslash
   (ASCII 92, e.g. ``{Z..a}``) emits an *empty but kept* word at the backslash
   position -- bash does NOT output a literal ``\\``, and unlike an empty list
   item the empty word is not dropped.

2. Stray-brace neighbors: stray/unmatched ``{``/``}`` around a valid brace
   group are literal text and do not prevent expanding the valid group
   (``}{a,b}{`` -> ``}a{ }b{``).
"""


from conformance_framework import ConformanceTest


class TestCharRangeBackslash(ConformanceTest):
    """Cross-case char ranges spanning the backslash match bash."""

    def test_z_to_a(self):
        self.assert_identical_behavior('echo {Z..a}')

    def test_a_to_z_full_span(self):
        self.assert_identical_behavior('echo {A..z}')

    def test_y_to_b(self):
        self.assert_identical_behavior('echo {Y..b}')

    def test_reverse_a_to_z(self):
        self.assert_identical_behavior('echo {a..Z}')

    def test_range_with_step(self):
        self.assert_identical_behavior('echo {Z..a..2}')

    def test_word_count_preserves_empty(self):
        self.assert_identical_behavior('set -- {Z..a}; echo "$#"')

    def test_pure_letter_range_unaffected(self):
        self.assert_identical_behavior('echo {a..e}')


class TestStrayBraceNeighbors(ConformanceTest):
    """Stray braces around a valid group are literal; the group still expands."""

    def test_stray_both_sides(self):
        self.assert_identical_behavior('echo }{a,b}{')

    def test_stray_close_inside_word(self):
        self.assert_identical_behavior('echo a}{b,c}d')

    def test_leading_stray_close(self):
        self.assert_identical_behavior('echo }{a,b}')

    def test_trailing_stray_open(self):
        self.assert_identical_behavior('echo {a,b}{')

    def test_leading_stray_open(self):
        self.assert_identical_behavior('echo {{a,b}')

    def test_nested_group_with_stray_neighbors(self):
        self.assert_identical_behavior('echo }{a,{b,c}}{')

    def test_no_group_stays_literal_open(self):
        self.assert_identical_behavior('echo {a,b')

    def test_no_group_stays_literal_close(self):
        self.assert_identical_behavior('echo a,b}')

    def test_valid_group_unaffected(self):
        self.assert_identical_behavior('echo x{a,b}y')

    def test_param_expansion_not_brace_expanded(self):
        self.assert_identical_behavior('HOME=/h; echo ${HOME}/{a,b}')


class TestLiteralBraceSuffix(ConformanceTest):
    """A literal ``}``/``]`` suffix on a brace group ATTACHES to each expanded
    item — it is not a shell operator (brace expansion is per-word). Previously
    psh space-joined them (``arr[{1,2}]`` -> ``arr[1 2]``) via a vestigial
    'detach' path left over from the token-stream migration (reappraisal #14)."""

    def test_array_subscript_form(self):
        self.assert_identical_behavior('echo arr[{1,2}]')

    def test_bracketed(self):
        self.assert_identical_behavior('echo [{1,2}]')

    def test_close_brace_suffix(self):
        self.assert_identical_behavior('echo {a,b}]')

    def test_double_brace(self):
        self.assert_identical_behavior('echo {{a,b}}')

    def test_sequence_with_bracket_suffix(self):
        self.assert_identical_behavior('echo x{1..3}]')

    def test_prefix_and_bracket_suffix(self):
        self.assert_identical_behavior('echo pre{a,b}suf]')

    def test_escaped_semicolon_attaches(self):
        # An escaped operator sits in the word and attaches to each item (bash).
        self.assert_identical_behavior(r'echo {a,b}\;')

    def test_dot_suffix_regression(self):
        self.assert_identical_behavior('echo {a,b}.txt')

    def test_adjacent_groups_regression(self):
        self.assert_identical_behavior('echo {a,b}{c,d}')


class TestWordStageRuntimeToggles(ConformanceTest):
    """Brace expansion runs at the Word stage reading the LIVE braceexpand
    option (task #30), so a `set`/`shopt` that actually RUNS updates it and the
    next command honours it — the 6 same-stream approximation classes the old
    token scanner got wrong are now bash-identical."""

    def test_class1_toggle_in_not_taken_branch(self):
        self.assert_identical_behavior('if false; then set +B; fi; echo {a,b}')

    def test_class1_toggle_in_uncalled_function(self):
        self.assert_identical_behavior('f() { set +B; }; echo {a,b}')

    def test_class2_loop_body_per_iteration(self):
        self.assert_identical_behavior(
            'for i in 1 2 3; do echo {a,b}; set +B; done')

    def test_class3_shadowed_set_does_not_toggle(self):
        self.assert_identical_behavior('set() { :; }; set +B; echo {a,b}')

    def test_class4_pipeline_segment_does_not_leak(self):
        self.assert_identical_behavior('true | set +B; echo {a,b}')

    def test_class5_invalid_cluster_does_not_toggle(self):
        self.assert_identical_behavior('set -zB 2>/dev/null; echo {a,b}')

    def test_class6_quoted_operand_toggles(self):
        self.assert_identical_behavior(
            'shopt -so "braceexpand"; set +o "braceexpand"; echo {a,b}')

    def test_function_body_expands_at_call_time(self):
        self.assert_identical_behavior('f() { echo {a,b}; }; set +B; f')

    def test_straight_line_toggle_off(self):
        self.assert_identical_behavior('set +B; echo {a,b}')

    def test_straight_line_toggle_off_then_on(self):
        self.assert_identical_behavior('set +B; set -B; echo {a,b}')


class TestWordStageNonExpandingPositions(ConformanceTest):
    """bash performs NO brace expansion in a case subject/pattern or a
    here-string; the Word-stage move keeps them literal (the old token-stream
    pass wrongly expanded them, corrupting parses/matches)."""

    def test_case_subject_literal(self):
        self.assert_identical_behavior('case {a,b} in *) echo sub;; esac')

    def test_case_pattern_literal_no_match(self):
        self.assert_identical_behavior(
            'case abc in {a,b}*) echo m;; *) echo no;; esac')

    def test_case_pattern_literal_exact(self):
        self.assert_identical_behavior(
            'case a in {a,b}) echo lit;; a) echo justa;; esac')

    def test_herestring_literal(self):
        self.assert_identical_behavior('cat <<< {a,b}')

    def test_herestring_prefix_suffix_literal(self):
        self.assert_identical_behavior('cat <<< a{1,2}b')


class TestWordStageVariableFusion(ConformanceTest):
    """Brace expansion precedes parameter expansion: a bare `$v` fuses a
    trailing name-char run (`$v{1,2}` -> names v1/v2) while a brace-delimited
    `${v}` does not (`${v}{1,2}` -> ${v}1/${v}2)."""

    def test_bare_var_fuses(self):
        self.assert_identical_behavior('v1=one v2=two; echo $v{1,2}')

    def test_braced_var_does_not_fuse(self):
        self.assert_identical_behavior('v1=one v2=two; echo ${v}{1,2}')

    def test_quoted_var_does_not_fuse(self):
        self.assert_identical_behavior('v=X; echo "$v"{1,2}')

    def test_prefix_var_composite(self):
        self.assert_identical_behavior('v1=one; echo pre$v{1,2}')
