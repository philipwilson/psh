"""$HISTFILE / $HISTSIZE are honored (appraisal Tier 3, M14).

psh hardcoded ``~/.psh_history`` and a 1000-entry cap and ignored the
``HISTFILE`` / ``HISTSIZE`` shell variables, even though the user guide tells
users to set them. ``ShellState.history_file`` / ``max_history_size`` now read
those variables dynamically (bash), falling back to the defaults.
"""

import os

import pytest

from psh.shell import Shell


@pytest.fixture
def shell():
    return Shell(norc=True)


def test_default_when_unset(shell):
    assert shell.state.history_file == os.path.expanduser("~/.psh_history")
    assert shell.state.max_history_size == 1000


def test_histfile_honored(shell):
    shell.state.set_variable('HISTFILE', '/tmp/psh_test_hist')
    assert shell.state.history_file == '/tmp/psh_test_hist'


def test_histfile_tilde_expanded(shell):
    shell.state.set_variable('HISTFILE', '~/custom_hist')
    assert shell.state.history_file == os.path.expanduser('~/custom_hist')


def test_histsize_honored(shell):
    shell.state.set_variable('HISTSIZE', '42')
    assert shell.state.max_history_size == 42


def test_histsize_zero(shell):
    shell.state.set_variable('HISTSIZE', '0')
    assert shell.state.max_history_size == 0


def test_invalid_histsize_falls_back(shell):
    shell.state.set_variable('HISTSIZE', 'not-a-number')
    assert shell.state.max_history_size == 1000


def test_negative_histsize_falls_back(shell):
    shell.state.set_variable('HISTSIZE', '-5')
    assert shell.state.max_history_size == 1000


def test_histsize_trims_on_save(tmp_path):
    # HISTSIZE actually limits what HistoryManager persists.
    shell = Shell(norc=True)
    histfile = tmp_path / "h"
    shell.state.set_variable('HISTFILE', str(histfile))
    shell.state.set_variable('HISTSIZE', '3')
    shell.state.history = ['c1', 'c2', 'c3', 'c4', 'c5']
    shell.interactive_manager.history_manager.save_to_file()
    saved = histfile.read_text().splitlines()
    assert saved == ['c3', 'c4', 'c5']
