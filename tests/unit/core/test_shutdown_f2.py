"""Shell.shutdown(reason): idempotent, THE top-level cleanup path (F2).

Behavioral half of the shutdown census (the static half is
tests/unit/tooling/test_shutdown_census_f2.py): every route — exit builtin,
normal source completion, startup failure via __main__'s funnel, REPL EOF
(PTY tier) — converges on one idempotent cleanup, the EXIT trap fires
exactly once, and deactivation releases process ownership so a subsequent
shell can take over.

Order-independent: in-process tests build their own shells and close them in
``finally``; subprocess tests are hermetic by construction.
"""

import os
import subprocess
import sys

import pytest

from psh.core.process_lease import get_coordinator
from psh.shell import Shell

TREE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def _run_psh(args, **kwargs):
    env = dict(os.environ)
    env['PYTHONPATH'] = TREE
    return subprocess.run([sys.executable, '-m', 'psh', '--norc'] + args,
                          cwd=TREE, env=env, capture_output=True, text=True,
                          timeout=60, **kwargs)


def test_exit_builtin_routes_through_shutdown():
    shell = Shell(norc=True)
    try:
        with pytest.raises(SystemExit) as exc:
            shell.run_command('exit 5')
        assert exc.value.code == 5
        assert shell._shutdown_reason == 'exit-builtin'
        # Deactivation released process ownership (mid-execution release is
        # deferred to unwind, which has completed by now).
        assert get_coordinator().current_owner() is not shell.state
    finally:
        shell.close()


def test_shutdown_is_idempotent_and_keeps_first_reason():
    shell = Shell(norc=True)
    try:
        shell.run_command("X=0; trap 'X=$((X+1))' EXIT")
        shell.shutdown('repl-eof')
        assert shell._shutdown_reason == 'repl-eof'
        assert shell.state.get_variable('X') == '1'     # trap fired once
        shell.shutdown('exit-builtin')                  # later call: no-op
        assert shell._shutdown_reason == 'repl-eof'
        assert shell.state.get_variable('X') == '1'     # and only once
    finally:
        shell.close()


def test_shutdown_releases_ownership_for_the_next_shell():
    s1 = Shell(norc=True)
    s1.run_command('echo one >/dev/null')
    s1.shutdown('repl-eof')
    s2 = Shell(norc=True)
    try:
        assert s2.run_command('echo two >/dev/null') == 0
        assert get_coordinator().current_owner() is s2.state
    finally:
        s2.close()


def test_exit_trap_fires_exactly_once_on_exit_builtin():
    """shutdown() fires the trap; execute_as_main's later idempotent firing
    must not double it (subprocess: the real -c route)."""
    result = _run_psh(['-c', 'trap "echo TRAP-ONCE" EXIT; exit 7'])
    assert result.returncode == 7
    assert result.stdout.count('TRAP-ONCE') == 1


def test_exit_trap_fires_exactly_once_on_source_completion():
    result = _run_psh(['-c', 'trap "echo TRAP-ONCE" EXIT; echo body'])
    assert result.returncode == 0
    assert result.stdout.count('TRAP-ONCE') == 1
    assert 'body' in result.stdout


def test_startup_failure_route_is_clean():
    """A missing script exits 127 through __main__'s shutdown funnel with
    no stray diagnostics from cleanup itself."""
    result = _run_psh(['/nonexistent/script-f2.sh'])
    assert result.returncode == 127
    assert 'Traceback' not in result.stderr


def test_exit_status_of_trap_exit_override_preserved():
    """A trap body's own `exit N` still overrides (bash), through shutdown."""
    result = _run_psh(['-c', 'trap "exit 9" EXIT; exit 3'])
    assert result.returncode == 9


def test_script_completion_fires_trap_once(tmp_path):
    script = tmp_path / "s.sh"
    script.write_text('trap "echo SCRIPT-TRAP" EXIT\necho run\n')
    result = _run_psh([str(script)])
    assert result.returncode == 0
    assert result.stdout.count('SCRIPT-TRAP') == 1
