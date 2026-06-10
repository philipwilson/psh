"""Expansion correctness sweep (v0.267.0).

Bash-pinned tests for: ${!name} indirection through positionals, array
elements and special parameters; recursive arithmetic variable resolution;
tilde expansion honoring the shell's HOME; $0 in parameter expansion;
POSIX field splitting (escapes in literal text protected structurally,
backslashes in expansion data split as plain characters); and POSIX
expansion ordering for command-prefix assignments.

Every expectation here was verified against bash 5.2.
"""

import pytest


def run(shell, cmd):
    shell.run_command(cmd)
    return shell.get_stdout()


class TestIndirectExpansion:
    def test_through_positional(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; n=2; echo "[${!n}]"') == "[b]\n"

    def test_through_array_element(self, captured_shell):
        assert run(captured_shell,
                   'a=(x y z); ref="a[1]"; echo "[${!ref}]"') == "[y]\n"

    def test_through_array_at(self, captured_shell):
        assert run(captured_shell,
                   'a=(x y z); ref="a[@]"; echo "[${!ref}]"') == "[x y z]\n"

    def test_through_assoc_element(self, captured_shell):
        assert run(captured_shell,
                   'declare -A m=([k]=v); ref="m[k]"; echo "[${!ref}]"') == "[v]\n"

    def test_through_special_hash(self, captured_shell):
        # ${!#} → indirect through $# → the last positional
        assert run(captured_shell,
                   'set -- one two; echo "[${!#}]"') == "[two]\n"

    def test_through_at(self, captured_shell):
        assert run(captured_shell,
                   'ref="@"; set -- a b; echo "[${!ref}]"') == "[a b]\n"

    def test_operator_applies_to_target(self, captured_shell):
        assert run(captured_shell,
                   'x=hello ref=x; echo "[${!ref%lo}]"') == "[hel]\n"

    def test_default_operator_after_indirection(self, captured_shell):
        assert run(captured_shell,
                   'set -- a b c; n=2; echo "[${!n:-d}]"') == "[b]\n"

    def test_unset_target_uses_default(self, captured_shell):
        assert run(captured_shell,
                   'n=5; set -- a b; echo "[${!n:-unset}]"') == "[unset]\n"

    def test_out_of_range_positional_source_is_unset(self, captured_shell):
        # bash treats an out-of-range positional source as plain unset
        assert run(captured_shell, 'echo "[${!10:-none}]"') == "[none]\n"

    def test_unset_source_errors(self, captured_shell):
        # bash: "ref: invalid indirect expansion", exit status 1
        assert captured_shell.run_command('unset ref; echo "[${!ref}]"') == 1
        assert "invalid indirect expansion" in captured_shell.get_stderr()

    def test_invalid_target_name_errors(self, captured_shell):
        # bash: "9bad: invalid variable name", exit status 1
        assert captured_shell.run_command('ref="9bad"; echo "[${!ref}]"') == 1
        assert "invalid variable name" in captured_shell.get_stderr()

    def test_empty_target_errors_even_with_default(self, captured_shell):
        # the indirection error beats the :- operator (bash)
        assert captured_shell.run_command('ref=""; echo "[${!ref:-d}]"') == 1
        assert "invalid variable name" in captured_shell.get_stderr()

    def test_nameref_source_yields_target_name(self, captured_shell):
        assert run(captured_shell,
                   'declare -n nr=tgt; tgt=val; echo "[${!nr}]"') == "[tgt]\n"

    def test_prefix_listing_still_works(self, captured_shell):
        assert run(captured_shell,
                   'pre_a=1 pre_b=2; echo "${!pre_@}"') == "pre_a pre_b\n"

    def test_array_keys_still_work(self, captured_shell):
        assert run(captured_shell, 'a=(x y z); echo "${!a[@]}"') == "0 1 2\n"


class TestArithmeticVariableText:
    def test_expression_text_via_dollar(self, captured_shell):
        assert run(captured_shell, 'x="2 + 2"; echo "$(($x))"') == "4\n"

    def test_expression_text_bare_identifier(self, captured_shell):
        assert run(captured_shell, 'x="2 + 2"; echo "$((x))"') == "4\n"

    def test_reference_chain_via_dollar(self, captured_shell):
        assert run(captured_shell,
                   'y=z; z=42; x=y; echo "$(($x))"') == "42\n"

    def test_embedded_in_larger_expression(self, captured_shell):
        # textual substitution: 2 * 1+2 = 4 (bash)
        assert run(captured_shell, 'x="1+2"; echo "$((2 * $x))"') == "4\n"

    def test_unset_via_dollar_is_zero(self, captured_shell):
        assert run(captured_shell, 'unset x; echo "$(($x + 1))"') == "1\n"

    def test_braced_form(self, captured_shell):
        assert run(captured_shell, 'x="3*4"; echo "$((${x}))"') == "12\n"

    def test_invalid_text_errors(self, captured_shell):
        assert captured_shell.run_command('x="123abc"; echo "$(($x))"') == 1
        assert captured_shell.get_stdout() == ""


class TestTildeUsesShellHome:
    def test_home_assignment_changes_tilde(self, captured_shell):
        assert run(captured_shell, 'HOME=/xyz; echo ~') == "/xyz\n"

    def test_home_assignment_with_path(self, captured_shell):
        assert run(captured_shell, 'HOME=/xyz; echo ~/sub') == "/xyz/sub\n"


class TestDollarZeroParameterExpansion:
    def test_basename_of_zero(self, captured_shell):
        # In -c mode $0 is the shell name; just verify it's non-empty and
        # the operator applies (script-mode parity is covered by probes).
        out = run(captured_shell, 'echo "[${0##*/}]"')
        assert out.strip() != "[]"

    def test_zero_with_default_operator(self, captured_shell):
        out = run(captured_shell, 'echo "[${0:-empty}]"')
        assert out.strip() not in ("[]", "[empty]")


class TestFieldSplitting:
    def test_escaped_space_in_literal_not_split(self, captured_shell):
        # the \  was literal word text — never a field boundary
        assert run(captured_shell,
                   'x=1; printf "[%s]" pre\\ post$x; echo') == "[pre post1]\n"

    def test_backslash_in_expansion_is_data(self, captured_shell):
        # bash: x='a\ b'; $x splits into a\ and b
        assert run(captured_shell,
                   r'x="a\ b"; printf "[%s]" $x; echo') == "[a\\][b]\n"

    def test_backslash_with_custom_ifs(self, captured_shell):
        assert run(captured_shell,
                   r'IFS=:; x="a\:b"; printf "[%s]" $x; echo') == "[a\\][b]\n"

    def test_quoted_text_adjacent_to_expansion_not_split(self, captured_shell):
        assert run(captured_shell,
                   'x="c d"; printf "[%s]" "a b"$x; echo') == "[a bc][d]\n"

    def test_whitespace_edges_in_expansion_break_fields(self, captured_shell):
        assert run(captured_shell,
                   'x=" a b "; printf "[%s]" pre${x}post; echo') == "[pre][a][b][post]\n"

    def test_leading_nonws_delimiter_closes_field(self, captured_shell):
        assert run(captured_shell,
                   'IFS=:; x=":a"; printf "[%s]" pre$x; echo') == "[pre][a]\n"

    def test_double_nonws_delimiter_keeps_empty_field(self, captured_shell):
        assert run(captured_shell,
                   'IFS=:; x="::a"; printf "[%s]" pre$x; echo') == "[pre][][a]\n"

    def test_trailing_nonws_delimiter_closes_field(self, captured_shell):
        assert run(captured_shell,
                   'IFS=:; x="a:"; printf "[%s]" ${x}post; echo') == "[a][post]\n"

    def test_adjacent_expansions_merge_at_boundary(self, captured_shell):
        assert run(captured_shell,
                   'x="a "; y=" b"; printf "[%s]" $x$y; echo') == "[a][b]\n"

    def test_adjacent_expansions_join_without_ifs(self, captured_shell):
        assert run(captured_shell,
                   'x=a; y=b; printf "[%s]" $x$y; echo') == "[ab]\n"


class TestAssignmentExpansionOrder:
    """POSIX: a command's words are expanded BEFORE its prefix assignments."""

    def test_command_sees_prior_value(self, captured_shell):
        assert run(captured_shell, 'V=v echo "[$V]"') == "[]\n"

    def test_command_sees_old_value(self, captured_shell):
        assert run(captured_shell, 'V=old; V=new echo "[$V]"') == "[old]\n"

    def test_assignment_visible_inside_function(self, captured_shell):
        assert run(captured_shell,
                   'f() { echo "[$V]"; }; V=v f') == "[v]\n"

    def test_assignment_temporary(self, captured_shell):
        assert run(captured_shell, 'V=v; V=n true; echo "[$V]"') == "[v]\n"

    def test_assignments_persist_when_command_expands_away(self, captured_shell):
        # bash: `V=v $EMPTY` leaves V set in the current shell
        assert run(captured_shell,
                   'unset E V; V=v $E; echo "[$V]"') == "[v]\n"

    def test_sequential_assignment_values(self, captured_shell):
        # B=$A sees the A=1 to its left (bash); both are temporary
        assert run(captured_shell,
                   'unset A B; f() { echo "[$B]"; }; A=1 B=$A f') == "[1]\n"

    def test_sequential_pure_assignments(self, captured_shell):
        assert run(captured_shell,
                   'unset A B; A=1 B=$A; echo "[$B]"') == "[1]\n"

    def test_expanded_command_name_uses_prior_value(self, captured_shell):
        assert run(captured_shell,
                   'BAR=echo; BAR=printf $BAR ok') == "ok\n"
