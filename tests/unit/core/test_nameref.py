"""Tests for name references (declare -n / local -n) — Phase 1 (scalar targets)."""

import subprocess
import sys

import pytest


def _run(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True)


class TestNamerefRead:
    def test_read_through(self, captured_shell):
        captured_shell.run_command('declare -n r=x; x=5; echo "$r"')
        assert captured_shell.get_stdout().strip() == "5"

    def test_read_through_via_state(self, shell):
        shell.run_command('TARGET=original; declare -n REF=TARGET')
        assert shell.state.get_variable('REF') == 'original'

    def test_chain(self, captured_shell):
        captured_shell.run_command('declare -n a=b b=c; c=deep; echo "$a"')
        assert captured_shell.get_stdout().strip() == "deep"

    def test_param_ops_through_nameref(self, captured_shell):
        captured_shell.run_command('declare -n r=x; x=hello; echo "${r^^} ${#r} ${r:0:2}"')
        assert captured_shell.get_stdout().strip() == "HELLO 5 he"


class TestNamerefWrite:
    def test_write_through(self, captured_shell):
        captured_shell.run_command('declare -n r=x; r=9; echo "$x"')
        assert captured_shell.get_stdout().strip() == "9"

    def test_write_creates_target(self, captured_shell):
        captured_shell.run_command('declare -n r=missing; r=created; echo "$missing"')
        assert captured_shell.get_stdout().strip() == "created"

    def test_chain_write(self, captured_shell):
        captured_shell.run_command('declare -n a=b b=c; a=W; echo "$c"')
        assert captured_shell.get_stdout().strip() == "W"

    def test_deferred_target(self, captured_shell):
        # declare -n with no target, then assigning sets the target name.
        captured_shell.run_command('declare -n r; r=x; x=val; echo "$r"')
        assert captured_shell.get_stdout().strip() == "val"


class TestNamerefLocal:
    def test_pass_by_reference(self, captured_shell):
        captured_shell.run_command(
            'f(){ local -n ref=$1; ref=set_by_func; }; v=orig; f v; echo "$v"')
        assert captured_shell.get_stdout().strip() == "set_by_func"

    def test_increment_helper(self, captured_shell):
        captured_shell.run_command(
            'inc(){ local -n n=$1; n=$((n+1)); }; c=5; inc c; inc c; echo "$c"')
        assert captured_shell.get_stdout().strip() == "7"


class TestNamerefUnset:
    def test_unset_removes_target(self, captured_shell):
        captured_shell.run_command('x=1; declare -n r=x; unset r; echo "[${x-gone}]"')
        assert captured_shell.get_stdout().strip() == "[gone]"

    def test_unset_n_removes_nameref(self, captured_shell):
        captured_shell.run_command(
            'x=1; declare -n r=x; unset -n r; echo "x=$x ref=[${r-gone}]"')
        assert captured_shell.get_stdout().strip() == "x=1 ref=[gone]"


class TestNamerefIntrospection:
    def test_declare_p(self, captured_shell):
        captured_shell.run_command('declare -n r=x; declare -p r')
        assert captured_shell.get_stdout().strip() == 'declare -n r="x"'

    def test_bang_ref_gives_target_name(self, captured_shell):
        captured_shell.run_command('declare -n r=x; x=5; echo "${!r}"')
        assert captured_shell.get_stdout().strip() == "x"

    def test_self_reference_rejected(self, captured_shell):
        rc = captured_shell.run_command('declare -n r=r')
        assert rc == 1
        assert "self references not allowed" in captured_shell.get_stderr()


class TestIndirectExpansion:
    """${!var} for a non-nameref is classic indirect expansion."""

    def test_indirect_value(self, captured_shell):
        captured_shell.run_command('x=y; y=hit; echo "${!x}"')
        assert captured_shell.get_stdout().strip() == "hit"

    def test_indirect_unset_is_empty(self, captured_shell):
        captured_shell.run_command('p=nope; echo "[${!p}]"')
        assert captured_shell.get_stdout().strip() == "[]"


class TestNamerefArrayElementTargets:
    """Phase 2: a nameref whose target is an array element (declare -n e=arr[1])."""

    def test_read_indexed_element(self, captured_shell):
        captured_shell.run_command('arr=(p q r); declare -n e=arr[1]; echo "$e"')
        assert captured_shell.get_stdout().strip() == "q"

    def test_read_braced(self, captured_shell):
        captured_shell.run_command('arr=(p q r); declare -n e=arr[2]; echo "${e}"')
        assert captured_shell.get_stdout().strip() == "r"

    def test_write_indexed_element(self, captured_shell):
        captured_shell.run_command('arr=(p q r); declare -n e=arr[1]; e=Q; echo "${arr[@]}"')
        assert captured_shell.get_stdout().strip() == "p Q r"

    def test_read_assoc_element(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=v); declare -n e=m[k]; echo "$e"')
        assert captured_shell.get_stdout().strip() == "v"

    def test_write_assoc_element(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=old); declare -n e=m[k]; e=new; echo "${m[k]}"')
        assert captured_shell.get_stdout().strip() == "new"

    def test_operator_through_element(self, captured_shell):
        captured_shell.run_command('arr=(hi yo); declare -n e=arr[0]; echo "${e^^}"')
        assert captured_shell.get_stdout().strip() == "HI"

    def test_bang_ref_gives_subscripted_name(self, captured_shell):
        captured_shell.run_command('arr=(p q); declare -n e=arr[1]; echo "${!e}"')
        assert captured_shell.get_stdout().strip() == "arr[1]"

    def test_local_n_to_element(self, captured_shell):
        captured_shell.run_command(
            'f(){ local -n el=$1; el=Z; }; a=(x y); f "a[0]"; echo "${a[0]}"')
        assert captured_shell.get_stdout().strip() == "Z"


class TestNamerefBashParity:
    @pytest.mark.parametrize("script", [
        'declare -n r=x; x=5; echo "$r"',
        'declare -n r=x; r=9; echo "$x"',
        'declare -n r=missing; r=v; echo "$missing"',
        'declare -n a=b b=c; c=deep; echo "$a"',
        'declare -n r=x; x=hi; echo "${!r}"',
        'x=y; y=hit; echo "${!x}"',
        'x=1; declare -n r=x; unset r; echo "[${x-gone}]"',
        'declare -n r=x; declare -p r',
        'f(){ local -n n=$1; n=42; }; v=0; f v; echo "$v"',
        'arr=(p q r); declare -n e=arr[1]; echo "$e"',
        'arr=(p q r); declare -n e=arr[1]; e=Q; echo "${arr[@]}"',
        'declare -A m=([k]=v); declare -n e=m[k]; echo "$e"',
        # reappraisal #14 H5: `+=` through a nameref must append to the
        # TARGET's value/attributes, not the nameref's own value (the target
        # name). Previously `n=5; declare -n r=n; r+=3` gave "n3".
        'n=5; declare -n r=n; r+=3; echo "$n"',
        'declare -i n=5; declare -n r=n; r+=3; echo "$n"',
        'declare -u u=x; declare -n r=u; r+=world; echo "$u"',
        'arr=(a b); declare -n r=arr; r+=x; echo "${arr[@]}"',
        'n=1; declare -n s=n; declare -n r=s; r+=9; echo "$n"',
        'g=5; f(){ declare -n r=g; r+=3; }; f; echo "$g"',
        'declare -A m=([0]=ab); declare -n r=m; r+=cd; echo "${m[0]}"',
    ])
    def test_matches_bash(self, script):
        psh = _run(script)
        bash = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode
