"""Per-element value operators on the positional $*/$@ views.

Reappraisal #17 F1: case modification (^ ^^ , ,,) and substitution
(/ // /# /%) on the positional ``*`` view used to run on the IFS-joined
string; bash applies every value-level operator PER ELEMENT and joins
afterwards, so the separator never participates in matching and anchored
patterns anchor at each element. The ``@`` scalar view (string contexts
like here-docs) shares the routing via ``_expand_positional_view``.

Controls pin the paths that were already correct: removal operators,
slices, @X transforms, the quoted "${@...}" field path, and the array
${a[*]...} view. All expectations bash-5.2-verified
(tmp/probes-r17t2-startilde/).
"""


class TestStarViewCaseModPerElement:
    def test_upper_first_per_element(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo "${*^}"')
        assert captured_shell.get_stdout() == "Foo Bar\n"

    def test_upper_all_per_element(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo "${*^^}"')
        assert captured_shell.get_stdout() == "FOO BAR\n"

    def test_lower_first_per_element(self, captured_shell):
        captured_shell.run_command('set -- FOO BAR; echo "${*,}"')
        assert captured_shell.get_stdout() == "fOO bAR\n"

    def test_lower_all_per_element(self, captured_shell):
        captured_shell.run_command('set -- FOO BAR; echo "${*,,}"')
        assert captured_shell.get_stdout() == "foo bar\n"

    def test_casemod_with_pattern_per_element(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo "${*^[fb]}"')
        assert captured_shell.get_stdout() == "Foo Bar\n"

    def test_custom_ifs_separator_not_modified(self, captured_shell):
        # The join separator (IFS[0] = 'o') must not be case-modified and
        # must not shield the second element from modification.
        captured_shell.run_command('IFS=o; set -- foo bar; echo "${*^}"')
        assert captured_shell.get_stdout() == "FoooBar\n"

    def test_empty_ifs_join(self, captured_shell):
        captured_shell.run_command('IFS=; set -- foo bar; echo "${*^}"')
        assert captured_shell.get_stdout() == "FooBar\n"

    def test_unquoted_star_casemod(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo ${*^}')
        assert captured_shell.get_stdout() == "Foo Bar\n"


class TestStarViewSubstitutionPerElement:
    def test_separator_never_matches(self, captured_shell):
        # IFS=o joins with 'o'; per-element substitution must leave the
        # separator alone (joined-string application gave f___f).
        captured_shell.run_command('IFS=o; set -- fo of; echo "${*//o/_}"')
        assert captured_shell.get_stdout() == "f_o_f\n"

    def test_anchored_prefix_each_element(self, captured_shell):
        captured_shell.run_command('set -- abc abd; echo "${*/#ab/X}"')
        assert captured_shell.get_stdout() == "Xc Xd\n"

    def test_anchored_suffix_each_element(self, captured_shell):
        captured_shell.run_command('set -- abc abd; echo "${*/%bc/Y}"')
        assert captured_shell.get_stdout() == "aY abd\n"

    def test_pattern_cannot_span_elements(self, captured_shell):
        # 'a*a' spans "ab ba" only in the joined string; bash finds no
        # match inside either element.
        captured_shell.run_command('set -- ab ba; echo "${*/a*a/X}"')
        assert captured_shell.get_stdout() == "ab ba\n"

    def test_empty_anchored_pattern_each_element(self, captured_shell):
        captured_shell.run_command('set -- abc abd; echo "${*/#/P}"')
        assert captured_shell.get_stdout() == "Pabc Pabd\n"

    def test_no_params_empty(self, captured_shell):
        captured_shell.run_command('set --; echo "[${*//o/_}]"')
        assert captured_shell.get_stdout() == "[]\n"


class TestAtViewStringContexts:
    """The @ scalar path serves string contexts (here-doc bodies,
    double-quoted string data) via expand_string_variables. End-to-end
    heredoc coverage lives in the golden pins (at_view_heredoc_*); here
    the scalar entry point is exercised directly.
    """

    def test_string_context_casemod_both_views(self, captured_shell):
        captured_shell.run_command('set -- p q')
        ve = captured_shell.expansion_manager.variable_expander
        assert ve.expand_string_variables('${@^} ${*^}') == 'P Q P Q'

    def test_string_context_anchored_subst(self, captured_shell):
        captured_shell.run_command('set -- abc abd')
        ve = captured_shell.expansion_manager.variable_expander
        assert ve.expand_string_variables('${@/#ab/X}') == 'Xc Xd'

    def test_string_context_subst_custom_ifs(self, captured_shell):
        # @ joins with spaces regardless of IFS; * joins with IFS[0].
        captured_shell.run_command('IFS=o; set -- fo of')
        ve = captured_shell.expansion_manager.variable_expander
        assert ve.expand_string_variables('${@//o/_} ${*//o/_}') == 'f_ _f f_o_f'


class TestControlsUnchanged:
    """Paths that were already correct must stay correct."""

    def test_removal_per_element(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo "${*#f}"')
        assert captured_shell.get_stdout() == "oo bar\n"

    def test_quoted_at_fields_casemod(self, captured_shell):
        captured_shell.run_command(
            'set -- foo bar; printf "[%s]" "${@^}"; echo')
        assert captured_shell.get_stdout() == "[Foo][Bar]\n"

    def test_array_star_view_subst(self, captured_shell):
        captured_shell.run_command('IFS=o; a=(fo of); echo "${a[*]//o/_}"')
        assert captured_shell.get_stdout() == "f_o_f\n"

    def test_conditional_operators_use_joined_view(self, captured_shell):
        # ${*-d} substitutes the JOINED view (bash) — must NOT become
        # per-element.
        captured_shell.run_command('IFS=:; set -- a b; echo "${*-d}"')
        assert captured_shell.get_stdout() == "a:b\n"

    def test_star_slice_still_ifs_joined(self, captured_shell):
        captured_shell.run_command('IFS=o; set -- a b c; echo "${*:1:2}"')
        assert captured_shell.get_stdout() == "aob\n"

    def test_star_transform_per_element(self, captured_shell):
        captured_shell.run_command('set -- foo bar; echo "${*@U}"')
        assert captured_shell.get_stdout() == "FOO BAR\n"

    def test_count_forms(self, captured_shell):
        captured_shell.run_command('set -- a b c; echo "${#*} ${#@}"')
        assert captured_shell.get_stdout() == "3 3\n"

    def test_nounset_empty_views_ok(self, captured_shell):
        rc = captured_shell.run_command('set -u; set --; echo "[${*^}]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[]\n"


class TestArrayStarViewOperandProtection:
    """${a[*]:-'p q'}: a single conditional field keeps operand quote
    protection through the [*] join (v0.606 disclosure)."""

    def test_default_operand_one_field(self, captured_shell):
        captured_shell.run_command(
            "a=(); printf '[%s]' ${a[*]:-'p q'}; echo")
        assert captured_shell.get_stdout() == "[p q]\n"

    def test_plus_operand_one_field(self, captured_shell):
        captured_shell.run_command(
            "a=(x); printf '[%s]' ${a[*]:+'p q'}; echo")
        assert captured_shell.get_stdout() == "[p q]\n"

    def test_quoted_expansion_operand_one_field(self, captured_shell):
        captured_shell.run_command(
            'a=(); b="p q"; printf "[%s]" ${a[*]:-"$b"}; echo')
        assert captured_shell.get_stdout() == "[p q]\n"

    def test_unprotected_operand_still_splits(self, captured_shell):
        captured_shell.run_command(
            'a=(); b="p q"; printf "[%s]" ${a[*]:-$b}; echo')
        assert captured_shell.get_stdout() == "[p][q]\n"

    def test_multi_element_view_still_joins_and_splits(self, captured_shell):
        captured_shell.run_command(
            'a=("p q" r); printf "[%s]" ${a[*]:-z}; echo')
        assert captured_shell.get_stdout() == "[p][q][r]\n"
