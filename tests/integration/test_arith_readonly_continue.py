"""A readonly/nameref failure in arithmetic must not abort a -c list
(reappraisal #17 H1).

``readonly r=5; (( r=9 )); echo after=$?`` used to leak a
ReadonlyVariableError to the buffered-command guard, printing
"psh: -c:1: unexpected error: r: readonly variable" and ABORTING the
whole ``-c`` list. bash prints "r: readonly variable", the command
fails with status 1, and the NEXT command on the same line runs.

Subprocess tests: the abort-vs-continue axis lives in the -c
source-processor path, which in-process fixtures don't exercise.
"""

import subprocess
import sys


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=15)


def _psh_script(tmp_path, script):
    p = tmp_path / "case.sh"
    p.write_text(script)
    return subprocess.run([sys.executable, '-m', 'psh', str(p)],
                          capture_output=True, text=True, timeout=15)


class TestArithReadonlyContinuesMinusCList:
    def test_scalar_paren_command(self):
        r = _psh_c('readonly r=5; (( r=9 )); echo after=$?; echo val=$r')
        assert r.stdout == "after=1\nval=5\n"
        assert "r: readonly variable" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 0

    def test_array_element_paren_command(self):
        r = _psh_c('readonly -a a=(1 2); (( a[0]=9 )); echo after=$?; echo val=${a[0]}')
        assert r.stdout == "after=1\nval=1\n"
        assert "a: readonly variable" in r.stderr
        assert r.returncode == 0

    def test_assoc_element_paren_command(self):
        r = _psh_c('declare -A m=([k]=1); readonly m; (( m[k]++ )); '
                   'echo after=$?; echo val=${m[k]}')
        assert r.stdout == "after=1\nval=1\n"
        assert "m: readonly variable" in r.stderr
        assert r.returncode == 0

    def test_let_array_element(self):
        r = _psh_c("readonly -a a=(1 2); let 'a[0]=9'; echo after=$?; echo val=${a[0]}")
        assert r.stdout == "after=1\nval=1\n"
        assert "a: readonly variable" in r.stderr
        assert r.returncode == 0

    def test_c_style_for_init(self):
        r = _psh_c('readonly z=1; for ((z=0; z<3; z++)); do echo body; done; '
                   'echo after=$?')
        assert r.stdout == "after=1\n"
        assert "z: readonly variable" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 0

    def test_c_style_for_update_body_ran_once(self):
        r = _psh_c('readonly z=1; for ((i=0; i<2; z++)); do echo body; done; '
                   'echo after=$?')
        assert r.stdout == "body\nafter=1\n"
        assert "z: readonly variable" in r.stderr
        assert r.returncode == 0

    def test_nameref_cycle_for_loop_var(self):
        r = _psh_c('declare -n na=nb; declare -n nb=na; '
                   'for na in 1 2; do echo body; done; echo after=$?')
        assert r.stdout == "after=1\n"
        assert "circular name reference" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 0

    def test_nameref_cycle_arith_write_warns_only(self):
        # bash: warn, assignment dropped, (( 5 )) is success.
        r = _psh_c('declare -n na=nb; declare -n nb=na; (( na=5 )); echo after=$?')
        assert r.stdout == "after=0\n"
        assert "circular name reference" in r.stderr
        assert r.returncode == 0

    def test_enhanced_test_arith_operand(self):
        r = _psh_c('readonly r=5; [[ $((r=9)) -eq 9 ]]; echo after=$?; echo val=$r')
        assert r.stdout == "after=1\nval=5\n"
        assert "r: readonly variable" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 0


class TestArithReadonlyScriptFileResumesNextLine:
    def test_paren_command_next_line_runs(self, tmp_path):
        r = _psh_script(tmp_path,
                        'readonly r=5\n(( r=9 ))\necho after=$?\necho val=$r\n')
        assert r.stdout == "after=1\nval=5\n"
        assert "r: readonly variable" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 0

    def test_expansion_context_next_line_runs(self, tmp_path):
        # bash: the failed $(( )) expansion kills only that line;
        # the next lines run (both psh and bash, all input modes).
        r = _psh_script(tmp_path,
                        'readonly -a a=(1 2)\necho $((a[0]=9))\n'
                        'echo after=$?\necho val=${a[0]}\n')
        assert r.stdout == "after=1\nval=1\n"
        assert "a: readonly variable" in r.stderr
        assert r.returncode == 0


class TestArithErrorRedirectScope:
    """Diagnostics from (( )) honour the compound's own redirections
    (bash: `(( r=9 )) 2>/dev/null` prints nothing)."""

    def test_readonly_message_redirected(self):
        r = _psh_c('readonly r=5; (( r=9 )) 2>/dev/null; echo after=$?')
        assert r.stdout == "after=1\n"
        assert r.stderr == ""
        assert r.returncode == 0

    def test_division_by_zero_message_redirected(self):
        r = _psh_c('(( 1/0 )) 2>/dev/null; echo after=$?')
        assert r.stdout == "after=1\n"
        assert r.stderr == ""
        assert r.returncode == 0
