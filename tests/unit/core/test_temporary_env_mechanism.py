"""In-process tests for the command temporary-environment mechanism
(``ScopeManager.command_temp_env``): the hidden overlay a ``VAR=x cmd`` prefix
over a builtin/external uses.

These exercise the lookup-consults / enumeration-skips / write-through / unset-
peel behaviors directly through the running shell (no subprocess), complementing
the bash-conformance battery (tests/conformance/bash/test_temporary_env_conformance.py)
and the visibility ledger (test_tempenv_visibility_ledger.py).

Enumeration output is read from the builtin's OWN stdout (no pipes — a piped
``grep`` forks and its output would bypass the captured_shell buffer), so the
"hidden" assertions check that the prefix name is absent from the full listing.
Values deferred into ``eval`` use ``\\$`` so the ``$`` reaches eval literally and
expands AFTER the prefix takes effect (POSIX: a command's own words expand
before its prefix assignments apply).
"""


class TestLookupConsultsEnumerationSkips:
    def test_prefix_visible_to_dollar_via_eval(self, captured_shell):
        captured_shell.run_command('FOO=bar eval "echo [\\$FOO]"')
        assert captured_shell.get_stdout() == "[bar]\n"

    def test_prefix_hidden_from_set(self, captured_shell):
        captured_shell.run_command('FOO=bar set')
        assert "FOO=bar" not in captured_shell.get_stdout()

    def test_prefix_hidden_from_export_p(self, captured_shell):
        captured_shell.run_command('FOO=bar export -p')
        assert 'declare -x FOO=' not in captured_shell.get_stdout()

    def test_prefix_hidden_from_declare_p_noname(self, captured_shell):
        captured_shell.run_command('FOO=bar declare -p')
        assert 'declare -x FOO=' not in captured_shell.get_stdout()

    def test_declare_p_specific_name_shows_prefix(self, captured_shell):
        captured_shell.run_command('FOO=bar declare -p FOO')
        assert captured_shell.get_stdout() == 'declare -x FOO="bar"\n'

    def test_gone_after_command(self, captured_shell):
        captured_shell.run_command(
            'FOO=bar true; echo "[${FOO+SET}${FOO-GONE}]"')
        assert captured_shell.get_stdout() == "[GONE]\n"


class TestOverrideOfExistingVariable:
    def test_temp_shadows_during_but_restored_after(self, captured_shell):
        # (captured_shell drops output past an eval boundary in one run_command,
        # so observe during and after in separate commands.)
        captured_shell.run_command('export E=orig; E=temp eval "echo during=[\\$E]"')
        assert captured_shell.get_stdout() == "during=[temp]\n"
        captured_shell.clear_output()
        captured_shell.run_command('echo after=[$E]')
        assert captured_shell.get_stdout() == "after=[orig]\n"

    def test_export_p_shows_original_not_temp(self, captured_shell):
        captured_shell.run_command('export E=orig; E=temp export -p')
        out = captured_shell.get_stdout()
        assert 'declare -x E="orig"' in out
        assert 'declare -x E="temp"' not in out

    def test_no_attribute_inheritance(self, captured_shell):
        # bash: the temporary binding is a plain exported string; a shadowed
        # -i (integer) attribute is NOT inherited.
        captured_shell.run_command('declare -i n=5; n=abc eval "echo [\\$n]"')
        assert captured_shell.get_stdout() == "[abc]\n"


class TestBodyMutation:
    def test_body_reassignment_updates_temp_only(self, captured_shell):
        captured_shell.run_command(
            'export G=global; G=temp eval "G=new; echo mid=[\\$G]"')
        assert captured_shell.get_stdout() == "mid=[new]\n"
        captured_shell.clear_output()
        captured_shell.run_command('echo after=[$G]')
        assert captured_shell.get_stdout() == "after=[global]\n"

    def test_unset_peels_temp_revealing_real(self, captured_shell):
        captured_shell.run_command(
            'export G=global; G=temp eval "unset G; echo [\\$G]"')
        assert captured_shell.get_stdout() == "[global]\n"

    def test_unset_twice_removes_real(self, captured_shell):
        captured_shell.run_command(
            'export G=global; G=temp eval "unset G; unset G; echo [\\${G-GONE}]"')
        assert captured_shell.get_stdout() == "[GONE]\n"


class TestArrayAndNamerefShadowing:
    def test_scalar_shadows_array_non_destructively(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); a=x eval "echo [\\$a]"')
        assert captured_shell.get_stdout() == "[x]\n"

    def test_array_intact_after_scalar_prefix(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); a=x true; echo "[${a[@]}]"')
        assert captured_shell.get_stdout() == "[1 2 3]\n"

    def test_nameref_prefix_writes_through_target(self, captured_shell):
        captured_shell.run_command(
            'declare -n r=t; r=x eval "echo t=[\\$t] r=[\\$r]"')
        assert captured_shell.get_stdout() == "t=[x] r=[x]\n"

    def test_nameref_target_gone_after(self, captured_shell):
        captured_shell.run_command(
            'declare -n r=t; r=x true; echo "t=[${t-UNSET}]"')
        assert captured_shell.get_stdout() == "t=[UNSET]\n"


class TestAttributeBuiltinPromotion:
    """`export`/`readonly`/`declare -x` named on a temporary-environment binding
    promotes it to a real variable that persists past the command."""

    def test_export_valueless_promotes(self, captured_shell):
        captured_shell.run_command('V=hi export V; declare -p V')
        assert captured_shell.get_stdout() == 'declare -x V="hi"\n'

    def test_readonly_valueless_promotes_with_export(self, captured_shell):
        captured_shell.run_command('V=hi readonly V; declare -p V')
        assert captured_shell.get_stdout() == 'declare -rx V="hi"\n'

    def test_export_promotes_temp_value_over_existing_real(self, captured_shell):
        captured_shell.run_command('export E=orig; E=temp export E; declare -p E')
        assert captured_shell.get_stdout() == 'declare -x E="temp"\n'

    def test_export_in_function_promotes_to_global(self, captured_shell):
        captured_shell.run_command('f(){ V=hi export V; }; f; echo "[${V-GONE}]"')
        assert captured_shell.get_stdout() == "[hi]\n"

    def test_export_promotes_only_named_var(self, captured_shell):
        captured_shell.run_command('A=1 B=2 export A; echo "[${A-N}][${B-GONE}]"')
        assert captured_shell.get_stdout() == "[1][GONE]\n"


class TestReadIfsPrefixIdiom:
    """The canonical ``IFS=: read`` / ``while IFS= read -r`` idiom: read must
    honor an IFS command-prefix (a temporary_env binding the ENUMERATION path
    skips but the LOOKUP path — which read uses — sees)."""

    def test_ifs_colon_split(self, captured_shell):
        captured_shell.run_command('IFS=: read a b c <<< "one:two:three"')
        captured_shell.run_command('echo "$a/$b/$c"')
        assert captured_shell.get_stdout() == "one/two/three\n"

    def test_empty_ifs_no_split(self, captured_shell):
        captured_shell.run_command('IFS= read -r line <<< "  keep  spaces  "')
        captured_shell.run_command('echo "[$line]"')
        assert captured_shell.get_stdout() == "[  keep  spaces  ]\n"

    def test_ifs_not_leaked_to_shell_afterward(self, captured_shell):
        captured_shell.run_command('IFS=: read a b c <<< "x:y:z"')
        # After the read command, IFS is back to the default (splitting on
        # whitespace, not ':').
        captured_shell.run_command('set -- p:q r; echo "$# [$1]"')
        assert captured_shell.get_stdout() == "2 [p:q]\n"
