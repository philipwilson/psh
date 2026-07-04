"""Readonly and cyclic-nameref writes in arithmetic (reappraisal #17 H1).

Every arithmetic entry point — ``(( ))``, ``$(( ))``, ``let``, the three
C-style ``for`` expressions — used to silently WRITE readonly array
elements (indexed and associative, for every mutation form ``=``, ``+=``,
``++``, prefix ``++``), and a readonly SCALAR assignment in ``(( ))`` /
C-style ``for`` leaked a ReadonlyVariableError to the buffered-command
guard as "unexpected error" (aborting a ``-c`` list). Cyclic-nameref
writes leaked the same way.

bash-verified model (bash 5.2, tmp/probes-r17t1-readonly/truth_table.py):

- readonly (scalar, array element, either array kind, any mutation form):
  "NAME: readonly variable" on stderr, the arithmetic EVALUATION aborts
  (later comma-operands never run), the command fails with status 1,
  execution continues, the value is unchanged.
- cyclic-nameref WRITE inside arithmetic: bash only WARNS and drops the
  assignment; evaluation continues and the status comes from the value.
- cyclic-nameref LOOP-VARIABLE binding (``for na in ...``): warn, status
  1, loop abandoned, execution continues.
"""

import pytest


def _unchanged(shell, expr, expected):
    shell.run_command(f'echo "{expr}"')
    assert shell.get_stdout().strip().splitlines()[-1] == expected


class TestReadonlyIndexedArrayElementArithCommand:
    """(( )) may not write elements of a readonly indexed array."""

    @pytest.mark.parametrize("mutation", [
        "a[0]=9", "a[0]+=5", "a[0]*=3", "a[0]++", "a[0]--", "++a[0]", "--a[0]",
    ])
    def test_mutation_rejected_value_unchanged(self, captured_shell, mutation):
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command(f"(( {mutation} ))")
        assert rc == 1
        assert "a: readonly variable" in shell.get_stderr()
        assert "unexpected error" not in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${a[0]} ${a[1]}", "1 2")

    def test_second_element_pre_increment(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command("(( ++a[1] ))")
        assert rc == 1
        assert "a: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${a[1]}", "2")

    def test_evaluation_aborts_midexpression(self, captured_shell):
        # bash: `(( a[0]=9, x=1 ))` leaves x unset — the readonly failure
        # aborts the whole evaluation, not just the one assignment.
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command("(( a[0]=9, x=1 ))")
        assert rc == 1
        shell.clear_output()
        _unchanged(shell, "x=[${x-unset}]", "x=[unset]")

    def test_readonly_array_read_still_allowed(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command("(( v = a[0] + a[1] ))")
        assert rc == 0
        assert shell.get_stderr() == ""
        shell.clear_output()
        _unchanged(shell, "$v", "3")


class TestReadonlyAssociativeArrayElementArithCommand:
    """(( )) may not write elements of a readonly associative array."""

    @pytest.mark.parametrize("mutation", ["m[k]=9", "m[k]+=5", "m[k]++"])
    def test_mutation_rejected_value_unchanged(self, captured_shell, mutation):
        shell = captured_shell
        shell.run_command("declare -A m=([k]=1); readonly m")
        rc = shell.run_command(f"(( {mutation} ))")
        assert rc == 1
        assert "m: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${m[k]}", "1")


class TestReadonlyScalarArithCommand:
    """Readonly SCALAR failures in (( )) report cleanly and continue."""

    def test_paren_assign_reports_and_returns_1(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly r=5")
        rc = shell.run_command("(( r=9 ))")
        assert rc == 1
        # bash's message and flow — NOT "unexpected error" + abort.
        assert "r: readonly variable" in shell.get_stderr()
        assert "unexpected error" not in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$r", "5")

    @pytest.mark.parametrize("mutation", ["r+=4", "r++", "++r"])
    def test_all_mutation_forms(self, captured_shell, mutation):
        shell = captured_shell
        shell.run_command("readonly r=5")
        rc = shell.run_command(f"(( {mutation} ))")
        assert rc == 1
        assert "r: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$r", "5")

    def test_readonly_scalar_with_subscript(self, captured_shell):
        # `(( s[0]=9 ))` on a readonly scalar goes through the array
        # creation/conversion fallthrough — still rejected (bash).
        shell = captured_shell
        shell.run_command("readonly s=5")
        rc = shell.run_command("(( s[0]=9 ))")
        assert rc == 1
        assert "s: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$s", "5")

    def test_nameref_to_readonly_reports_target_name(self, captured_shell):
        # bash reports the RESOLVED target name ("ro", not "r").
        shell = captured_shell
        shell.run_command("declare -n r=ro; readonly ro=5")
        rc = shell.run_command("(( r=9 ))")
        assert rc == 1
        assert "ro: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$ro", "5")

    def test_shell_continues_after_error(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly r=5")
        shell.run_command("(( r=9 ))")
        shell.clear_output()
        rc = shell.run_command("echo continued")
        assert rc == 0
        assert shell.get_stdout() == "continued\n"


class TestReadonlyArithmeticExpansion:
    """$(( )) may not write readonly variables/elements either."""

    @pytest.mark.parametrize("mutation", ["a[0]=9", "a[0]+=5", "a[0]++", "++a[1]"])
    def test_array_element_mutation_rejected(self, captured_shell, mutation):
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command(f"echo $(( {mutation} ))")
        assert rc == 1
        assert "a: readonly variable" in shell.get_stderr()
        # the failed expansion suppresses the echo (bash)
        assert shell.get_stdout() == ""
        shell.clear_output()
        _unchanged(shell, "${a[0]} ${a[1]}", "1 2")

    def test_assoc_element_rejected(self, captured_shell):
        shell = captured_shell
        shell.run_command("declare -A m=([k]=1); readonly m")
        rc = shell.run_command("echo $(( m[k]=9 ))")
        assert rc == 1
        assert "m: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${m[k]}", "1")


class TestReadonlyLet:
    """let may not write readonly variables/elements."""

    @pytest.mark.parametrize("mutation", ["a[0]=9", "a[0]+=5", "a[0]++"])
    def test_array_element_mutation_rejected(self, captured_shell, mutation):
        shell = captured_shell
        shell.run_command("readonly -a a=(1 2)")
        rc = shell.run_command(f"let '{mutation}'")
        assert rc == 1
        assert "a: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${a[0]} ${a[1]}", "1 2")

    def test_assoc_element_rejected(self, captured_shell):
        shell = captured_shell
        shell.run_command("declare -A m=([k]=1); readonly m")
        rc = shell.run_command("let 'm[k]=9'")
        assert rc == 1
        assert "m: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "${m[k]}", "1")

    def test_scalar_rejected(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly r=5")
        rc = shell.run_command("let 'r=9'")
        assert rc == 1
        assert "r: readonly variable" in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$r", "5")


class TestCStyleForReadonly:
    """The three C-style for expressions report readonly and continue."""

    def test_init_reports_and_skips_loop(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly z=1")
        rc = shell.run_command("for ((z=0; z<3; z++)); do echo body; done")
        assert rc == 1
        assert "z: readonly variable" in shell.get_stderr()
        assert "unexpected error" not in shell.get_stderr()
        assert shell.get_stdout() == ""  # loop never ran

    def test_condition_reports_and_stops(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly z=1")
        rc = shell.run_command("for ((i=0; z++ < 3; i++)); do echo body; done")
        assert rc == 1
        assert "z: readonly variable" in shell.get_stderr()
        assert shell.get_stdout() == ""

    def test_update_reports_after_one_iteration(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly z=1")
        rc = shell.run_command("for ((i=0; i<2; z++)); do echo body; done")
        assert rc == 1
        assert "z: readonly variable" in shell.get_stderr()
        assert shell.get_stdout() == "body\n"  # body ran once (bash)

    def test_shell_continues_after_error(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly z=1")
        shell.run_command("for ((z=0; z<3; z++)); do echo body; done")
        shell.clear_output()
        rc = shell.run_command("echo continued")
        assert rc == 0
        assert shell.get_stdout() == "continued\n"


class TestEnhancedTestReadonly:
    """[[ $((r=9)) -eq 9 ]]: report the failure, status 1, continue."""

    def test_arith_operand_readonly(self, captured_shell):
        shell = captured_shell
        shell.run_command("readonly r=5")
        rc = shell.run_command("[[ $((r=9)) -eq 9 ]]")
        assert rc == 1
        assert "r: readonly variable" in shell.get_stderr()
        assert "unexpected error" not in shell.get_stderr()
        shell.clear_output()
        _unchanged(shell, "$r", "5")


class TestNamerefCycleInArithmetic:
    """bash: a cyclic-nameref WRITE inside arithmetic warns and drops the
    assignment; evaluation continues with the value. A LOOP-VARIABLE
    binding failure is an error (status 1, loop abandoned)."""

    def test_paren_assign_nonzero_value_is_success(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; (( na=5 )); echo after=$?')
        captured = capsys.readouterr()
        assert rc == 0
        assert "after=0" in captured.out
        assert "circular name reference" in captured.err
        assert "unexpected error" not in captured.err

    def test_paren_assign_zero_value_is_failure(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; (( na=0 )); echo after=$?')
        captured = capsys.readouterr()
        assert rc == 0
        assert "after=1" in captured.out
        assert "circular name reference" in captured.err

    def test_subscripted_write_warns_and_continues(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; (( na[0]=5 )); echo after=$?')
        captured = capsys.readouterr()
        assert rc == 0
        assert "after=0" in captured.out
        assert "circular name reference" in captured.err

    def test_expansion_write_warns_and_keeps_value(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; echo $((na=5))')
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == "5\n"
        assert "circular name reference" in captured.err

    def test_let_write_warns_and_continues(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; let na=5; echo after=$?')
        captured = capsys.readouterr()
        assert rc == 0
        assert "after=0" in captured.out
        assert "circular name reference" in captured.err

    def test_for_loop_variable_binding_is_error(self, shell, capsys):
        rc = shell.run_command(
            'declare -n na=nb; declare -n nb=na; for na in 1 2; do echo body; done')
        captured = capsys.readouterr()
        assert rc == 1
        assert "body" not in captured.out
        assert "circular name reference" in captured.err
        assert "unexpected error" not in captured.err


class TestUnreadonlyArithWritesStillWork:
    """Controls: everything that must keep working."""

    @pytest.mark.parametrize("mutation,expected", [
        ("a[0]=9", "9"), ("a[0]+=5", "6"), ("a[0]++", "2"), ("++a[0]", "2"),
    ])
    def test_indexed_mutations(self, captured_shell, mutation, expected):
        shell = captured_shell
        shell.run_command("a=(1 2)")
        rc = shell.run_command(f"(( {mutation} ))")
        assert rc == 0
        assert shell.get_stderr() == ""
        shell.clear_output()
        _unchanged(shell, "${a[0]}", expected)

    def test_assoc_mutation(self, captured_shell):
        shell = captured_shell
        shell.run_command("declare -A m=([k]=1)")
        assert shell.run_command("(( m[k]=9 ))") == 0
        shell.clear_output()
        _unchanged(shell, "${m[k]}", "9")

    def test_array_creation_via_arith(self, captured_shell):
        shell = captured_shell
        assert shell.run_command("(( b[3]=7 ))") == 0
        shell.clear_output()
        _unchanged(shell, "${b[3]}", "7")

    def test_plain_nameref_write_through(self, captured_shell):
        shell = captured_shell
        shell.run_command("declare -n p=q")
        assert shell.run_command("(( p=7 ))") == 0
        shell.clear_output()
        _unchanged(shell, "$q", "7")

    def test_division_by_zero_still_status_1(self, captured_shell):
        shell = captured_shell
        rc = shell.run_command("(( 1/0 ))")
        assert rc == 1
        assert "ivision by zero" in shell.get_stderr()
