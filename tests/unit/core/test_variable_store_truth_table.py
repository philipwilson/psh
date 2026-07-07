"""VariableStore campaign — declaration/mutation truth-table battery.

This file is the safety net for the VariableStore + declaration-service
campaign (core-state appraisal Phase 2 / builtins appraisal finding 3). It has
two halves:

1. THE FOUR INTENDED FIXES (``TestFixN...``), each marked
   ``@pytest.mark.xfail(strict=True)`` at commit 1. They assert the CORRECT
   (bash 5.2) behavior, so they xfail until the declaration engine lands, then
   XPASS — strict mode turns that XPASS into a failure, forcing the marker's
   removal in the fixing commit (the "xfail flip").

2. BEHAVIOR LOCKS (``TestLock...``) pinning the large surface that must NOT
   move: the ``declare -p`` attribute matrix, ``export``/``readonly``/``set``
   listings, the ``local`` battery, the nameref suite, and the append battery.
   These are re-diffed after every commit — only the four fixes may change.

Every expected value was verified against ``/opt/homebrew/bin/bash 5.2.26``
(``--noprofile --norc``) on 2026-07-07. Two accepted psh divergences are noted
inline: the ``psh:`` diagnostic prefix, and associative-array iteration order
(bash uses internal hash order; psh uses insertion order — psh's documented,
deterministic behavior).
"""

import pytest

# ==========================================================================
# FIX 1 — integer append through export uses canonical append semantics.
# `declare -i n=2; export n+=3` is 5 in bash (arithmetic 2+3), not 23
# (textual "2"+"3"). ExportBuiltin concatenates textually before applying the
# integer attribute; the declaration engine must append through the store.
# ==========================================================================

class TestFix1IntegerAppendThroughExport:
    @pytest.mark.xfail(strict=True, reason="FIX1: export n+= must use integer-append (store)")
    def test_export_integer_append_value(self, captured_shell):
        rc = captured_shell.run_command('declare -i n=2; export n+=3; echo "$n"')
        assert rc == 0
        assert captured_shell.get_stdout() == "5\n"

    @pytest.mark.xfail(strict=True, reason="FIX1: export n+= integer declare -p")
    def test_export_integer_append_declare_p(self, captured_shell):
        rc = captured_shell.run_command('declare -i n=2; export n+=3; declare -p n')
        assert rc == 0
        assert captured_shell.get_stdout() == 'declare -ix n="5"\n'

    # Collateral that must stay correct (no integer attribute -> textual concat).
    def test_export_append_no_integer_is_textual(self, captured_shell):
        rc = captured_shell.run_command('n=2; export n+=3; echo "$n"')
        assert rc == 0
        assert captured_shell.get_stdout() == "23\n"

    def test_export_append_unset_base(self, captured_shell):
        rc = captured_shell.run_command('export n+=3; echo "$n"')
        assert rc == 0
        assert captured_shell.get_stdout() == "3\n"


# ==========================================================================
# FIX 2 — an incompatible array conversion FAILS (rc=1) and PRESERVES the
# existing array. `a=(x y); declare -A a` in bash prints the error, returns 1,
# and leaves `a` an indexed array. psh converts and returns 0. bash applies
# this even to an EMPTY indexed array (no exception). The reverse direction
# (assoc -> -a) is ALREADY correct in psh (rc=1, preserved).
# ==========================================================================

class TestFix2IncompatibleArrayConversion:
    @pytest.mark.xfail(strict=True, reason="FIX2: declare -A on indexed array must fail rc=1")
    def test_indexed_to_assoc_returns_1(self, captured_shell):
        rc = captured_shell.run_command('a=(x y); declare -A a')
        assert rc == 1

    @pytest.mark.xfail(strict=True, reason="FIX2: declare -A on indexed must preserve indexed")
    def test_indexed_to_assoc_preserves_indexed(self, captured_shell):
        captured_shell.run_command('a=(x y); declare -A a 2>/dev/null; declare -p a')
        assert captured_shell.get_stdout() == 'declare -a a=([0]="x" [1]="y")\n'

    @pytest.mark.xfail(strict=True, reason="FIX2: empty indexed array also blocks -A")
    def test_empty_indexed_to_assoc_returns_1(self, captured_shell):
        rc = captured_shell.run_command('declare -a e; declare -A e')
        assert rc == 1

    # The error message is still printed (bash prints it even in the rc=1 case).
    @pytest.mark.xfail(strict=True, reason="FIX2: conversion error message + rc=1")
    def test_indexed_to_assoc_prints_error(self, captured_shell):
        rc = captured_shell.run_command('a=(x y); declare -A a')
        assert rc == 1
        assert "cannot convert indexed to associative array" in captured_shell.get_stderr()

    # Reverse direction already correct — LOCK it (must not regress).
    def test_assoc_to_indexed_already_fails(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=v); declare -a m 2>/dev/null; echo "rc=$?"')
        assert captured_shell.get_stdout() == "rc=1\n"

    def test_assoc_to_indexed_preserves_assoc(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=v); declare -a m 2>/dev/null; declare -p m')
        assert captured_shell.get_stdout() == 'declare -A m=([k]="v" )\n'


# ==========================================================================
# FIX 3 — `declare -g` targets the global scope for EVERY operation, including
# the append base. `x=G; f(){ local x=L; declare -g x+=A; }; f` yields global
# GA in bash; psh reads the append base through the local shadow -> LA. Plain
# `-g x=NEW` already targets global correctly; only the += base is wrong.
# ==========================================================================

class TestFix3DeclareGThroughLocalShadow:
    @pytest.mark.xfail(strict=True, reason="FIX3: declare -g x+= reads global base")
    def test_g_string_append_reads_global(self, captured_shell):
        rc = captured_shell.run_command(
            'x=G; f(){ local x=L; declare -g x+=A; }; f; echo "$x"')
        assert rc == 0
        assert captured_shell.get_stdout() == "GA\n"

    @pytest.mark.xfail(strict=True, reason="FIX3: local instance unchanged by declare -g")
    def test_g_append_leaves_local_untouched(self, captured_shell):
        rc = captured_shell.run_command(
            'x=G; f(){ local x=L; declare -g x+=A; echo "in=$x"; }; f; echo "out=$x"')
        assert rc == 0
        assert captured_shell.get_stdout() == "in=L\nout=GA\n"

    @pytest.mark.xfail(strict=True, reason="FIX3: integer -g append reads global base")
    def test_g_integer_append_reads_global(self, captured_shell):
        # Non-coincidental values: string-concat "1"+"5"="15" != arithmetic
        # 100+5=105, so this genuinely distinguishes reading the global base.
        rc = captured_shell.run_command(
            'declare -i n=100; f(){ local n=1; declare -g n+=5; }; f; echo "$n"')
        assert rc == 0
        assert captured_shell.get_stdout() == "105\n"

    @pytest.mark.xfail(strict=True, reason="FIX3: nested-depth -g append reads global base")
    def test_g_append_nested_depth(self, captured_shell):
        rc = captured_shell.run_command(
            'x=G; g(){ declare -g x+=B; }; f(){ local x=L; g; }; f; echo "$x"')
        assert rc == 0
        assert captured_shell.get_stdout() == "GB\n"

    # Plain -g assignment already correct — LOCK it.
    def test_g_plain_assignment_targets_global(self, captured_shell):
        rc = captured_shell.run_command(
            'x=G; f(){ local x=L; declare -g x=NEW; }; f; echo "$x"')
        assert rc == 0
        assert captured_shell.get_stdout() == "NEW\n"


# ==========================================================================
# FIX 4 — `declare -pn` lists namerefs ONLY. psh omits nameref from the
# declaration filter and prints every variable. Same for `declare -p -n` and
# the `declare -n` listing form.
# ==========================================================================

class TestFix4DeclarePnNamerefsOnly:
    @staticmethod
    def _nonempty_lines(text):
        return [ln for ln in text.splitlines() if ln.strip()]

    @pytest.mark.xfail(strict=True, reason="FIX4: declare -pn lists namerefs only")
    def test_declare_pn_lists_only_namerefs(self, captured_shell):
        rc = captured_shell.run_command('a=1; declare -n r=a; declare -pn')
        assert rc == 0
        lines = self._nonempty_lines(captured_shell.get_stdout())
        assert lines, "declare -pn produced no output"
        assert all(ln.startswith("declare -n ") for ln in lines), lines
        assert 'declare -n r="a"' in lines

    @pytest.mark.xfail(strict=True, reason="FIX4: declare -p -n split-flag form")
    def test_declare_p_n_split_form(self, captured_shell):
        rc = captured_shell.run_command('a=1; declare -n r=a; declare -p -n')
        assert rc == 0
        lines = self._nonempty_lines(captured_shell.get_stdout())
        assert all(ln.startswith("declare -n ") for ln in lines), lines
        assert 'declare -n r="a"' in lines

    @pytest.mark.xfail(strict=True, reason="FIX4: declare -n listing form")
    def test_declare_n_listing_form(self, captured_shell):
        rc = captured_shell.run_command('a=1; declare -n r=a; declare -n')
        assert rc == 0
        lines = self._nonempty_lines(captured_shell.get_stdout())
        # bash lists the same reusable `declare -n r="a"` form here.
        assert 'declare -n r="a"' in lines
        assert all(ln.startswith("declare -n ") for ln in lines), lines


# ==========================================================================
# LOCKS — must-not-change behavior. Re-diffed after every commit.
# ==========================================================================

class TestLockDeclarePAttributeMatrix:
    """`declare -p` across the scalar/array attribute matrix (== bash 5.2)."""

    @pytest.mark.parametrize("cmd,expected", [
        ('x=hi; declare -p x', 'declare -- x="hi"\n'),
        ('declare -r x=hi; declare -p x', 'declare -r x="hi"\n'),
        ('declare -x x=hi; declare -p x', 'declare -x x="hi"\n'),
        ('declare -i x=5; declare -p x', 'declare -i x="5"\n'),
        ('declare -l x=HI; declare -p x', 'declare -l x="hi"\n'),
        ('declare -u x=hi; declare -p x', 'declare -u x="HI"\n'),
        ('declare -rx x=hi; declare -p x', 'declare -rx x="hi"\n'),
        ('declare -ix x=5; declare -p x', 'declare -ix x="5"\n'),
        ('a=1; declare -n r=a; declare -p r', 'declare -n r="a"\n'),
        ('a=(x y z); declare -p a', 'declare -a a=([0]="x" [1]="y" [2]="z")\n'),
        ('declare -A m=([k1]=v1 [k2]=v2); declare -p m',
         'declare -A m=([k1]="v1" [k2]="v2" )\n'),
        ('declare -ar a=(x y); declare -p a', 'declare -ar a=([0]="x" [1]="y")\n'),
        ('declare -Ax m=([k]=v); declare -p m', 'declare -Ax m=([k]="v" )\n'),
        ('declare -ai a=(1 2 3); declare -p a', 'declare -ai a=([0]="1" [1]="2" [2]="3")\n'),
        ('a=([2]=b [5]=e); declare -p a', 'declare -a a=([2]="b" [5]="e")\n'),
    ])
    def test_declare_p(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected


class TestLockListings:
    # These pipe a listing through external `grep`; the piped output bypasses
    # the in-process StringIO capture, so run psh in a subprocess (which
    # inherits the worktree cwd, hence the worktree's psh).
    @staticmethod
    def _psh(script):
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, '-m', 'psh', '--norc', '-c', script],
            capture_output=True, text=True)

    def test_export_p_single(self):
        r = self._psh('export ZZ=1; export -p | grep "declare -x ZZ"')
        assert r.returncode == 0
        assert r.stdout == 'declare -x ZZ="1"\n'

    def test_readonly_p_single(self):
        r = self._psh('readonly ZZ=1; readonly -p | grep "declare -r ZZ"')
        assert r.returncode == 0
        assert r.stdout == 'declare -r ZZ="1"\n'

    def test_set_listing_single(self):
        r = self._psh('ZZ=hello; set | grep "^ZZ="')
        assert r.returncode == 0
        assert r.stdout == "ZZ=hello\n"


class TestLockLocalBattery:
    @pytest.mark.parametrize("cmd,expected", [
        ('x=g; f(){ local x=l; echo $x; }; f; echo $x', "l\ng\n"),
        ('f(){ local v; echo ${v-U}; }; f', "U\n"),
        ('a=1; f(){ local -n r=a; echo $r; r=2; }; f; echo $a', "1\n2\n"),
        ('f(){ local -a arr=(a b c); echo ${arr[1]}; }; f', "b\n"),
        ('f(){ local -i n=2+3; echo $n; }; f', "5\n"),
        ('x=1; f(){ echo $x; }; x=2 f; echo $x', "2\n1\n"),
    ])
    def test_local(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected

    def test_local_export_env_visible(self):
        # printenv is external; run in a subprocess (inherits the worktree cwd).
        import subprocess
        import sys
        r = subprocess.run(
            [sys.executable, '-m', 'psh', '--norc', '-c',
             'f(){ local -x LX=hi; printenv LX; }; f'],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout == "hi\n"


class TestLockNamerefSuite:
    @pytest.mark.parametrize("cmd,expected", [
        ('a=1; declare -n r=a; declare -n s=r; echo $s', "1\n"),
        ('a=1; declare -n r=a; r=99; echo $a', "99\n"),
        ('arr=(x y); declare -n r=arr; echo ${r[1]}', "y\n"),
    ])
    def test_nameref(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected

    def test_nameref_circular_warns_and_empty(self, captured_shell):
        # psh uses the "psh:" diagnostic prefix (accepted divergence from bash's
        # program-name prefix); the behavior (warn + empty expansion) matches.
        rc = captured_shell.run_command('declare -n a=b; declare -n b=a; echo ${a-empty}')
        assert rc == 0
        assert captured_shell.get_stdout() == "empty\n"
        assert "circular name reference" in captured_shell.get_stderr()


class TestLockAppendBattery:
    @pytest.mark.parametrize("cmd,expected", [
        ('x=ab; x+=cd; echo $x', "abcd\n"),
        ('declare -i n=5; n+=3; echo $n', "8\n"),
        ('a=(x y); a+=(z w); declare -p a', 'declare -a a=([0]="x" [1]="y" [2]="z" [3]="w")\n'),
        ('a=(x y); a[0]+=Z; declare -p a', 'declare -a a=([0]="xZ" [1]="y")\n'),
        ('x=a; x+=b echo hi; echo $x', "hi\na\n"),
        ('declare -ai a=(1 2); a[0]+=10; declare -p a', 'declare -ai a=([0]="11" [1]="2")\n'),
    ])
    def test_append(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected

    def test_assoc_append_order(self, captured_shell):
        # Associative-array iteration order is bash-hash-order (unspecified) vs
        # psh's own order — a fundamental accepted divergence. This LOCK pins
        # psh's CURRENT order (new-element-first for this 2-key case) so the
        # refactor cannot silently change it; if it does, evaluate whether the
        # new order is an improvement before updating.
        rc = captured_shell.run_command(
            'declare -A m=([k]=v); m+=([j]=w); declare -p m')
        assert rc == 0
        assert captured_shell.get_stdout() == 'declare -A m=([j]="w" [k]="v" )\n'
