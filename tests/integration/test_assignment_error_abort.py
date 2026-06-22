"""
A fatal assignment error aborts the current top-level command, not the shell
(reappraisal #14 H6).

A readonly-variable or circular-nameref assignment error used to `sys.exit(1)`
the whole shell in script mode, so a script that hit such an error mid-way
silently died and lost every following line. bash reports the error, unwinds
the WHOLE current top-level command (the rest of the command list and any
enclosing if/loop/function/subshell on the same input), and resumes at the next
top-level command. Verified against bash 5.2.

(The arithmetic-assignment-error `-c`-vs-script nuance is a separate, deferred
follow-up — H6b in the reappraisal report.)
"""

import subprocess
import sys


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def _psh_script(tmp_path, script):
    p = tmp_path / "case.sh"
    p.write_text(script)
    return subprocess.run([sys.executable, '-m', 'psh', str(p)],
                          capture_output=True, text=True)


def _bash_script(tmp_path, script):
    p = tmp_path / "case_bash.sh"
    p.write_text(script)
    return subprocess.run(['bash', str(p)], capture_output=True, text=True)


def _assert_matches_bash_script(tmp_path, script):
    psh = _psh_script(tmp_path, script)
    bash = _bash_script(tmp_path, script)
    assert psh.stdout == bash.stdout, f"stdout differs for {script!r}"
    assert psh.returncode == bash.returncode, f"rc differs for {script!r}"
    # Both must diagnose on stderr (wording/prefix differs and is excluded).
    assert bool(psh.stderr) == bool(bash.stderr), f"stderr presence differs for {script!r}"


class TestReadonlyAbortScopeMatchesBash:
    def test_multiline_continues_next_line(self, tmp_path):
        _assert_matches_bash_script(tmp_path, 'readonly r=1\nr=2\necho REACHED\n')

    def test_if_body_aborts_to_next_line(self, tmp_path):
        _assert_matches_bash_script(
            tmp_path, 'readonly r=1\nif true; then r=2; echo IN; fi\necho OUT\n')

    def test_loop_body_aborts_whole_loop(self, tmp_path):
        _assert_matches_bash_script(
            tmp_path, 'readonly r=1\nfor i in 1 2; do r=2; echo IN$i; done\necho OUT\n')

    def test_function_body_aborts_caller_continues(self, tmp_path):
        _assert_matches_bash_script(
            tmp_path, 'readonly r=1\nf(){ r=2; echo INF; }\nf\necho OUT\n')

    def test_subshell_aborts_parent_continues(self, tmp_path):
        _assert_matches_bash_script(
            tmp_path, 'readonly r=1\n( r=2; echo INSUB )\necho OUT\n')

    def test_two_bad_lines_both_reported_then_continue(self, tmp_path):
        _assert_matches_bash_script(tmp_path, 'readonly r=1\nr=2\nr=3\necho END\n')

    def test_nameref_cycle_multiline_continues(self, tmp_path):
        _assert_matches_bash_script(
            tmp_path, 'declare -n a=b\ndeclare -n b=a\na=5\necho REACHED\n')


class TestReadonlyAbortDirect:
    def test_oneliner_aborts_rest_of_list(self):
        # All on one line -> the whole command list aborts (NOTREACHED skipped).
        r = _psh_c('readonly r=1; r=2; echo NOTREACHED')
        assert 'NOTREACHED' not in r.stdout
        assert r.returncode == 1

    def test_multiline_c_continues(self):
        r = _psh_c('readonly r=1\nr=2\necho REACHED')
        assert r.stdout == "REACHED\n"
        assert r.returncode == 0

    def test_shell_survives_does_not_exit(self):
        # The shell keeps running after the error (the bug was a full exit).
        r = _psh_c('readonly r=1\nr=2\necho alive')
        assert "alive" in r.stdout

    def test_command_substitution_aborts_sub_only(self):
        r = _psh_c('readonly r=1; x=$(r=2; echo SUB); echo "x=[$x] done"')
        # The sub aborts before echo SUB; the outer command continues.
        assert "done" in r.stdout
        assert "SUB" not in r.stdout

    def test_prefix_assignment_still_runs_command(self):
        # RO=2 cmd (prefix) is NOT a pure assignment: the command still runs.
        r = _psh_c('RO=1; readonly RO; RO=2 echo INLINE; echo AFTER')
        assert "INLINE" in r.stdout
        assert "AFTER" in r.stdout
