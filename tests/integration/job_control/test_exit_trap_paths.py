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

reappraisal #15 F3 adds the FOURTH dropped path: death from an untrapped fatal
signal (SIGTERM/SIGHUP/SIGINT). The script-mode signal handler used to re-raise
the signal without running the EXIT trap, so `psh script.sh &; kill %1` died
silently while bash ran the trap. `SignalManager._terminate_from_signal` now
reuses the same idempotent chokepoint before re-raising. See
`TestExitTrapOnFatalSignal`.
"""

import os
import signal
import subprocess
import sys
import time


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


def _wait_for_child(pid, timeout=10.0):
    """Block until `pid` has spawned a child process, then return True.

    In these tests the child is the script's `sleep`, which runs only AFTER the
    `trap` line — so "the shell has a child" proves the trap is installed AND the
    shell has entered the sleep. Signalling at that moment cannot race trap
    installation; and because we signal the instant the sleep begins, the sleep
    always has its full (short) duration left to hold the pipe. Both properties
    are independent of machine load, unlike a fixed pre-signal delay. Returns
    False if no child appears within `timeout` (caller signals anyway; the poll
    never hangs).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(['pgrep', '-P', str(pid)],
                           capture_output=True, text=True)
        if r.stdout.strip():
            return True
        time.sleep(0.01)
    return False


def _spawn_and_signal(argv, sig, delay=None, timeout=20):
    """Start a shell, deliver `sig` to its PID once it is in the sleep, and
    return (stdout, stderr, returncode). A negative returncode is -signum
    (WIFSIGNALED); >=0 is a normal exit code.

    Readiness is EVENT-BASED by default (``delay=None``): wait for the shell to
    spawn its ``sleep`` child (``_wait_for_child``) before signalling, rather
    than guessing a fixed delay. This is load-independent and lets the scripts
    use a short ``sleep`` (the orphan then holds the pipe only briefly, so
    ``communicate`` returns fast). Pass an explicit ``delay=`` for a script with
    no observable child (the builtin busy-loop case), which falls back to a
    fixed pre-signal sleep.

    The signal goes to the shell PID only (not its process group), so the
    foreground `sleep` child is untouched — exactly the F3 probe: a fatal
    signal aimed at the shell itself. `communicate` blocks until EOF, which
    the orphaned sleep releases when it finishes; the shell's own death is
    captured in `returncode`.
    """
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    if delay is None:
        _wait_for_child(proc.pid)
    else:
        time.sleep(delay)
    try:
        os.kill(proc.pid, sig)
    except ProcessLookupError:
        pass
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        out += "\n[TIMEOUT]"
    return out, err, proc.returncode


def _psh_script_signal(tmp_path, script, sig, **kw):
    path = tmp_path / "sig.sh"
    path.write_text(script)
    return _spawn_and_signal([sys.executable, '-m', 'psh', str(path)], sig, **kw)


def _bash_script_signal(tmp_path, script, sig, **kw):
    path = tmp_path / "sig_bash.sh"
    path.write_text(script)
    return _spawn_and_signal(['bash', str(path)], sig, **kw)


class TestExitTrapOnFatalSignal:
    """reappraisal #15 F3: an untrapped fatal signal must run the EXIT trap
    before the shell dies, and the shell must still die BY the signal
    (128+N wait status) so its parent sees a genuine signal death.

    Regression: psh used to die silently on SIGTERM/SIGHUP/SIGINT — the
    v0.540 EXIT-trap chokepoint covered EOF/`set -e`/`exit` but not the
    signal path. Pinned to bash 5.2. (Signals are delivered to a live
    process, so these cannot be golden_cases entries — that harness only
    diffs command stdout/exit codes.)

    Auto-marked ``serial`` by the ``job_control/`` path (kills/waits on
    processes — xdist-unsafe).
    """

    def test_sigterm_fires_exit_trap_then_dies_by_signal(self, tmp_path):
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo EXIT-TRAP-FIRED" EXIT\nsleep 0.5\n',
            signal.SIGTERM)
        assert out == "EXIT-TRAP-FIRED\n"
        assert rc == -signal.SIGTERM  # WIFSIGNALED -> parent sees 128+15

    def test_matches_bash_for_sigterm(self, tmp_path):
        script = 'trap "echo EXIT-TRAP-FIRED" EXIT\nsleep 0.5\n'
        p = _psh_script_signal(tmp_path, script, signal.SIGTERM)
        b = _bash_script_signal(tmp_path, script, signal.SIGTERM)
        assert (p[0], p[2]) == (b[0], b[2])

    def test_sighup_fires_exit_trap_then_dies_by_signal(self, tmp_path):
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo BYE" EXIT\nsleep 0.5\n', signal.SIGHUP)
        assert out == "BYE\n"
        assert rc == -signal.SIGHUP

    def test_dollar_question_inside_trap(self, tmp_path):
        # $? inside the EXIT trap is 0 here (bash): the pending signal does
        # not itself set $?, and the last-run command was the trap builtin.
        out, err, rc = _psh_script_signal(
            tmp_path, "trap 'echo status=$?' EXIT\nsleep 0.5\n", signal.SIGTERM)
        assert out == "status=0\n"
        assert rc == -signal.SIGTERM

    def test_exit_trap_fires_exactly_once(self, tmp_path):
        # The signal handler and execute_as_main share one idempotent
        # chokepoint — the trap body must appear exactly once.
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo ONCE" EXIT\nsleep 0.5\n', signal.SIGTERM)
        assert out.count("ONCE") == 1
        assert rc == -signal.SIGTERM

    def test_command_mode_fires_exit_trap(self, tmp_path):
        # -c shares execute_as_main, so the same chokepoint fires.
        out, err, rc = _spawn_and_signal(
            [sys.executable, '-m', 'psh', '-c',
             'trap "echo CBYE" EXIT; sleep 0.5'],
            signal.SIGTERM)
        assert out == "CBYE\n"
        assert rc == -signal.SIGTERM

    def test_stdin_mode_fires_exit_trap(self, tmp_path):
        # Piped stdin is non-interactive too (is_script_mode is unset there),
        # so the fatal-signal path must fire the EXIT trap for it as well.
        script = 'trap "echo SBYE" EXIT\nsleep 0.5\n'
        proc = subprocess.Popen(
            [sys.executable, '-m', 'psh'], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        proc.stdin.write(script)
        proc.stdin.flush()
        proc.stdin.close()
        _wait_for_child(proc.pid)
        os.kill(proc.pid, signal.SIGTERM)
        out, err = proc.communicate(timeout=20)
        assert out == "SBYE\n"
        assert proc.returncode == -signal.SIGTERM

    def test_signal_trap_takes_precedence_over_exit(self, tmp_path):
        # A trap ON the signal runs and does NOT terminate the shell; the EXIT
        # trap fires only at the eventual normal exit. Regression pin: this
        # already worked and must keep working after the F3 fix.
        script = ('trap "echo got-term" TERM\n'
                  'trap "echo EXIT" EXIT\n'
                  'sleep 0.5\n')
        p = _psh_script_signal(tmp_path, script, signal.SIGTERM)
        b = _bash_script_signal(tmp_path, script, signal.SIGTERM)
        assert p[0] == "got-term\nEXIT\n"
        assert p[2] == 0  # normal exit, NOT a signal death
        assert (p[0], p[2]) == (b[0], b[2])

    def test_signal_death_in_subshell_fires_both_exit_traps(self, tmp_path):
        # The parent's EXIT trap AND the subshell's own EXIT trap both fire;
        # the shell still dies by the signal (wave-1 e-adopt subshell-exit
        # semantics preserved under a fatal signal).
        script = ('trap "echo OUTER" EXIT\n'
                  '( trap "echo INNER" EXIT; sleep 0.5 )\n'
                  'echo after\n')
        p = _psh_script_signal(tmp_path, script, signal.SIGTERM)
        b = _bash_script_signal(tmp_path, script, signal.SIGTERM)
        assert "OUTER" in p[0] and "INNER" in p[0]
        assert "after" not in p[0]
        assert p[2] == -signal.SIGTERM
        assert (p[0], p[2]) == (b[0], b[2])

    def test_sigint_running_own_code_fires_exit_trap(self, tmp_path):
        # SIGINT delivered while the shell runs its OWN code (a builtin loop,
        # no foreground external command) terminates it, running the EXIT trap
        # and dying by SIGINT — matching bash. (During a foreground external
        # command SIGINT is instead ignored by bash; psh does not yet
        # replicate that fg-child masking — deeper job-control, out of F3.)
        script = 'trap "echo INT-TRAP" EXIT\ni=0\nwhile :; do i=$((i+1)); done\n'
        p = _psh_script_signal(tmp_path, script, signal.SIGINT, delay=0.6)
        b = _bash_script_signal(tmp_path, script, signal.SIGINT, delay=0.6)
        assert p[0] == "INT-TRAP\n"
        assert p[2] == -signal.SIGINT
        assert (p[0], p[2]) == (b[0], b[2])

    # --- fix-introduced-defect regression: EXIT trap that itself calls
    # `exit N` under a fatal signal must NOT rob the shell of its 128+N
    # signal-death wait status. The `exit` builtin raises SystemExit; if that
    # escapes the signal handler it bypasses the re-raise and the shell exits
    # normally (rc=0/N). bash keeps the signal death regardless. ---

    def test_exit0_in_exit_trap_still_dies_by_sigterm(self, tmp_path):
        # THE reported defect: `exit 0` in the EXIT trap used to make psh exit
        # normally (rc=0); it must still die BY SIGTERM (128+15).
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo cleanup; exit 0" EXIT\nsleep 0.5\n',
            signal.SIGTERM)
        assert out == "cleanup\n"
        assert rc == -signal.SIGTERM

    def test_exit7_in_exit_trap_still_dies_by_sigterm(self, tmp_path):
        # A non-zero `exit N` in the trap likewise loses to the signal death.
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo cleanup; exit 7" EXIT\nsleep 0.5\n',
            signal.SIGTERM)
        assert out == "cleanup\n"
        assert rc == -signal.SIGTERM

    def test_exit_in_exit_trap_fires_trap_exactly_once(self, tmp_path):
        # The trap body still runs exactly once even though it raises
        # SystemExit (TrapManager sets its idempotency flag before the body).
        out, err, rc = _psh_script_signal(
            tmp_path, 'trap "echo ONCE; exit 0" EXIT\nsleep 0.5\n',
            signal.SIGTERM)
        assert out.count("ONCE") == 1
        assert rc == -signal.SIGTERM

    def test_exit_in_exit_trap_matches_bash_sigterm(self, tmp_path):
        # Pinned to bash 5.2: stdout AND wait status must agree.
        script = 'trap "echo cleanup; exit 0" EXIT\nsleep 0.5\n'
        p = _psh_script_signal(tmp_path, script, signal.SIGTERM)
        b = _bash_script_signal(tmp_path, script, signal.SIGTERM)
        assert (p[0], p[2]) == (b[0], b[2])
        assert p[2] == -signal.SIGTERM

    def test_exit0_in_exit_trap_command_mode_dies_by_signal(self, tmp_path):
        # -c mode shares the same signal path; the SystemExit must not escape.
        out, err, rc = _spawn_and_signal(
            [sys.executable, '-m', 'psh', '-c',
             'trap "echo cleanup; exit 0" EXIT; sleep 0.5'],
            signal.SIGTERM)
        assert out == "cleanup\n"
        assert rc == -signal.SIGTERM
