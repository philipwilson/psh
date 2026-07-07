"""Core-state Phase 1: array mutation invariants (C2 + builtins P1.2).

THE invariant: a FAILED operation must not mutate a readonly array, and
negative-subscript resolution must be identical on read, write, and unset.

The 2026-07-06 core-state and builtins appraisals reproduced several routes
that mutate a readonly array before (or without) the readonly check:
  - ``unset 'a[0]'`` removes a readonly element (no check at all);
  - ``declare a+=(y)`` / ``local a+=(y)`` build into the LIVE array, then
    ``set_variable`` rejects — but the mutation already happened;
  - ``mapfile -O`` overlays the live array before the rejection.
And ``unset`` used a different negative-index formula than read/write, so a
sparse ``unset 'a[-2]'`` removed the wrong slot.

Invariants are asserted on the shell's own array objects (bash aborts the
whole ``-c`` on an assignment error while psh continues, so the full line is
not directly bash-comparable — the mutation state is). Fixed in Commit 4:
readonly checked before element unset; the append/overlay routes build into a
COPY committed atomically; unset shares read/write negative-index resolution.
"""

from psh.core.variables import IndexedArray


def _array(shell, name):
    var = shell.state.scope_manager.get_variable_object(name)
    return var.value if var is not None else None


# --------------------------------------------------------------------------
# Readonly enforcement on every array mutation route.
# --------------------------------------------------------------------------

def test_readonly_element_unset_refused(captured_shell):
    rc = captured_shell.run_command("a=(x y); readonly a; unset 'a[0]'")
    assert rc == 1
    assert _array(captured_shell, "a").all_elements() == ["x", "y"]


def test_readonly_declare_append_no_mutation(captured_shell):
    rc = captured_shell.run_command("readonly -a a=(x); declare a+=(y)")
    assert rc == 1
    assert _array(captured_shell, "a").all_elements() == ["x"]


def test_readonly_mapfile_origin_no_mutation(captured_shell):
    rc = captured_shell.run_command("readonly -a a=(old); mapfile -t -O 1 a <<< new")
    assert rc == 1
    assert _array(captured_shell, "a").all_elements() == ["old"]


def test_readonly_local_append_no_mutation(captured_shell):
    rc = captured_shell.run_command(
        "readonly -a a=(x); f() { local a+=(y); }; f")
    assert rc == 1
    assert _array(captured_shell, "a").all_elements() == ["x"]


# --------------------------------------------------------------------------
# Sparse negative-subscript unset must match read/write (highest+1+n).
# --------------------------------------------------------------------------

def test_sparse_negative_unset_matches_bash():
    # a[5],a[10]; unset a[-2] -> slot 9 (unset) -> no-op like bash.
    from psh.shell import Shell
    sh = Shell(norc=True)
    try:
        sh.run_command("a=([5]=F [10]=T); unset 'a[-2]'")
        arr = _array(sh, "a")
        assert isinstance(arr, IndexedArray)
        assert arr.indices() == [5, 10], "unset a[-2] must be a no-op (slot 9)"
    finally:
        sh.close()


# --------------------------------------------------------------------------
# Regression guards for the routes that ALREADY enforce readonly correctly
# (executor element/compound/arith paths) — must stay correct after Commit 4.
# --------------------------------------------------------------------------

class TestReadonlyRoutesAlreadyCorrect:
    def test_element_assign_refused(self, captured_shell):
        rc = captured_shell.run_command("a=(x y); readonly a; a[0]=z")
        assert rc == 1
        assert _array(captured_shell, "a").all_elements() == ["x", "y"]

    def test_compound_append_refused(self, captured_shell):
        rc = captured_shell.run_command("a=(x y); readonly a; a+=(w)")
        assert rc == 1
        assert _array(captured_shell, "a").all_elements() == ["x", "y"]

    def test_arith_incr_refused(self, captured_shell):
        rc = captured_shell.run_command("a=(1 2); readonly a; (( a[0]++ ))")
        assert rc == 1
        assert _array(captured_shell, "a").all_elements() == ["1", "2"]

    def test_whole_array_unset_refused(self, captured_shell):
        rc = captured_shell.run_command("a=(x y); readonly a; unset a")
        assert rc == 1
        assert _array(captured_shell, "a").all_elements() == ["x", "y"]

    def test_sparse_negative_last_removes(self):
        # unset a[-1] on [5,10] -> slot 10 removed (matches bash); already OK.
        from psh.shell import Shell
        sh = Shell(norc=True)
        try:
            sh.run_command("a=([5]=F [10]=T); unset 'a[-1]'")
            assert _array(sh, "a").indices() == [5]
        finally:
            sh.close()

    def test_negative_unset_out_of_range_errors(self, captured_shell):
        rc = captured_shell.run_command("a=([5]=F [10]=T); unset 'a[-12]'")
        assert rc == 1
        assert _array(captured_shell, "a").indices() == [5, 10]
