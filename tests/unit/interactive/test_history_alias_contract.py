"""The state.history alias contract (reappraisal #15 K1).

The line editor's HistoryNavigator holds a reference to the shell's
``state.history`` LIST OBJECT for the whole session; nothing re-points it
between reads. Two things must therefore always hold:

1. The editor never substitutes a private list — even when the injected
   history is EMPTY (every fresh install). ``HistoryNavigator(history or
   [])`` did exactly that, leaving up-arrow/Ctrl-R dead all session while
   commands were being recorded.

2. Every HistoryManager operation mutates ``state.history`` IN PLACE.
   erasedups, the HISTSIZE trim and the load-time trim used to rebind
   ``state.history`` to a fresh list, silently disconnecting the editor
   mid-session.
"""

import pytest

from psh.interactive.history_nav import HistoryNavigator
from psh.interactive.line_editor import LineEditor
from psh.shell import Shell


class TestNavigatorAliasesInjectedList:
    def test_initially_empty_list_sees_later_appends(self):
        history: list = []
        nav = HistoryNavigator(history)
        history.append('echo hi')
        nav.reset()
        assert nav.up('') == 'echo hi'

    def test_line_editor_keeps_empty_list_identity(self):
        history: list = []
        editor = LineEditor(history=history)
        assert editor.history is history
        history.append('echo hi')
        editor.history_nav.reset()
        assert editor.history_nav.up('') == 'echo hi'

    def test_line_editor_none_gets_private_list(self):
        editor = LineEditor(history=None)
        assert editor.history == []


@pytest.fixture
def shell():
    return Shell(norc=True)


class TestHistoryManagerMutatesInPlace:
    """Each operation must preserve the identity of state.history."""

    def test_erasedups_preserves_identity(self, shell):
        hist = shell.state.history
        shell.state.set_variable('HISTCONTROL', 'erasedups')
        hm = shell.interactive_manager.history_manager
        for cmd in ('echo a', 'echo b', 'echo a'):
            hm.add_to_history(cmd)
        assert shell.state.history is hist
        assert shell.state.history == ['echo b', 'echo a']

    def test_histsize_trim_preserves_identity(self, shell):
        hist = shell.state.history
        shell.state.max_history_size = 3
        hm = shell.interactive_manager.history_manager
        for i in range(6):
            hm.add_to_history(f'echo {i}')
        assert shell.state.history is hist
        assert shell.state.history == ['echo 3', 'echo 4', 'echo 5']

    def test_load_from_file_trim_preserves_identity(self, shell, tmp_path):
        histfile = tmp_path / 'psh_history'
        histfile.write_text(''.join(f'echo {i}\n' for i in range(10)))
        shell.state.history_file = str(histfile)
        shell.state.max_history_size = 4
        hist = shell.state.history
        shell.interactive_manager.history_manager.load_from_file()
        assert shell.state.history is hist
        assert shell.state.history == [f'echo {i}' for i in range(6, 10)]

    def test_clear_history_preserves_identity(self, shell):
        hist = shell.state.history
        hm = shell.interactive_manager.history_manager
        hm.add_to_history('echo a')
        hm.clear_history()
        assert shell.state.history is hist
        assert shell.state.history == []

    def test_editor_over_empty_history_survives_every_operation(self, shell):
        """End to end: an editor built over an initially-EMPTY
        state.history still sees the latest entry after appends,
        erasedups and the HISTSIZE trim have all run."""
        assert shell.state.history == []
        editor = LineEditor(history=shell.state.history)
        shell.state.set_variable('HISTCONTROL', 'erasedups')
        shell.state.max_history_size = 3
        hm = shell.interactive_manager.history_manager
        for cmd in ('echo a', 'echo b', 'echo a', 'echo c', 'echo d'):
            hm.add_to_history(cmd)
        assert editor.history is shell.state.history
        editor.history_nav.reset()
        assert editor.history_nav.up('') == 'echo d'
