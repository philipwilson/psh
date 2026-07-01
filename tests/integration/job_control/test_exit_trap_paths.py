"""
Tests for the EXIT trap firing on EVERY shell-exit path (reappraisal #14 H1).

Regression guards: the EXIT trap used to be wired only into the `exit` builtin.
Three other exit paths silently dropped it:
  * a script reaching end-of-file (`script_executor.py` guard was always-false
    because is_script_mode is set at construction);
  * a `set -e` abort (the executor raises SystemExit, bypassing the trap);
  * a backgrounded subshell completing (omitted the call the foreground had).
Now a single chokepoint (`SourceProcessor.execute_as_main`) fires it on EOF and
on a recovered SystemExit, and the background-subshell body fires its own.
Verified against bash 5.2.
"""

import subprocess
import sys


def _run(argv, stdin=None):
    return subprocess.run([sys.executable, '-m', 'psh', *argv],
                          capture_output=True, text=True, input=stdin)


def run_psh_c(cmd):
    return _run(['-c', cmd])


def run_psh_script(tmp_path, script):
    path = tmp_path / "case.sh"
    path.write_text(script)
    return _run([str(path)])


def run_bash_script(tmp_path, script):
    path = tmp_path / "case_bash.sh"
    path.write_text(script)
    return subprocess.run(['bash', str(path)], capture_output=True, text=True)


class TestExitTrapScriptFile:
    def test_fires_at_eof(self, tmp_path):
        r = run_psh_script(tmp_path, 'trap "echo BYE" EXIT\ntrue\n')
        assert r.stdout == "BYE\n"
        assert r.returncode == 0

    def test_fires_on_set_e_abort(self, tmp_path):
        r = run_psh_script(
            tmp_path,
            'trap "echo CLEANUP" EXIT\nset -e\necho before\nfalse\necho after\n')
        assert r.stdout == "before\nCLEANUP\n"
        assert r.returncode == 1

    def test_reads_status_of_last_command(self, tmp_path):
        # Single-quoted action defers $? to trap-fire time (bash: got=42).
        r = run_psh_script(tmp_path, "trap 'echo got=$?' EXIT\n(exit 42)\n")
        assert r.stdout == "got=42\n"
        assert r.returncode == 42

    def test_status_preserved_through_trap(self, tmp_path):
        # The trap runs but does not change the shell's exit status.
        r = run_psh_script(tmp_path, 'trap "echo T" EXIT\nfalse\n')
        assert r.stdout == "T\n"
        assert r.returncode == 1

    def test_trap_exit_overrides_status(self, tmp_path):
        # `exit N` inside the EXIT trap overrides the pending status (bash).
        r = run_psh_script(tmp_path, 'trap "exit 7" EXIT\nfalse\n')
        assert r.returncode == 7

    def test_explicit_exit_fires_trap_once(self, tmp_path):
        r = run_psh_script(tmp_path, 'trap "echo ONCE" EXIT\necho a\nexit 0\necho b\n')
        assert r.stdout == "a\nONCE\n"
        assert r.returncode == 0

    def test_sourced_file_trap_deferred_to_main_exit(self, tmp_path):
        inc = tmp_path / "inc.sh"
        inc.write_text('trap "echo SRC" EXIT\n')
        r = run_psh_script(tmp_path, f'. {inc}\necho mid\n')
        assert r.stdout == "mid\nSRC\n"
        assert r.returncode == 0

    def test_source_that_exits_fires_main_trap_once(self, tmp_path):
        ex = tmp_path / "ex.sh"
        ex.write_text('exit 4\n')
        r = run_psh_script(tmp_path, f'trap "echo MAINBYE" EXIT\n. {ex}\necho notreached\n')
        assert r.stdout == "MAINBYE\n"
        assert r.returncode == 4

    def test_matches_bash_set_e_abort(self, tmp_path):
        script = 'trap "echo CLEANUP" EXIT\nset -e\necho before\nfalse\necho after\n'
        psh = run_psh_script(tmp_path, script)
        bash = run_bash_script(tmp_path, script)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode


class TestExitTrapCommandString:
    def test_fires_on_set_e_abort(self):
        r = run_psh_c('trap "echo CLEANUP" EXIT; set -e; false; echo after')
        assert r.stdout == "CLEANUP\n"
        assert r.returncode == 1

    def test_normal_eof(self):
        r = run_psh_c('trap "echo BYE" EXIT; echo hi')
        assert r.stdout == "hi\nBYE\n"
        assert r.returncode == 0


class TestExitTrapStdin:
    def test_fires_from_piped_stdin(self):
        r = _run([], stdin='trap "echo SBYE" EXIT\necho hi\n')
        assert r.stdout == "hi\nSBYE\n"
        assert r.returncode == 0


class TestExitTrapSubshell:
    def test_foreground_subshell_runs_own_exit_trap(self):
        r = run_psh_c('( trap "echo fgbye" EXIT; echo in ); echo out')
        assert r.stdout == "in\nfgbye\nout\n"

    def test_background_subshell_runs_own_exit_trap(self):
        r = run_psh_c('( trap "echo subbye" EXIT; sleep 0.05 ) & wait; echo main')
        assert "subbye" in r.stdout
        assert r.stdout.strip().endswith("main")

    def test_nested_subshell_traps(self):
        r = run_psh_c('( trap "echo outer" EXIT; ( trap "echo inner" EXIT; echo deep ) ); echo top')
        assert r.stdout == "deep\ninner\nouter\ntop\n"


class TestExitTrapSubstitutionChildren:
    """Substitution children are subshells: each runs its own EXIT trap
    (reappraisal #15, adjacent to F2 — the run_child_shell exit path
    dropped it while ( ... ) subshells fired theirs)."""

    def test_command_substitution_runs_own_exit_trap(self):
        r = run_psh_c('x=$(trap "echo inner" EXIT); echo "x=$x"')
        assert r.stdout == "x=inner\n"

    def test_command_substitution_posix_trap_0(self):
        r = run_psh_c('x=$(trap "echo inner" 0); echo "x=$x"')
        assert r.stdout == "x=inner\n"

    def test_command_substitution_exit_n_keeps_status(self):
        r = run_psh_c('x=$(trap "echo bye" EXIT; exit 5); echo "x=$x rc=$?"')
        assert r.stdout == "x=bye rc=5\n"

    def test_exit_inside_exit_trap_sets_child_status(self):
        r = run_psh_c('x=$(trap "echo bye; exit 7" EXIT; exit 5); echo "x=$x rc=$?"')
        assert r.stdout == "x=bye rc=7\n"

    def test_process_substitution_runs_own_exit_trap(self):
        r = run_psh_c('cat <(trap "echo bye" EXIT; echo body); echo after')
        assert r.stdout == "body\nbye\nafter\n"

    def test_parent_exit_trap_not_fired_in_child(self):
        # Subshells reset inherited traps; only the parent fires "parent".
        r = run_psh_c('trap "echo parent" EXIT; x=$(echo hi); echo "x=$x"')
        assert r.stdout == "x=hi\nparent\n"
