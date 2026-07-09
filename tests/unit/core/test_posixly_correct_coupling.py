"""POSIXLY_CORRECT <-> posix option two-way coupling (bash set_posix_mode).

Task #31: psh wires the existing ``posix`` shell option to the
POSIXLY_CORRECT variable in both directions, exactly like bash:

* assigning POSIXLY_CORRECT (any value, even empty) enables posix mode;
  unsetting it disables posix mode (the variable observer, sv_strict_posix);
* ``set -o posix`` binds POSIXLY_CORRECT to ``y`` (unexported, and only when
  the variable is not already set); ``set +o posix`` unsets it (the option
  on_change observer).

These pin the coupling in-process; the conformance file re-checks the same
table against live bash, and the system suite covers the ``--posix`` flag and
the real-environment startup import which need a subprocess.
"""

import pytest

from psh.shell import Shell


@pytest.fixture
def shell():
    # No teardown needed: these tests start no background jobs.
    return Shell()


def _posix(sh) -> bool:
    return bool(sh.state.options.get('posix'))


def _var(sh):
    return sh.state.scope_manager.get_variable('POSIXLY_CORRECT')


# --- variable -> option --------------------------------------------------

def test_assign_enables_posix(shell):
    assert _posix(shell) is False
    shell.run_command('POSIXLY_CORRECT=x')
    assert _posix(shell) is True


def test_empty_assign_enables_posix(shell):
    shell.run_command('POSIXLY_CORRECT=')
    assert _posix(shell) is True


def test_unset_disables_posix(shell):
    shell.run_command('POSIXLY_CORRECT=1')
    assert _posix(shell) is True
    shell.run_command('unset POSIXLY_CORRECT')
    assert _posix(shell) is False


def test_reassignment_keeps_value_and_posix_on(shell):
    shell.run_command('POSIXLY_CORRECT=1; POSIXLY_CORRECT=2')
    assert _posix(shell) is True
    assert _var(shell) == '2'


# --- option -> variable --------------------------------------------------

def test_set_o_posix_binds_y(shell):
    shell.run_command('set -o posix')
    assert _posix(shell) is True
    assert _var(shell) == 'y'


def test_set_o_posix_binding_is_not_exported(shell):
    shell.run_command('set -o posix')
    # bash: set -o posix creates POSIXLY_CORRECT but does NOT export it.
    assert 'POSIXLY_CORRECT' not in shell.state.env


def test_set_o_posix_keeps_existing_value(shell):
    # An existing value is preserved (already-on when set -o posix runs).
    shell.run_command('POSIXLY_CORRECT=custom; set -o posix')
    assert _var(shell) == 'custom'


def test_set_plus_o_posix_unsets_variable(shell):
    shell.run_command('POSIXLY_CORRECT=1; set +o posix')
    assert _posix(shell) is False
    assert _var(shell) is None


def test_round_trip(shell):
    shell.run_command('set -o posix')
    assert _var(shell) == 'y'
    shell.run_command('set +o posix')
    assert _var(shell) is None
    assert _posix(shell) is False


# --- SHELLOPTS reflection (cross-release with v0.675) --------------------

def test_shellopts_lists_posix_after_assign(shell):
    shell.run_command('POSIXLY_CORRECT=1')
    shellopts = shell.state.scope_manager.get_variable('SHELLOPTS') or ''
    assert 'posix' in shellopts.split(':')


# --- readonly is tolerated silently --------------------------------------

def test_set_plus_o_posix_readonly_is_silent(shell, capsys):
    # A user-made-readonly POSIXLY_CORRECT is pathological; the coupling must
    # not emit a "readonly variable" diagnostic the plain toggle never did.
    shell.run_command('readonly POSIXLY_CORRECT=1')
    capsys.readouterr()
    shell.run_command('set +o posix')
    err = capsys.readouterr().err
    assert 'readonly' not in err
    assert _posix(shell) is False


# --- startup environment import (in-process, monkeypatched env) ----------

def test_startup_env_enables_posix(monkeypatch):
    monkeypatch.setenv('POSIXLY_CORRECT', '1')
    sh = Shell()
    assert bool(sh.state.options.get('posix')) is True
    # Imported as an exported shell variable (arrived via the environment).
    assert sh.state.scope_manager.get_variable('POSIXLY_CORRECT') == '1'


def test_startup_env_empty_enables_posix(monkeypatch):
    monkeypatch.setenv('POSIXLY_CORRECT', '')
    sh = Shell()
    assert bool(sh.state.options.get('posix')) is True


def test_no_startup_env_posix_off(monkeypatch):
    monkeypatch.delenv('POSIXLY_CORRECT', raising=False)
    sh = Shell()
    assert bool(sh.state.options.get('posix')) is False
