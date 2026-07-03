"""Unit tests for HistoryNavigator and HistorySearch (history_nav.py).

Both classes are pure against an injected history list — no tty, no
renderer, no editor — so these tests exercise them directly. The editor
applies the returned text / SearchState via EditBuffer + LineRenderer.
The reverse-search behaviors pinned here match readline/bash 5.2:
refining a pattern re-searches from the current entry INCLUSIVE (a still-
matching entry is kept), while an explicit Ctrl-R/Ctrl-S steps off it
(reappraisal #16 H8b).
"""

from psh.interactive.history_nav import HistoryNavigator, HistorySearch


class TestHistoryNavigator:
    def test_up_from_bottom_returns_newest_and_stashes_original(self):
        nav = HistoryNavigator(['first', 'second'])
        assert nav.up('typed but not run') == 'second'
        assert nav.pos == 1
        assert nav.original_line == 'typed but not run'

    def test_up_at_oldest_returns_none(self):
        nav = HistoryNavigator(['only'])
        assert nav.up('') == 'only'
        assert nav.up('') is None
        assert nav.pos == 0

    def test_down_at_bottom_returns_none(self):
        nav = HistoryNavigator(['x'])
        assert nav.down() is None
        assert nav.pos == 1

    def test_up_up_down_down_restores_original_line(self):
        nav = HistoryNavigator(['first', 'second'])
        nav.up('wip')
        nav.up('not stashed again')   # original_line stashed only at bottom
        assert nav.down() == 'second'
        assert nav.down() == 'wip'
        assert nav.pos == 2

    def test_up_joins_multiline_entry_to_single_line(self):
        nav = HistoryNavigator(['for i in a b\ndo\n  echo $i\ndone'])
        text = nav.up('')
        assert text is not None and '\n' not in text
        assert 'for i in a b; do' in text
        assert '; done' in text

    def test_down_joins_multiline_entry_to_single_line(self):
        nav = HistoryNavigator(['echo one', 'if true\nthen\n  echo y\nfi'])
        nav.pos = 0
        text = nav.down()
        assert text is not None and 'if true; then' in text

    def test_first_jumps_to_oldest_and_stashes_original(self):
        nav = HistoryNavigator(['a', 'b', 'c'])
        assert nav.first('wip') == 'a'
        assert nav.pos == 0
        assert nav.original_line == 'wip'

    def test_first_returns_raw_entry_without_multiline_join(self):
        # Pinned quirk: unlike up/down, Meta-< shows the entry verbatim.
        entry = 'echo a\necho b'
        nav = HistoryNavigator([entry])
        assert nav.first('') == entry

    def test_first_with_empty_history_returns_none(self):
        nav = HistoryNavigator([])
        assert nav.first('wip') is None
        assert nav.original_line == ''

    def test_last_restores_original_and_reanchors_at_bottom(self):
        nav = HistoryNavigator(['a', 'b'])
        nav.up('wip')
        assert nav.last() == 'wip'
        assert nav.pos == 2
        assert nav.last() is None     # already at the bottom

    def test_reset_reanchors_after_injected_list_grows(self):
        history = ['a']
        nav = HistoryNavigator(history)
        history.append('b')           # aliases shell state: grows in place
        nav.reset()
        assert nav.pos == 2
        assert nav.up('') == 'b'


class TestHistorySearch:
    HISTORY = ['echo findme_16', 'echo other_3']

    def search(self, history=None, pos=None, original=''):
        history = self.HISTORY if history is None else history
        pos = len(history) if pos is None else pos
        return HistorySearch(history, pos, original)

    def test_start_state_is_empty_backward_prompt(self):
        s = self.search()
        state = s.start()
        assert state.status == 'active'
        assert state.prompt == "(bck-i-search)`': "
        assert state.line is None     # at the bottom: buffer untouched
        assert state.repaint

    def test_first_char_finds_most_recent_match(self):
        s = self.search()
        state = s.feed('f')
        assert state.status == 'active'
        assert state.prompt == "(bck-i-search)`f': "
        assert state.line == 'echo findme_16'
        assert state.cursor == len('echo f')   # just past the match
        assert state.history_pos == 0

    def test_pattern_extension_keeps_match_displayed(self):
        s = self.search()
        for ch in 'findme':
            state = s.feed(ch)
        # Every character re-searches from the current entry INCLUSIVE, so
        # extending the pattern while the entry still matches keeps us on
        # it with a non-failed prompt (readline/bash).
        assert state.status == 'active'
        assert state.prompt == "(bck-i-search)`findme': "
        assert state.line == 'echo findme_16'
        assert state.cursor == len('echo findme')
        assert state.history_pos == 0

    def test_no_match_shows_failed_prompt_and_restores_position(self):
        s = self.search()
        state = s.feed('z')
        assert state.status == 'active'
        assert state.prompt == "(failed-bck-i-search)`z': "
        assert state.history_pos == len(self.HISTORY)
        assert state.line is None

    def test_narrowing_rechecks_current_entry_inclusive(self):
        # reappraisal #16 H8b: re-search is INCLUSIVE of the current
        # position, so extending the pattern while sitting on a match that
        # still matches keeps us on it with a non-failed prompt (bash).
        s = self.search(['echo match'])
        s.feed('m')
        state = s.feed('a')
        assert state.prompt == "(bck-i-search)`ma': "
        assert state.line == 'echo match'
        assert state.history_pos == 0

    def test_extension_stays_on_current_match_h8b(self):
        # reappraisal #16 H8b: refining a pattern that STILL matches the
        # entry we are on must keep us there, not jump to an older match.
        # older 'echo foo bar' (0), newer 'echo foo baz' (1).
        s = self.search(['echo foo bar', 'echo foo baz'])
        for ch in 'foo':
            state = s.feed(ch)
        assert state.line == 'echo foo baz'   # newest match, not the older
        assert state.history_pos == 1
        assert state.prompt == "(bck-i-search)`foo': "

    def test_ctrl_r_steps_off_current_match_to_older(self):
        # An explicit Ctrl-R moves off the current entry (even though it
        # still matches) to the next older match; a further Ctrl-R past
        # the last match shows the failed- prompt.
        s = self.search(['echo foo bar', 'echo foo baz'])
        for ch in 'foo':
            s.feed(ch)                # on 'echo foo baz' (pos 1)
        state = s.feed('\x12')        # Ctrl-R: step to the older match
        assert state.line == 'echo foo bar'
        assert state.history_pos == 0
        state = s.feed('\x12')        # Ctrl-R: no more matches
        assert state.prompt == "(failed-bck-i-search)`foo': "
        assert state.history_pos == 0

    def test_repeated_ctrl_r_moves_to_earlier_match(self):
        s = self.search(['echo x a', 'other', 'echo x b'])
        state = s.feed('x')
        assert state.history_pos == 2
        state = s.feed('\x12')        # Ctrl-R: next match backward
        assert state.history_pos == 0
        assert state.line == 'echo x a'

    def test_ctrl_r_past_oldest_match_shows_failed(self):
        # Stepping past the oldest match repaints the failed- prompt and
        # stays on the last match (bash beeps + shows failed-reverse).
        s = self.search(['echo x'])
        s.feed('x')                   # match at 0
        state = s.feed('\x12')        # step past the oldest entry
        assert state.status == 'active'
        assert state.repaint
        assert state.prompt == "(failed-bck-i-search)`x': "
        assert state.history_pos == 0

    def test_ctrl_s_switches_to_forward_prompt(self):
        s = self.search(['a echo', 'b echo'], pos=0)
        state = s.feed('\x13')        # Ctrl-S: search forward
        assert state.status == 'active'
        assert state.prompt.startswith('(fwd-i-search)') or \
            state.prompt.startswith('(failed-fwd-i-search)')
        assert state.history_pos == 1

    def test_ctrl_g_aborts_restoring_position_and_original_line(self):
        s = self.search(original='half-typed')
        s.feed('f')                   # moves to the match
        state = s.feed('\x07')        # Ctrl-G
        assert state.status == 'aborted'
        assert state.line == 'half-typed'
        assert state.cursor == len('half-typed')
        assert state.history_pos == len(self.HISTORY)
        assert state.prompt is None   # back to the normal prompt

    def test_enter_accepts_current_match_without_executing(self):
        # Accept puts the match in the buffer; a second Enter (outside
        # the machine) executes it — pinned by the PTY ctrl-r test.
        s = self.search()
        s.feed('f')
        state = s.feed('\r')
        assert state.status == 'accepted'
        assert state.line == 'echo findme_16'
        assert not state.redispatch

    def test_accept_at_bottom_keeps_buffer(self):
        s = self.search()
        state = s.feed('\n')          # Enter before any match landed
        assert state.status == 'accepted'
        assert state.line is None     # buffer (the typed text) is kept

    def test_backspace_shortens_pattern_and_researches(self):
        s = self.search(['echo a', 'echo b'])
        s.feed('e')                   # matches 'echo b' (pos 1)
        s.feed('z')                   # 'ez': failed, still at pos 1
        state = s.feed('\x7f')        # back to 'e': inclusive re-search
        # 'echo b' still matches 'e', so shortening keeps us on it (bash
        # keeps the current entry on a pattern change).
        assert state.prompt == "(bck-i-search)`e': "
        assert state.line == 'echo b'
        assert state.history_pos == 1

    def test_backspace_on_empty_pattern_does_not_repaint(self):
        s = self.search()
        state = s.feed('\x7f')
        assert state.status == 'active'
        assert not state.repaint

    def test_other_control_char_accepts_and_redispatches(self):
        s = self.search()
        s.feed('f')
        state = s.feed('\x01')        # Ctrl-A: accept, then act normally
        assert state.status == 'accepted'
        assert state.redispatch
        assert state.line == 'echo findme_16'
