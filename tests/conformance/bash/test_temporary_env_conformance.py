"""
Conformance tests for bash's temporary environment (``VAR=x cmd`` prefix over a
builtin/external).

bash keeps a ``VAR=x cmd`` prefix in a SEPARATE temporary environment: NAME
LOOKUP consults it (``$VAR``, ``declare -p VAR``, ``${VAR@a}``, the command's
own process environment) but whole-table ENUMERATIONS (``set`` / ``export -p``
/ ``declare -p`` with no name) skip it, and it is NOT a shell variable so it
does not inherit the shadowed variable's attributes and vanishes on teardown.

psh used to bind the prefix var as a real exported shell variable for the
command's duration, which LEAKED into those enumerations (the full-temporary_env
follow-up, closed 2026-07-09). Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestEnumerationSkipsTemporaryEnv(ConformanceTest):
    """Whole-table enumerations do NOT list a command-prefix variable."""

    def test_export_p_hides_prefix_var(self):
        self.assert_identical_behavior(
            'FOO=bar export -p | grep "^declare -x FOO=" || echo NONE')

    def test_set_hides_prefix_var(self):
        self.assert_identical_behavior('FOO=bar set | grep "^FOO=" || echo NONE')

    def test_declare_p_noname_hides_prefix_var(self):
        self.assert_identical_behavior(
            'FOO=bar declare -p | grep "^declare -x FOO=" || echo NONE')

    def test_multi_prefix_hidden_from_export_p(self):
        self.assert_identical_behavior(
            'A=1 B=2 export -p | grep -E "^declare -x [AB]=" || echo NONE')

    def test_multi_prefix_hidden_from_set(self):
        self.assert_identical_behavior(
            'A=1 B=2 set | grep -E "^[AB]=" || echo NONE')

    def test_override_shows_original_in_export_p(self):
        self.assert_identical_behavior(
            'export E=orig; E=temp export -p | grep "^declare -x E="')


class TestNameLookupConsultsTemporaryEnv(ConformanceTest):
    """Name lookup — but not enumeration — sees the command-prefix variable."""

    def test_dollar_var_via_eval(self):
        self.assert_identical_behavior('FOO=bar eval "echo [\\$FOO]"')

    def test_declare_p_specific_name(self):
        self.assert_identical_behavior('FOO=bar declare -p FOO')

    def test_attribute_operator_shows_exported(self):
        self.assert_identical_behavior('FOO=bar eval "echo attrs=\\${FOO@a}"')

    def test_prefix_reaches_external_env(self):
        self.assert_identical_behavior('FOO=bar printenv FOO || echo NONE')

    def test_prefix_reaches_env_builtin(self):
        self.assert_identical_behavior(
            'FOO=bar command env | grep "^FOO=" || echo NONE')

    def test_override_visible_during_command(self):
        self.assert_identical_behavior('export E=orig; E=temp printenv E')


class TestTemporaryEnvNotAShellVariable(ConformanceTest):
    """The prefix binding does not inherit attributes and is gone afterwards."""

    def test_no_integer_attribute_inheritance(self):
        # declare -i n=5; n=abc cmd -> the command sees plain "abc", not 0.
        self.assert_identical_behavior('declare -i n=5; n=abc eval "echo [\\$n]"')

    def test_override_drops_integer_attribute(self):
        self.assert_identical_behavior('declare -i N=5; N=10 declare -p N')

    def test_gone_after_command(self):
        self.assert_identical_behavior(
            'FOO=bar true; declare -p FOO >/dev/null 2>&1 && echo SET || echo GONE')

    def test_override_restored_after_command(self):
        self.assert_identical_behavior('export E=orig; E=temp true; printenv E')

    def test_array_shadowed_non_destructively(self):
        # a=x cmd shadows an array with a scalar for the command; array intact.
        self.assert_identical_behavior('a=(1 2 3); a=x eval "echo [\\$a]"')

    def test_array_intact_after(self):
        self.assert_identical_behavior('a=(1 2 3); a=x true; declare -p a')


class TestTemporaryEnvBodyMutation(ConformanceTest):
    """A body (eval) assignment/unset targets the temporary binding, revealing
    the shell variable underneath, and is discarded on teardown."""

    def test_body_reassignment_updates_temp_only(self):
        self.assert_identical_behavior(
            'export G=global; G=temp eval "G=new; echo [\\$G]"; echo after=[\\$G]')

    def test_unset_peels_temp_revealing_real(self):
        self.assert_identical_behavior(
            'export G=global; G=temp eval "unset G; echo [\\$G]"')

    def test_unset_twice_removes_real_too(self):
        self.assert_identical_behavior(
            'export G=global; G=temp eval "unset G; unset G; echo [\\${G-GONE}]"')


class TestAttributeBuiltinPromotesTemporaryEnv(ConformanceTest):
    """`export`/`readonly`/`declare -x` named on a temporary-environment binding
    PROMOTES it to a real variable that persists past the command (carrying the
    temp value, which wins over any real same-name variable)."""

    def test_export_valueless_promotes(self):
        self.assert_identical_behavior('V=hi export V; declare -p V 2>&1')

    def test_readonly_valueless_promotes(self):
        self.assert_identical_behavior('V=hi readonly V; declare -p V 2>&1')

    def test_declare_x_valueless_promotes(self):
        self.assert_identical_behavior('V=hi declare -x V; declare -p V 2>&1')

    def test_export_promotes_temp_value_over_real(self):
        self.assert_identical_behavior(
            'export E=orig; E=temp export E; declare -p E 2>&1; printenv E')

    def test_export_explicit_value_still_wins(self):
        self.assert_identical_behavior('V=hi export V=bye; declare -p V 2>&1')

    def test_export_in_function_promotes_to_global(self):
        self.assert_identical_behavior(
            'f(){ V=hi export V; }; f; echo "[${V-GONE}]"')

    def test_export_promotes_only_named(self):
        # Only the named var promotes; the other prefix var is discarded.
        self.assert_identical_behavior('A=1 B=2 export A; echo "[${B-GONE}]"')


class TestFunctionPrefixStillEnumerated(ConformanceTest):
    """A prefix over a FUNCTION is bash's temporary VARIABLE CONTEXT, merged into
    the function's locals — visible to enumerations run inside the body (unlike
    the builtin/external temporary environment)."""

    def test_func_body_set_lists_prefix_var(self):
        self.assert_identical_behavior(
            'f(){ set | grep "^FOO=" || echo NONE; }; FOO=bar f')

    def test_func_body_export_p_lists_prefix_var(self):
        self.assert_identical_behavior(
            'f(){ export -p | grep "FOO=" || echo NONE; }; FOO=bar f')

    def test_func_body_sees_value(self):
        self.assert_identical_behavior('f(){ echo "[$FOO]"; }; FOO=bar f')
