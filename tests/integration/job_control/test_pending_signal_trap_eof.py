"""A signal trap queued by the FINAL statement fires before the shell exits.

R18 T2-E (M-cc2): psh ran pending signal traps at the START of each statement
(`ExecutorVisitor.visit_StatementList`), so a trap queued by the LAST statement
— e.g. a script whose final line is `kill -TERM $$` with a TERM trap — had no
later command boundary to fire at and was silently dropped when there was no
EXIT trap to force one. bash runs the pending trap before exit.
`SourceProcessor.execute_as_main` now flushes pending traps before the EXIT
trap. Pinned against bash 5.2.
"""
from shell_oracle import is_comparable, run_bash, run_psh


def _run(script, tmp_path, name):
    path = tmp_path / name
    path.write_text(script)
    psh = run_psh([str(path)], timeout=10)
    assert is_comparable(psh), psh
    bash = run_bash([str(path)], timeout=10)
    assert is_comparable(bash), bash
    return psh, bash


def test_term_trap_last_statement_no_exit_trap(tmp_path):
    psh, bash = _run(
        'trap "echo GOT_TERM" TERM\necho before\nkill -TERM $$\n',
        tmp_path, 'a.sh')
    assert psh.stdout == 'before\nGOT_TERM\n'
    assert psh.returncode == 0
    assert psh.stdout == bash.stdout and psh.returncode == bash.returncode


def test_term_trap_last_statement_with_exit_trap(tmp_path):
    psh, bash = _run(
        'trap "echo GOT_TERM" TERM\ntrap "echo GOT_EXIT" EXIT\n'
        'echo before\nkill -TERM $$\n',
        tmp_path, 'b.sh')
    assert psh.stdout == 'before\nGOT_TERM\nGOT_EXIT\n'
    assert psh.returncode == 0
    assert psh.stdout == bash.stdout and psh.returncode == bash.returncode


def test_pending_trap_action_that_exits_sets_status(tmp_path):
    psh, bash = _run(
        'trap "echo GOT; exit 7" TERM\nkill -TERM $$\n',
        tmp_path, 'c.sh')
    assert psh.stdout == 'GOT\n'
    assert psh.returncode == 7
    assert psh.stdout == bash.stdout and psh.returncode == bash.returncode


def test_pending_trap_action_exits_still_runs_exit_trap(tmp_path):
    psh, bash = _run(
        'trap "echo GOT; exit 7" TERM\ntrap "echo BYE" EXIT\nkill -TERM $$\n',
        tmp_path, 'd.sh')
    assert psh.stdout == 'GOT\nBYE\n'
    assert psh.returncode == 7
    assert psh.stdout == bash.stdout and psh.returncode == bash.returncode


def test_hup_trap_last_statement(tmp_path):
    psh, bash = _run(
        'trap "echo GOT_HUP" HUP\nkill -HUP $$\n', tmp_path, 'e.sh')
    assert psh.stdout == 'GOT_HUP\n'
    assert psh.returncode == 0
    assert psh.stdout == bash.stdout and psh.returncode == bash.returncode


def test_dash_c_pending_trap(tmp_path):
    # Same fix on the -c path (StringInput also routes through execute_as_main).
    psh = run_psh(
        ['-c', 'trap "echo GOT_TERM" TERM; echo before; kill -TERM $$'],
        timeout=10)
    assert is_comparable(psh), psh
    assert psh.stdout == 'before\nGOT_TERM\n'
    assert psh.returncode == 0
