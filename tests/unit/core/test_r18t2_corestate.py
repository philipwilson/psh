"""R18 Tier-2 cluster T2-B: core state fixes, verified against bash 5.2.

Covers:
  M-c4  temp-env prefix + a function body's declare -g/export survives return
  M-c5  UID/EUID/PPID are readonly integer variables
  M-c6  BASHPID/HOSTNAME/OSTYPE/MACHTYPE/HOSTTYPE/SRANDOM special variables
  T1-3  local re-declaration attribute merge; array-element case-fold on
        append; nameref temp-env export leak; integer-array element-0 +=
"""

import os
import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


# ---------------------------------------------------------------------------
# M-c4: temp-env prefix over a function call is bash's temporary-variable
# context — a body's declare -g/export reaches the global and SURVIVES the
# return, while a plain body assignment updates the (discarded) temp layer.
# ---------------------------------------------------------------------------
class TestTempEnvFunctionScope:
    def test_declare_g_survives_return(self):
        r = run_psh('X=outer; f() { declare -g X=2; }; X=1 f; echo "$X"')
        assert r.stdout == '2\n'

    def test_declare_g_survives_when_no_prior_global(self):
        r = run_psh('f() { declare -g X=2; }; X=1 f; echo "$X"')
        assert r.stdout == '2\n'

    def test_declare_g_attributes_not_polluted_by_temp_export(self):
        # The temp X is exported for the call, but the body's declare -g writes
        # the real global, which keeps its own (non-exported) attributes.
        r = run_psh('X=outer; f() { declare -g X=2; }; X=1 f; declare -p X')
        assert r.stdout == 'declare -- X="2"\n'

    def test_export_survives_return(self):
        r = run_psh('X=outer; f() { export X=2; }; X=1 f; declare -p X')
        assert r.stdout == 'declare -x X="2"\n'

    def test_pre_exported_global_stays_exported(self):
        r = run_psh('export X=outer; f() { declare -g X=2; }; X=1 f; declare -p X')
        assert r.stdout == 'declare -x X="2"\n'

    def test_local_shadow_then_declare_g(self):
        r = run_psh('X=outer; f() { local X=l; declare -g X=2; echo "in=$X"; };'
                    ' X=1 f; echo "after=$X"')
        assert r.stdout == 'in=l\nafter=2\n'

    def test_plain_body_write_is_discarded(self):
        r = run_psh('X=outer; f() { X=2; }; X=1 f; echo "$X"')
        assert r.stdout == 'outer\n'

    def test_declare_g_then_plain_keeps_global(self):
        r = run_psh('X=outer; f() { declare -g X=2; X=3; }; X=1 f; echo "$X"')
        assert r.stdout == '2\n'

    def test_temp_env_visible_in_body_and_gone_after(self):
        r = run_psh('X=outer; f() { echo "in=$X"; }; X=1 f; echo "after=$X"')
        assert r.stdout == 'in=1\nafter=outer\n'

    def test_temp_env_attribute_not_inherited(self):
        # declare -i X=5; X=abc f  -> the temp X is a plain exported "abc",
        # NOT integer-evaluated to 0 (bash initializes the temp var fresh).
        r = run_psh('declare -i X=5; f() { declare -p X; }; X=abc f')
        assert r.stdout == 'declare -x X="abc"\n'

    def test_left_to_right_temp_env_values(self):
        r = run_psh('f() { echo "$A $B"; }; A=1 B=$A f')
        assert r.stdout == '1 1\n'


# ---------------------------------------------------------------------------
# M-c5: UID/EUID/PPID are readonly integer variables (bash: declare -ir).
# ---------------------------------------------------------------------------
class TestReadonlyIdVariables:
    def test_values(self):
        r = run_psh('echo "$UID $EUID"')
        assert r.stdout == f"{os.getuid()} {os.geteuid()}\n"

    def test_ppid_is_invoking_process(self):
        r = run_psh('echo $PPID')
        assert int(r.stdout) == os.getpid()

    def test_declare_p_shows_readonly_integer(self):
        r = run_psh('declare -p UID EUID PPID')
        for name in ('UID', 'EUID', 'PPID'):
            assert f'declare -ir {name}=' in r.stdout

    def test_assignment_is_readonly_error(self):
        r = run_psh('UID=0; echo SHOULD_NOT_PRINT')
        assert 'readonly variable' in r.stderr
        assert 'SHOULD_NOT_PRINT' not in r.stdout

    def test_unset_is_readonly_error(self):
        r = run_psh('unset UID; echo "rc=$?"')
        assert 'readonly variable' in r.stderr
        assert r.stdout == 'rc=1\n'

    def test_ppid_stable_in_subshell(self):
        r = run_psh('(echo $PPID); echo $PPID')
        a, b = r.stdout.split()
        assert a == b == str(os.getpid())


# ---------------------------------------------------------------------------
# M-c6: BASHPID / SRANDOM computed specials; HOSTNAME/OSTYPE/MACHTYPE/HOSTTYPE
# ordinary startup variables. Values differ machine-to-machine — test the
# CONTRACT, not exact values.
# ---------------------------------------------------------------------------
class TestBashpid:
    def test_matches_dollar_dollar_at_top_level(self):
        r = run_psh('[ "$BASHPID" = "$$" ] && echo same || echo diff')
        assert r.stdout == 'same\n'

    def test_differs_from_dollar_dollar_in_subshell(self):
        r = run_psh('( [ "$BASHPID" != "$$" ] && echo diff || echo same )')
        assert r.stdout == 'diff\n'

    def test_differs_from_dollar_dollar_in_cmdsub(self):
        r = run_psh('inner=$(echo $BASHPID); [ "$inner" != "$$" ] && echo diff || echo same')
        assert r.stdout == 'diff\n'

    def test_assignment_has_no_effect(self):
        r = run_psh('before=$BASHPID; BASHPID=99999; [ "$BASHPID" = "$before" ] && echo ok')
        assert r.stdout == 'ok\n'

    def test_unset_deactivates_special(self):
        r = run_psh('unset BASHPID; echo "[$BASHPID]"; BASHPID=7; echo "$BASHPID"')
        assert r.stdout == '[]\n7\n'


class TestSrandom:
    def test_two_reads_differ(self):
        r = run_psh('a=$SRANDOM; b=$SRANDOM; [ "$a" != "$b" ] && echo diff || echo same')
        assert r.stdout == 'diff\n'

    def test_not_affected_by_random_seed(self):
        r = run_psh('RANDOM=1; a=$SRANDOM; RANDOM=1; b=$SRANDOM;'
                    ' [ "$a" != "$b" ] && echo diff || echo same')
        assert r.stdout == 'diff\n'

    def test_32_bit_range(self):
        r = run_psh('for i in 1 2 3 4 5; do echo $SRANDOM; done')
        vals = [int(x) for x in r.stdout.split()]
        assert len(vals) == 5
        assert all(0 <= v <= 0xFFFFFFFF for v in vals)

    def test_assignment_has_no_effect(self):
        r = run_psh('SRANDOM=5; a=$SRANDOM; SRANDOM=5; b=$SRANDOM;'
                    ' [ "$a" != "$b" ] && echo ignored || echo seeded')
        assert r.stdout == 'ignored\n'


class TestPlatformVariables:
    def test_all_are_nonempty(self):
        r = run_psh('for v in HOSTNAME OSTYPE MACHTYPE HOSTTYPE; do'
                    ' [ -n "${!v}" ] && echo set || echo empty; done')
        assert r.stdout == 'set\nset\nset\nset\n'

    def test_reassignable(self):
        r = run_psh('OSTYPE=custom; echo "$OSTYPE"')
        assert r.stdout == 'custom\n'

    def test_unsettable(self):
        r = run_psh('unset HOSTNAME; echo "rc=$? [${HOSTNAME-gone}]"')
        assert r.stdout == 'rc=0 [gone]\n'


# ---------------------------------------------------------------------------
# T1-3 leftovers.
# ---------------------------------------------------------------------------
class TestLocalRedeclareAttributeMerge:
    def test_uppercase_attr_merged_on_append(self):
        r = run_psh('f() { local -u x=ab; local x+=cd; echo "$x"; }; f')
        assert r.stdout == 'ABCD\n'

    def test_integer_attr_merged_on_append(self):
        r = run_psh('f() { local -i n=5; local n+=3; echo "$n"; }; f')
        assert r.stdout == '8\n'

    def test_lowercase_attr_merged_on_append(self):
        r = run_psh('f() { local -l y=HELLO; local y+=WORLD; echo "$y"; }; f')
        assert r.stdout == 'helloworld\n'

    def test_valueless_redeclare_does_not_tombstone(self):
        r = run_psh('f() { local -u x=hi; local x; echo "[${x-UNSET}]"; declare -p x; }; f')
        assert r.stdout == '[HI]\ndeclare -u x="HI"\n'

    def test_append_fresh_local_ignores_outer(self):
        # A fresh `local x+=` starts from empty even when an outer scope has x.
        r = run_psh('g() { local x+=INNER; echo "$x"; }; f() { local -u x=out; g; }; f')
        assert r.stdout == 'INNER\n'


class TestArrayElementCaseFoldOnAppend:
    def test_uppercase_element_appended(self):
        r = run_psh('declare -u a; a+=(three); echo "${a[0]}"')
        assert r.stdout == 'THREE\n'

    def test_lowercase_elements(self):
        r = run_psh('declare -l b=(ONE); b+=(TWO); echo "${b[*]}"')
        assert r.stdout == 'one two\n'


class TestNamerefTempEnvExportLeak:
    def test_nameref_prefix_does_not_leave_target_exported(self):
        r = run_psh('declare -n r=a; a=orig; r=x true; declare -p a')
        assert r.stdout == 'declare -- a="orig"\n'

    def test_nameref_prefix_value_reverts(self):
        r = run_psh('a=orig; declare -n r=a; r=temp true; echo "$a"')
        assert r.stdout == 'orig\n'


class TestIntegerArrayScalarAppend:
    def test_element_zero_arithmetic_add(self):
        r = run_psh('declare -ai a=(1 2 3); a+=10; declare -p a')
        assert r.stdout == 'declare -ai a=([0]="11" [1]="2" [2]="3")\n'

    def test_element_zero_add_value(self):
        r = run_psh('declare -ai a=(5 6); a+=3; echo "${a[0]}"')
        assert r.stdout == '8\n'

    def test_non_integer_array_still_concatenates(self):
        r = run_psh('a=(1 2); a+=x; echo "${a[0]}"')
        assert r.stdout == '1x\n'
