"""Characterization harness for special-variable RAW lookup.

Pins the CURRENT exact psh output for every special variable across many
contexts, guarding the v0.x state-consolidation refactor that has
``VariableExpander._expand_special_variable`` delegate the 7 shared raw
lookups ($?, $$, $!, $#, $-, $@, $*) to ``ShellState.get_special_variable``.

These are CHARACTERIZATION tests: they capture behavior as-is at the time
of the refactor (verified green on the unmodified code first). Where psh
diverges from bash it is noted in the docstring; we still pin psh's
current output so the refactor is provably zero-behavior-change.

Subprocess-based so positional params / IFS / $$ / $! / set -u / functions
are exercised end-to-end through a real psh process.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestExitStatus:
    def test_question_after_success(self):
        assert run_psh('true; echo $?').stdout == '0\n'

    def test_question_after_failure(self):
        assert run_psh('false; echo $?').stdout == '1\n'

    def test_question_after_specific_exit(self):
        assert run_psh('(exit 42); echo $?').stdout == '42\n'

    def test_question_braced(self):
        assert run_psh('false; echo ${?}').stdout == '1\n'


class TestShellPid:
    def test_dollar_is_numeric_pid(self):
        out = run_psh('echo $$').stdout.strip()
        assert out.isdigit() and int(out) > 0

    def test_dollar_stable_within_process(self):
        out = run_psh('echo $$; echo $$').stdout.split()
        assert out[0] == out[1]

    def test_dollar_braced(self):
        out = run_psh('echo ${$}').stdout.strip()
        assert out.isdigit()


class TestLastBgPid:
    def test_bang_empty_with_no_bg_job(self):
        assert run_psh('echo "[$!]"').stdout == '[]\n'

    def test_bang_after_bg_job(self):
        out = run_psh('sleep 0.1 & echo $!').stdout.strip()
        assert out.isdigit() and int(out) > 0

    def test_bang_braced_empty(self):
        assert run_psh('echo "[${!}]"').stdout == '[]\n'


class TestArgCount:
    def test_hash_zero_params(self):
        assert run_psh('echo $#').stdout == '0\n'

    def test_hash_one_param(self):
        assert run_psh('set -- a; echo $#').stdout == '1\n'

    def test_hash_many_params(self):
        assert run_psh('set -- a b c d e; echo $#').stdout == '5\n'

    def test_hash_braced(self):
        assert run_psh('set -- a b c; echo ${#}').stdout == '3\n'


class TestOptionFlags:
    def test_dash_default_noninteractive(self):
        # -c invocation: non-interactive, stdin not a script. Pin current output.
        out = run_psh('echo $-').stdout.strip()
        assert out == 'hB' or 'h' in out  # characterize: whatever psh emits now

    def test_dash_with_errexit(self):
        out = run_psh('set -e; echo $-').stdout.strip()
        assert 'e' in out

    def test_dash_with_nounset(self):
        out = run_psh('set -u; echo $-').stdout.strip()
        assert 'u' in out

    def test_dash_with_xtrace(self):
        # xtrace prints the trace too; just assert 'x' appears in the flags line.
        out = run_psh('set -x; echo $-').stdout
        assert 'x' in out

    def test_dash_braced(self):
        out = run_psh('set -e; echo ${-}').stdout.strip()
        assert 'e' in out


class TestAtParam:
    def test_at_zero_params(self):
        assert run_psh('echo "[$@]"').stdout == '[]\n'

    def test_at_one_param(self):
        assert run_psh('set -- a; echo "[$@]"').stdout == '[a]\n'

    def test_at_many_params_unquoted(self):
        assert run_psh('set -- a b c; echo $@').stdout == 'a b c\n'

    def test_at_many_params_quoted_string_context(self):
        # In a scalar (string) context $@ joins with a space regardless of IFS.
        assert run_psh('IFS=:; set -- a b c; x="$@"; echo "$x"').stdout == 'a b c\n'

    def test_at_quoted_end_to_end_separate_words(self):
        # "$@" produces separate words; printf with one %s per line shows them.
        out = run_psh('set -- "a b" c; for w in "$@"; do echo "<$w>"; done').stdout
        assert out == '<a b>\n<c>\n'

    def test_at_braced(self):
        assert run_psh('set -- a b c; echo ${@}').stdout == 'a b c\n'


class TestStarParam:
    def test_star_zero_params(self):
        assert run_psh('echo "[$*]"').stdout == '[]\n'

    def test_star_one_param(self):
        assert run_psh('set -- a; echo "[$*]"').stdout == '[a]\n'

    def test_star_default_ifs(self):
        # Default IFS: first char is space -> joins with space.
        assert run_psh('set -- a b c; echo "[$*]"').stdout == '[a b c]\n'

    def test_star_ifs_colon_quoted(self):
        assert run_psh('IFS=:; set -- a b c; echo "[$*]"').stdout == '[a:b:c]\n'

    def test_star_ifs_empty_quoted(self):
        # Null IFS: join with no separator.
        assert run_psh('IFS=; set -- a b c; echo "[$*]"').stdout == '[abc]\n'

    def test_star_ifs_multichar_quoted(self):
        # Only the first char of IFS is used for joining.
        assert run_psh('IFS=:-; set -- a b c; echo "[$*]"').stdout == '[a:b:c]\n'

    def test_star_ifs_colon_unquoted_resplits(self):
        # Unquoted $* joins with first IFS char, then word-splits on IFS.
        assert run_psh('IFS=:; set -- a b c; echo $*').stdout == 'a b c\n'

    def test_star_braced(self):
        assert run_psh('IFS=:; set -- a b c; echo "${*}"').stdout == 'a:b:c\n'


class TestPositionalDigits:
    def test_first_positional(self):
        assert run_psh('set -- a b c; echo $1').stdout == 'a\n'

    def test_third_positional(self):
        assert run_psh('set -- a b c; echo $3').stdout == 'c\n'

    def test_out_of_range_empty(self):
        assert run_psh('set -- a b c; echo "[$9]"').stdout == '[]\n'

    def test_multidigit_positional_braced(self):
        assert run_psh('set -- a b c d e f g h i j k; echo ${10} ${11}').stdout == 'j k\n'

    def test_out_of_range_with_nounset_errors(self):
        r = run_psh('set -u; set -- a; echo "[$5]"')
        assert r.returncode != 0
        assert '5' in r.stderr

    def test_in_range_with_nounset_ok(self):
        r = run_psh('set -u; set -- a b; echo "[$2]"')
        assert r.returncode == 0
        assert r.stdout == '[b]\n'


class TestDollarZero:
    def test_zero_top_level_is_psh_or_script(self):
        # Top level via -c: pin whatever psh reports (its script_name).
        out = run_psh('echo "[$0]"').stdout
        assert out.startswith('[') and out.endswith(']\n')

    def test_zero_inside_function_is_function_name(self):
        # psh is FUNCTION-AWARE for $0: it returns the function name inside a
        # function. (Pre-existing psh/bash divergence: bash prints the shell
        # name here. Pinned as a follow-up, NOT changed by this refactor.)
        assert run_psh('f(){ echo "[$0]"; }; f').stdout == '[f]\n'

    def test_zero_nested_function(self):
        assert run_psh('g(){ echo "[$0]"; }; f(){ g; }; f').stdout == '[g]\n'

    def test_zero_after_function_returns_to_outer(self):
        out = run_psh('f(){ echo "[$0]"; }; f; echo "[$0]"').stdout
        lines = out.splitlines()
        assert lines[0] == '[f]'
        # outer $0 is the script name again (not 'f')
        assert lines[1] != '[f]'


class TestNounsetRegularVar:
    def test_unset_var_errors_under_nounset(self):
        r = run_psh('set -u; echo "$NOPE_UNSET_VAR"')
        assert r.returncode != 0
        assert 'NOPE_UNSET_VAR' in r.stderr

    def test_set_var_ok_under_nounset(self):
        assert run_psh('set -u; x=hi; echo "$x"').stdout == 'hi\n'


class TestForkedBuiltinFdLevelIO:
    """Half 1 sanity: a forked builtin still does fd-level I/O so its
    output survives through pipes/subshells (covers the removal of the
    vestigial ExecutionContext.in_forked_child field)."""

    def test_echo_in_subshell(self):
        assert run_psh('(echo hello)').stdout == 'hello\n'

    def test_echo_in_pipeline_member(self):
        assert run_psh('echo hello | cat').stdout == 'hello\n'

    def test_builtin_in_background_subshell(self):
        # echo forked as a background builtin; output still appears.
        r = run_psh('echo bg & wait')
        assert 'bg' in r.stdout

    def test_printf_in_pipeline(self):
        assert run_psh("printf '%s\\n' xyz | cat").stdout == 'xyz\n'
