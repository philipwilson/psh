"""
Tests for common scripting idioms added in v0.262.0:
scalar +=, export +=, printf -v, printf %(fmt)T, quoted-regex-as-literal
in [[ =~ ]], and the `builtin` builtin. Verified against bash 5.2.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestAppendAssignment:
    def test_scalar_append(self):
        assert run_psh('x=a; x+=b; echo "$x"').stdout == 'ab\n'

    def test_append_to_unset(self):
        assert run_psh('unset y; y+=tail; echo "$y"').stdout == 'tail\n'

    def test_integer_append_adds(self):
        assert run_psh('declare -i n=1; n+=2; echo $n').stdout == '3\n'

    def test_append_empty_keeps_value(self):
        assert run_psh('x=a; x+=""; echo "[$x]"').stdout == '[a]\n'

    def test_readonly_append_aborts(self):
        result = run_psh('readonly r=1; r+=x; echo after')
        assert 'after' not in result.stdout
        assert 'readonly variable' in result.stderr

    def test_command_prefix_append_is_temporary(self):
        assert run_psh('V=x; x+=1 env >/dev/null; echo "[$x]"').stdout == '[]\n'

    def test_export_append(self):
        result = run_psh('export PATH+=:/extra; echo "$PATH"')
        assert result.stdout.rstrip().endswith(':/extra')

    def test_array_append_still_works(self):
        assert run_psh('a=(1 2); a+=(3); echo "${a[@]}"').stdout == '1 2 3\n'


class TestPrintfV:
    def test_stores_instead_of_printing(self):
        result = run_psh('printf -v v "%s-%s" a b; echo "$v"')
        assert result.stdout == 'a-b\n'

    def test_format_cycling(self):
        assert run_psh('printf -v out "[%s]" x y; echo "$out"').stdout == '[x][y]\n'

    def test_missing_varname_is_usage_error(self):
        assert run_psh('printf -v').returncode == 2


class TestPrintfDateFormat:
    def test_explicit_epoch(self):
        result = run_psh('printf "%(%Y-%m-%d)T\\n" 1000000000')
        assert result.stdout == '2001-09-09\n'

    def test_no_argument_means_now(self):
        result = run_psh('printf "%(%Y)T\\n"')
        assert result.stdout.strip().isdigit()
        assert int(result.stdout) >= 2026

    def test_with_dash_v(self):
        result = run_psh('printf -v v "%(%Y)T" 1000000000; echo "$v"')
        assert result.stdout == '2001\n'


class TestQuotedRegexLiteral:
    def test_double_quoted_regex_is_literal(self):
        assert run_psh('[[ "abc" =~ "a.c" ]] && echo m || echo no').stdout == 'no\n'

    def test_single_quoted_regex_is_literal(self):
        assert run_psh("[[ abc =~ 'a.c' ]] && echo m || echo no").stdout == 'no\n'

    def test_literal_match_succeeds(self):
        assert run_psh('[[ "a.c" =~ "a.c" ]] && echo m').stdout == 'm\n'

    def test_unquoted_regex_still_regex(self):
        assert run_psh('[[ abc =~ a.c ]] && echo m').stdout == 'm\n'

    def test_variable_regex_still_regex(self):
        assert run_psh('v="^a"; [[ abc =~ $v ]] && echo m').stdout == 'm\n'

    def test_bash_rematch_groups_intact(self):
        assert run_psh('[[ abc =~ ^a(b)c$ ]] && echo "${BASH_REMATCH[1]}"').stdout == 'b\n'


class TestBuiltinBuiltin:
    def test_runs_builtin(self):
        assert run_psh('builtin echo hi').stdout == 'hi\n'

    def test_function_wrapper_no_recursion(self):
        """Regression: wrappers used to recurse to 'command not found'."""
        result = run_psh('echo(){ builtin echo "wrapped:$*"; }; echo hi')
        assert result.stdout == 'wrapped:hi\n'

    def test_not_a_builtin_rc_1(self):
        result = run_psh('builtin nosuchthing; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert 'not a shell builtin' in result.stderr

    def test_bare_builtin_rc_0(self):
        assert run_psh('builtin; echo rc=$?').stdout == 'rc=0\n'
