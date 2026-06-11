"""Builtins consistency sweep (v0.284.0) — bash-pinned.

Regression tests for the option-parsing/error-channel convergence:
- type: clustered options, `-` operand, invalid-option usage errors,
  bare `type` succeeding (all bash-pinned).
- unset array elements: subscript evaluation delegated to the canonical
  expansion-path evaluator (negative subscripts, scalar-as-array,
  nonexistent names, bad-subscript diagnostics — all bash-pinned).
"""


class TestTypeOptionParsing:
    def test_clustered_options(self, captured_shell):
        """bash accepts clustered options: type -af NAME."""
        rc = captured_shell.run_command('type -ta true')
        assert rc == 0
        out = captured_shell.get_stdout().splitlines()
        assert out[0] == 'builtin'
        # -a also reports the external true(1) if present on PATH
        assert 'file' in out[1:] or len(out) == 1

    def test_invalid_option_usage_error(self, captured_shell):
        """bash: `type: -x: invalid option` + usage line, rc 2."""
        rc = captured_shell.run_command('type -x true')
        assert rc == 2
        err = captured_shell.get_stderr()
        assert 'type: -x: invalid option' in err
        assert 'usage: type [-afptP] name [name ...]' in err

    def test_invalid_option_inside_cluster(self, captured_shell):
        """bash reports the bad char, not the whole cluster: -afx → -x."""
        rc = captured_shell.run_command('type -afx true')
        assert rc == 2
        assert 'type: -x: invalid option' in captured_shell.get_stderr()

    def test_single_dash_is_operand(self, captured_shell):
        """bash: `type -` looks up a command named '-' (rc 1), not an option."""
        rc = captured_shell.run_command('type -')
        assert rc == 1
        assert '-: not found' in captured_shell.get_stderr()

    def test_no_operands_succeeds(self, captured_shell):
        """bash: bare `type` prints nothing and returns 0."""
        rc = captured_shell.run_command('type')
        assert rc == 0
        assert captured_shell.get_stdout() == ''

    def test_double_dash_ends_options(self, captured_shell):
        """bash: `type -- -p` treats -p as an operand."""
        rc = captured_shell.run_command('type -- -p')
        assert rc == 1
        assert '-p: not found' in captured_shell.get_stderr()


class TestUnsetArrayElement:
    def test_arithmetic_subscript(self, captured_shell):
        rc = captured_shell.run_command(
            'a=(1 2 3); unset "a[1+1]"; echo "${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == '1 2\n'

    def test_variable_subscript(self, captured_shell):
        rc = captured_shell.run_command(
            'a=(1 2 3); i=2; unset "a[$i]"; echo "${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == '1 2\n'

    def test_unevaluable_subscript_is_index_zero(self, captured_shell):
        """bash: a[junk] evaluates to a[0]."""
        rc = captured_shell.run_command(
            'a=(1 2 3); unset "a[junk]"; echo "${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == '2 3\n'

    def test_negative_subscript_counts_from_end(self, captured_shell):
        """bash: unset 'a[-1]' removes the last element."""
        rc = captured_shell.run_command(
            'a=(1 2 3); unset "a[-1]"; echo "${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == '1 2\n'

    def test_negative_subscript_out_of_range(self, captured_shell):
        """bash: out-of-range negative subscript is an error (rc 1)."""
        rc = captured_shell.run_command('a=(1 2 3); unset "a[-5]"')
        assert rc == 1
        assert 'unset: [-5]: bad array subscript' in captured_shell.get_stderr()

    def test_assoc_key_with_variable(self, captured_shell):
        rc = captured_shell.run_command(
            'declare -A m; m[k]=v; i=k; unset "m[$i]"; echo "${m[k]:-gone}"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'gone\n'

    def test_scalar_subscript_zero_unsets_variable(self, captured_shell):
        """bash treats a scalar as a one-element array: x[0] unsets x."""
        rc = captured_shell.run_command('x=5; unset "x[0]"; echo "${x:-gone}"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'gone\n'

    def test_scalar_nonzero_subscript_errors(self, captured_shell):
        rc = captured_shell.run_command('x=5; unset "x[1]"')
        assert rc == 1
        assert 'unset: x: not an array variable' in captured_shell.get_stderr()

    def test_nonexistent_name_succeeds_silently(self, captured_shell):
        """bash: unset 'nosuch[2]' is a silent success."""
        rc = captured_shell.run_command('unset "nosuch[2]"')
        assert rc == 0
        assert captured_shell.get_stderr() == ''

    def test_missing_element_succeeds(self, captured_shell):
        rc = captured_shell.run_command(
            'a=(1 2 3); unset "a[10]"; echo "rc=$? ${a[@]}"')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=0 1 2 3\n'
