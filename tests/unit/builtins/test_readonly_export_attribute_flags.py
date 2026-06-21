"""readonly accepts -a/-A; export accepts -f (appraisal H6/H7).

bash's ``readonly`` accepts ``-aAfp`` and ``export`` accepts ``-fpn``; psh
rejected the attribute/function flags outright (``readonly: invalid option:
-a``, ``export: -f: invalid option``), so the everyday "readonly array" and
"export a function" idioms failed with exit 2 — fatal under ``set -e``. The two
hand-rolled flag parsers now forward ``-a``/``-A`` to ``declare -r`` and handle
``export -f`` via a function export attribute (appraisal 2026-06-21, H6/H7).

Every expectation was probe-verified against bash 5.2.
"""

import subprocess
import sys


def run(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestReadonlyArrayFlags:
    def test_readonly_indexed_array(self, captured_shell):
        rc = captured_shell.run_command('readonly -a arr=(1 2 3)')
        assert rc == 0
        captured_shell.run_command('echo "${arr[@]}"')
        assert captured_shell.get_stdout() == '1 2 3\n'

    def test_readonly_associative_array(self, captured_shell):
        rc = captured_shell.run_command('readonly -A m=([k]=v)')
        assert rc == 0
        captured_shell.run_command('echo "${m[k]}"')
        assert captured_shell.get_stdout() == 'v\n'

    def test_readonly_array_is_readonly(self):
        # Assigning to a readonly array element fails (exit 1), exactly like a
        # readonly scalar; bash aborts the -c script on the violation.
        r = run('readonly -a arr=(1 2); arr[0]=9; echo "${arr[@]}"')
        assert r.returncode != 0

    def test_readonly_ar_declare_p(self, captured_shell):
        captured_shell.run_command('readonly -a arr=(x y)')
        captured_shell.clear_output()
        captured_shell.run_command('declare -p arr')
        assert captured_shell.get_stdout() == 'declare -ar arr=([0]="x" [1]="y")\n'

    def test_unknown_flag_still_rejected(self, captured_shell):
        rc = captured_shell.run_command('readonly -Z x=1')
        assert rc == 2


class TestExportFunctionFlag:
    def test_export_function_succeeds(self, captured_shell):
        captured_shell.run_command('myfn() { echo hi; }')
        rc = captured_shell.run_command('export -f myfn')
        assert rc == 0

    def test_export_function_marks_attribute(self, captured_shell):
        captured_shell.run_command('myfn() { echo hi; }; export -f myfn')
        assert captured_shell.function_manager.get_function('myfn').exported

    def test_export_minus_f_nonexistent_is_error(self, captured_shell):
        rc = captured_shell.run_command('export -f nope')
        assert rc == 1

    def test_export_minus_f_on_variable_is_error(self, captured_shell):
        rc = captured_shell.run_command('x=5; export -f x')
        assert rc == 1

    def test_export_fn_unmarks(self, captured_shell):
        captured_shell.run_command('f() { :; }; export -f f; export -fn f')
        assert not captured_shell.function_manager.get_function('f').exported

    def test_export_f_listing(self, captured_shell):
        captured_shell.run_command('g() { :; }; export -f g')
        captured_shell.clear_output()
        captured_shell.run_command('export -f')
        assert 'declare -fx g' in captured_shell.get_stdout()

    def test_export_function_survives_redefinition(self, captured_shell):
        captured_shell.run_command('f() { echo a; }; export -f f; f() { echo b; }')
        assert captured_shell.function_manager.get_function('f').exported
