"""Reappraisal #19 T2 — declaration family: `local` converges on `declare` (H5).

These pin the behavior changes that --compare-bash cannot (stderr labels, which
carry the psh `$0` prefix bash spells differently) plus the shared-engine
consolidation. All expectations verified against bash 5.2.
"""

from psh.builtins.declaration_engine import (
    ATTRIBUTE_FLAGS,
    attributes_from_options,
    is_valid_nameref_target,
    removed_attributes_from_options,
)
from psh.core import VarAttributes


class TestSharedAttributeTable:
    """The -flag→VarAttributes mapping + -l/-u cancellation live in ONE engine
    table, shared by declare and local (no more two divergent if-chains)."""

    def test_attributes_from_options_basic(self):
        opts = {k: False for k in ATTRIBUTE_FLAGS}
        opts['integer'] = True
        opts['export'] = True
        attrs = attributes_from_options(opts)
        assert attrs & VarAttributes.INTEGER
        assert attrs & VarAttributes.EXPORT
        assert not (attrs & VarAttributes.READONLY)

    def test_case_flags_cancel(self):
        opts = {k: False for k in ATTRIBUTE_FLAGS}
        opts['lowercase'] = True
        opts['uppercase'] = True
        attrs = attributes_from_options(opts)
        assert not (attrs & VarAttributes.LOWERCASE)
        assert not (attrs & VarAttributes.UPPERCASE)

    def test_removed_attributes(self):
        opts = {f'remove_{k}': False for k in ATTRIBUTE_FLAGS}
        opts['remove_export'] = True
        assert removed_attributes_from_options(opts) & VarAttributes.EXPORT

    def test_missing_keys_default_false(self):
        # local's option dict omits 'trace'; .get() must not KeyError.
        assert attributes_from_options({'integer': True}) & VarAttributes.INTEGER


class TestNamerefTargetShape:
    """The nameref target-SHAPE check is shared so `local -n` validates like
    `declare -n` (H5 twin drift closed)."""

    def test_valid_shapes(self):
        for v in ('a', 'a0', '_x', 'a[0]', 'a[$i]', 'a[b[c]]'):
            assert is_valid_nameref_target(v), v

    def test_invalid_shapes(self):
        for v in ('1', '1bad', 'a b', 'a-b', 'a[', 'a[]', 'a[0]x', 'a[0][1]'):
            assert not is_valid_nameref_target(v), v


class TestReadonlyErrorLabel:
    """Carry 4b: `readonly` (which delegates through declare) must label its own
    diagnostics `readonly:`, not `declare:` — and its ASSIGNMENT error BARE."""

    def test_invalid_id_labeled_readonly(self, captured_shell):
        rc = captured_shell.run_command('readonly 1bad=x')
        assert rc == 1
        err = captured_shell.get_stderr()
        assert "readonly: `1bad=x': not a valid identifier" in err
        assert "declare:" not in err

    def test_bare_invalid_id_labeled_readonly(self, captured_shell):
        captured_shell.run_command('readonly 1bad')
        err = captured_shell.get_stderr()
        assert "readonly: `1bad': not a valid identifier" in err
        assert "declare:" not in err

    def test_assignment_error_is_bare(self, captured_shell):
        captured_shell.run_command('readonly r=1; readonly r=2')
        err = captured_shell.get_stderr()
        assert "r: readonly variable" in err
        # bare: neither the builtin name nor the delegated declare label
        assert "readonly: r:" not in err
        assert "declare: r:" not in err

    def test_declare_still_labeled_declare(self, captured_shell):
        captured_shell.run_command('declare 1bad=x')
        assert "declare: `1bad=x': not a valid identifier" in captured_shell.get_stderr()

    def test_typeset_labeled_typeset(self, captured_shell):
        captured_shell.run_command('readonly x=1; typeset x=2')
        assert "typeset: x: readonly variable" in captured_shell.get_stderr()


class TestMultiArgContinueOnError:
    """Carry 4a: declare/typeset/readonly arg loops are continue-on-error."""

    def test_declare_sets_later_arg_after_readonly(self, captured_shell):
        rc = captured_shell.run_command('readonly x=1; declare x=2 y=3; echo "$y"')
        assert rc == 0
        assert captured_shell.get_stdout() == "3\n"

    def test_declare_returns_1(self, captured_shell):
        captured_shell.run_command('readonly x=1; declare x=2 y=3; echo "rc=$?"')
        assert captured_shell.get_stdout() == "rc=1\n"

    def test_declare_sets_later_arg_after_invalid_id(self, captured_shell):
        captured_shell.run_command('declare 1bad=x y=3; echo "$y"')
        assert captured_shell.get_stdout() == "3\n"

    def test_readonly_sets_later_arg(self, captured_shell):
        captured_shell.run_command('readonly r=1; readonly r=2 s=3; echo "$s"')
        assert captured_shell.get_stdout() == "3\n"

    def test_readonly_command_continues(self, captured_shell):
        rc = captured_shell.run_command(
            'readonly r=1; readonly r=2 s=3; echo AFTER')
        assert rc == 0
        assert captured_shell.get_stdout() == "AFTER\n"


class TestExplicitArrayScalarAppend:
    """Carry 4d: explicit -a/-A + scalar NAME+=value appends onto element 0
    through the ONE append engine, preserving the array (no more clobber)."""

    def test_integer_append_onto_array(self, captured_shell):
        captured_shell.run_command('a=(1 2); declare -ai a+=10; echo "${a[0]}|${a[1]}"')
        assert captured_shell.get_stdout() == "11|2\n"

    def test_upper_append_onto_array(self, captured_shell):
        captured_shell.run_command('a=(ab cd); declare -au a+=x; echo "${a[0]}|${a[1]}"')
        assert captured_shell.get_stdout() == "ABX|cd\n"

    def test_textual_append_onto_array(self, captured_shell):
        captured_shell.run_command('a=(1 2); declare -a a+=10; echo "${a[0]}|${a[1]}"')
        assert captured_shell.get_stdout() == "110|2\n"

    def test_assoc_scalar_append(self, captured_shell):
        captured_shell.run_command(
            'declare -A h=([k]=5); declare -Ai h+=10; echo "${h[k]}|${h[0]}"')
        assert captured_shell.get_stdout() == "5|10\n"

    def test_scalar_base_converts_then_appends(self, captured_shell):
        captured_shell.run_command('a=5; declare -a a+=10; echo "${a[0]}"')
        assert captured_shell.get_stdout() == "510\n"

    def test_non_append_scalar_still_index0(self, captured_shell):
        captured_shell.run_command('declare -a v=5; echo "${v[0]}"')
        assert captured_shell.get_stdout() == "5\n"


class TestPlusAttrRemoval:
    """Carry 4c: +attr removal. declare +attr-with-value removes AND assigns
    (value transformed with POST-removal attrs); local now parses +attr too."""

    def test_declare_plus_x_with_value(self, captured_shell):
        captured_shell.run_command('declare -x v=hi; declare +x v=bye; declare -p v')
        assert captured_shell.get_stdout() == 'declare -- v="bye"\n'

    def test_declare_plus_i_with_value_stays_literal(self, captured_shell):
        captured_shell.run_command('declare -ix n=5; declare +i n=2+3; declare -p n')
        assert captured_shell.get_stdout() == 'declare -x n="2+3"\n'

    def test_local_plus_x_removes_export(self, captured_shell):
        captured_shell.run_command('f(){ local -x v=hi; local +x v; declare -p v; }; f')
        assert captured_shell.get_stdout() == 'declare -- v="hi"\n'

    def test_local_plus_i_bare_removes_integer(self, captured_shell):
        captured_shell.run_command(
            'f(){ local -i n=5; local +i n; n=1+2; declare -p n; }; f')
        assert captured_shell.get_stdout() == 'declare -- n="1+2"\n'

    def test_local_plus_i_with_value_stays_literal(self, captured_shell):
        captured_shell.run_command('f(){ local +i n=2+3; declare -p n; }; f')
        assert captured_shell.get_stdout() == 'declare -- n="2+3"\n'

    def test_local_plus_n_removes_nameref(self, captured_shell):
        captured_shell.run_command('f(){ x=t; local -n r=x; local +n r; declare -p r; }; f')
        assert captured_shell.get_stdout() == 'declare -- r="x"\n'

    def test_local_plus_r_refuses_on_readonly(self, captured_shell):
        rc = captured_shell.run_command(
            'f(){ local -r v=1; local +r v; echo "rc=$?"; declare -p v; }; f')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=1\ndeclare -r v="1"\n'
        assert "local: v: readonly variable" in captured_shell.get_stderr()

    def test_local_plus_x_on_shadowed_export_makes_local_unexported(self, captured_shell):
        # `export G=g; f(){ local +x G=z; }` -> local shadow non-exported (z);
        # the global stays exported (g).
        captured_shell.run_command(
            'export G=g; f(){ local +x G=z; declare -p G; }; f; declare -p G')
        assert captured_shell.get_stdout() == 'declare -- G="z"\ndeclare -x G="g"\n'


class TestLocalNamerefShapeValidation:
    """Item 3: local -n adopts declare's target-SHAPE validation (behavior)."""

    def test_invalid_id_target_rejected(self, captured_shell):
        rc = captured_shell.run_command('f(){ local -n r=1bad; echo "rc=$?"; }; f')
        assert rc == 0
        assert captured_shell.get_stdout() == "rc=1\n"
        assert "invalid variable name for name reference" in captured_shell.get_stderr()

    def test_space_target_rejected(self, captured_shell):
        captured_shell.run_command('f(){ local -n r="a b"; echo "rc=$?"; }; f')
        assert captured_shell.get_stdout() == "rc=1\n"

    def test_empty_target_rejected(self, captured_shell):
        captured_shell.run_command('f(){ local -n r=; echo "rc=$?"; }; f')
        assert captured_shell.get_stdout() == "rc=1\n"
        assert "not a valid identifier" in captured_shell.get_stderr()

    def test_array_element_target_ok(self, captured_shell):
        rc = captured_shell.run_command(
            'f(){ local arr=(a b c); local -n r=arr[1]; echo "$r"; }; f')
        assert rc == 0
        assert captured_shell.get_stdout() == "b\n"

    def test_invalid_target_continues_loop(self, captured_shell):
        # a per-arg invalid nameref target is reported and skipped, not fatal
        # (with -n, `y=3` is itself an invalid target "3", so y stays unset)
        captured_shell.run_command('f(){ local -n r=1bad y=x; echo "done"; }; f')
        assert captured_shell.get_stdout() == "done\n"
