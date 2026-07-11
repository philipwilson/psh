"""Characterization of the ONE `+=` append engine (appraisal H8).

Before v0.699 the append COMPUTATION lived twice — `VariableStore.append`
(commit path) and `assignment_utils.resolve_append_assignment` (pure path used
by prefix/local/rollback callers) each spelled out the same nameref-resolve,
integer-arithmetic, array-element-0, and case-fold formula, and had already
cosmetically drifted (`container.copy()` vs `copy.deepcopy`). These tests pin
the observable append matrix across ALL caller families so the convergence onto
one shared computation helper is proven behavior-preserving.

Every value here was verified against bash 5.2 EXCEPT the two cases explicitly
marked KNOWN-DIVERGENCE (pre-existing integer-append bugs declared as riders):
- a temp-env prefix integer append leaves the arithmetic EXPRESSION unevaluated,
- `n=2; declare -i n+=3` appends textually because the base is read before -i.
Those are pinned to psh's CURRENT output so the refactor is provably identical;
they are NOT bash-conformance claims.
"""

import subprocess
import sys

from psh.core.variables import IndexedArray, VarAttributes


def _run(shell, cmd):
    shell.clear_output()
    rc = shell.run_command(cmd)
    return rc, shell.get_stdout()


def _psh(cmd):
    """Run a command in a fresh psh subprocess (robust for external commands
    like printenv and for temp-env prefix + eval fd interactions)."""
    r = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       capture_output=True, text=True)
    return r.stdout, r.returncode


class TestScalarAppendMatrix:
    """The scalar/integer/case-fold families (bash-verified)."""

    def test_scalar_textual(self, captured_shell):
        assert _run(captured_shell, 'x=a; x+=b; echo "$x"') == (0, "ab\n")

    def test_integer_arithmetic(self, captured_shell):
        assert _run(captured_shell, 'declare -i n=5; n+=3; echo "$n"') == (0, "8\n")

    def test_integer_empty_value_noop(self, captured_shell):
        assert _run(captured_shell, 'declare -i n=5; n+=; echo "$n"') == (0, "5\n")

    def test_append_unset_base(self, captured_shell):
        assert _run(captured_shell, 'x+=cd; echo "$x"') == (0, "cd\n")

    def test_uppercase_casefold(self, captured_shell):
        assert _run(captured_shell, 'declare -u s=AB; s+=cd; echo "$s"') == (0, "ABCD\n")

    def test_lowercase_casefold(self, captured_shell):
        assert _run(captured_shell, 'declare -l s=AB; s+=CD; echo "$s"') == (0, "abcd\n")


class TestArrayAppendMatrix:
    """Scalar `+=` onto an array updates element 0 in place (bash)."""

    def test_array_element0_textual(self, captured_shell):
        assert _run(captured_shell, 'a=(1 2); a+=x; echo "${a[0]}|${a[1]}"') == (0, "1x|2\n")

    def test_integer_array_element0_arith(self, captured_shell):
        assert _run(captured_shell, 'declare -ai a=(1 2 3); a+=10; echo "${a[0]}"') == (0, "11\n")

    def test_assoc_array_element0(self, captured_shell):
        assert _run(captured_shell, 'declare -A m=([k]=v); m+=z; echo "${m[0]}"') == (0, "z\n")


class TestNamerefAppend:
    """A nameref target appends THROUGH to the final variable (bash)."""

    def test_nameref_textual(self, captured_shell):
        assert _run(captured_shell, 'n=5; declare -n r=n; r+=3; echo "$n"') == (0, "53\n")

    def test_nameref_integer(self, captured_shell):
        assert _run(captured_shell,
                    'declare -i n=5; declare -n r=n; r+=3; echo "$n"') == (0, "8\n")


class TestScopedAppend:
    """Target-scope-aware append base: local vs -g global."""

    def test_local_append(self, captured_shell):
        assert _run(captured_shell,
                    'f(){ local x=a; local x+=b; echo "$x"; }; f') == (0, "ab\n")

    def test_global_g_append_reads_global_base(self, captured_shell):
        assert _run(captured_shell,
                    'x=G; f(){ local x=L; declare -g x+=A; echo "in=$x"; }; f; echo "out=$x"'
                    ) == (0, "in=L\nout=GA\n")

    def test_export_integer_append(self, captured_shell):
        assert _run(captured_shell,
                    'declare -i n=2; export n+=3; echo "$n"') == (0, "5\n")


class TestTempEnvPrefixAppend:
    """`VAR+=x cmd` prefix append (v0.679 temp-env semantics), via subprocess
    (printenv is external; temp-env + eval fd interactions are unreliable
    under in-process output capture)."""

    def test_tempenv_textual_prefix(self):
        # The prefix binds for the command's environment only; the real
        # variable is unchanged afterwards (bash-verified).
        assert _psh('x=a; x+=b printenv x; echo "after=$x"') == ("ab\nafter=a\n", 0)


class TestKnownIntegerAppendDivergences:
    """Two PRE-EXISTING integer-append bugs pinned to psh's CURRENT (buggy)
    output so the H8 pure refactor (commit A) is provably byte-identical. These
    are NOT bash-conformance claims — bash gives 8 and 5 respectively. The
    eager-integer-append rider (commit B) FLIPS both with bash-probe evidence.
    """

    def test_tempenv_integer_prefix_current(self):
        # bash: 8. psh currently leaves the arithmetic expression unevaluated
        # because the temp-env commit does not apply the INTEGER transform.
        assert _psh("declare -ix n=5; n+=3 printenv n") == ("(5)+(3)\n", 0)

    def test_declare_adds_integer_and_appends_current(self):
        # bash: 5 (integer 2+3). psh currently appends textually because the
        # base is read before the -i being added in the same declare is applied.
        assert _psh('n=2; declare -i n+=3; echo "$n"') == ("23\n", 0)


class TestAppendComputationIsPure:
    """The append computation returns a COPY with element 0 updated and never
    mutates the live base container — the deliberate copy() choice (H8). This is
    the case that WOULD distinguish copy() from deepcopy if array elements were
    themselves mutable; with str elements they are identical, so we pin the
    non-mutation property directly at the store level."""

    def test_compute_append_does_not_mutate_base_array(self, captured_shell):
        sm = captured_shell.state.scope_manager
        arr = IndexedArray()
        arr.set(0, "1")
        arr.set(1, "2")
        sm.set_variable("a", arr, attributes=VarAttributes.ARRAY)
        base = sm.get_variable_object("a")
        result = sm.store.compute_append_value(base, "x")
        # The live container is untouched; the result is an independent copy.
        assert isinstance(result, IndexedArray)
        assert result.get(0) == "1x"
        assert base.value.get(0) == "1"        # original element 0 unchanged
        assert result is not base.value

    def test_compute_append_scalar_integer_returns_expression(self, captured_shell):
        """Deliberately pinned: the INTEGER scalar append returns the arithmetic
        EXPRESSION for the commit's INTEGER transform to evaluate (the shared
        formula's documented contract)."""
        sm = captured_shell.state.scope_manager
        sm.set_variable("n", "5", attributes=VarAttributes.INTEGER)
        base = sm.get_variable_object("n")
        assert sm.store.compute_append_value(base, "3") == "(5)+(3)"
