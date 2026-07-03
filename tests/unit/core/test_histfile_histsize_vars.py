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


def test_negative_histsize_unlimited(shell):
    # bash: a negative HISTSIZE means unlimited history (no in-memory trim).
    import sys
    shell.state.set_variable('HISTSIZE', '-5')
    assert shell.state.max_history_size == sys.maxsize


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


def test_histfilesize_unset_falls_back_to_histsize(shell):
    assert shell.state.max_history_file_size is None


def test_histfilesize_honored(shell):
    shell.state.set_variable('HISTFILESIZE', '7')
    assert shell.state.max_history_file_size == 7


def test_negative_histfilesize_inhibits_truncation(shell):
    # bash: a negative HISTFILESIZE inhibits truncation of the file.
    import sys
    shell.state.set_variable('HISTFILESIZE', '-1')
    assert shell.state.max_history_file_size == sys.maxsize


def test_invalid_histfilesize_inhibits_truncation(shell):
    # bash: a non-numeric HISTFILESIZE also inhibits truncation.
    import sys
    shell.state.set_variable('HISTFILESIZE', 'nope')
    assert shell.state.max_history_file_size == sys.maxsize


def test_histfilesize_trims_file_not_histsize(tmp_path):
    # bash: the FILE is trimmed to $HISTFILESIZE, distinct from $HISTSIZE
    # (which caps the in-memory list). HISTSIZE=100 keeps all in memory, but
    # HISTFILESIZE=2 writes only the last two.
    shell = Shell(norc=True)
    histfile = tmp_path / "h"
    shell.state.set_variable('HISTFILE', str(histfile))
    shell.state.set_variable('HISTSIZE', '100')
    shell.state.set_variable('HISTFILESIZE', '2')
    shell.state.history = ['c1', 'c2', 'c3', 'c4']
    shell.interactive_manager.history_manager.save_to_file()
    saved = histfile.read_text().splitlines()
    assert saved == ['c3', 'c4']
