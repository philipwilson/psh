"""Unit tests for history WORD designators (!$, !^, !*, !!:n, ...).

These exercise ``HistoryExpander.expand_history`` directly with a fixed
history list and ``histexpand`` forced on, independent of the interactive
gating (history expansion is interactive-only at the integration level,
matching bash, which also disables histexpand non-interactively).

The expected values are pinned to bash's interactive behavior (verified with
``bash --norc -i``): word 0 is the command, words are 1-indexed arguments,
``$`` is the last word, ``*`` is words 1..last, and quoting is respected when
splitting the stored history line into words.
"""

import pytest

from psh.shell import Shell


@pytest.fixture
def expander():
    """A HistoryExpander on a shell with histexpand on and a fixed history."""
    shell = Shell()
    shell.state.options['histexpand'] = True
    return shell.history_expander


def _expand(expander, history, command):
    """The expanded text, or None on an ERROR outcome (the historical contract
    these designator assertions were written against; campaign I4 retyped the
    producer to a HistoryExpansionResult)."""
    expander.state.history[:] = list(history)
    r = expander.expand_history(command)
    return None if r.is_error else r.text


# Single history entry: "echo alpha beta gamma" (word0=echo, args alpha/beta/gamma)
ABG = ['echo alpha beta gamma']


@pytest.mark.parametrize("expr,expected", [
    ('!!', 'echo alpha beta gamma'),
    ('!!:0', 'echo'),
    ('!!:1', 'alpha'),
    ('!!:2', 'beta'),
    ('!!:3', 'gamma'),
    ('!!:$', 'gamma'),
    ('!!:^', 'alpha'),
    ('!!:*', 'alpha beta gamma'),
    ('!!:1-2', 'alpha beta'),
    ('!!:2-', 'beta'),       # word 2 .. second-to-last
    ('!!:2*', 'beta gamma'),  # word 2 .. last
    ('!!:1-$', 'alpha beta gamma'),
    # Bare-sigil shorthands default to the previous command (!!).
    ('!$', 'gamma'),
    ('!^', 'alpha'),
    ('!*', 'alpha beta gamma'),
    # !:n shorthand (event ! + numeric designator) also defaults to !!.
    ('!:0', 'echo'),
    ('!:1', 'alpha'),
    ('!:$', 'gamma'),
])
def test_word_designators_on_previous_command(expander, expr, expected):
    assert _expand(expander, ABG, expr) == expected


@pytest.mark.parametrize("expr,expected", [
    # The `:-n` (== `:0-n`) abbreviation: words 0 through n (bash). M9.
    ('!!:-0', 'echo'),
    ('!!:-1', 'echo alpha'),
    ('!!:-2', 'echo alpha beta'),
    ('!!:-3', 'echo alpha beta gamma'),
    ('!!:-$', 'echo alpha beta gamma'),
])
def test_leading_dash_range_is_word_zero_through_n(expander, expr, expected):
    """Regression (M9): `!!:-n` must expand to words 0..n, not abort with a
    'bad word specifier'. Verified against bash `history -p`."""
    assert _expand(expander, ABG, expr) == expected


def test_designator_garbage_suffix_fixed(expander):
    """Regression: !!:1 must select word 1, not leave ':1' as literal garbage."""
    # Before the fix this produced 'echo alpha beta gamma:1'.
    assert _expand(expander, ABG, '!!:1') == 'alpha'


def test_documented_user_guide_example(expander):
    """The user guide documents `!$` = last argument of the previous command."""
    assert _expand(expander, ['ls /some/long/path'], '!$') == '/some/long/path'


def test_designators_embedded_in_command(expander):
    assert _expand(expander, ABG, 'echo !$') == 'echo gamma'
    assert _expand(expander, ['true'], 'echo X!$Y') == 'echo XtrueY'


@pytest.mark.parametrize("expr,expected", [
    ('!1:$', 'three'),
    ('!1:^', 'one'),
    ('!1:2', 'two'),
    ('!echo:^', 'aaa'),   # most recent "echo..." is the 2nd entry
    ('!-2:2', 'two'),     # 2 commands back = entry 1
    ('!-1:$', 'bbb'),
])
def test_word_designators_on_explicit_events(expander, expr, expected):
    history = ['echo one two three', 'echo aaa bbb']
    assert _expand(expander, history, expr) == expected


def test_star_with_no_arguments_is_empty(expander):
    """!* (all args) expands to empty (not an error) when there are no args."""
    assert _expand(expander, ['true'], 'echo pre !* post') == 'echo pre  post'


def test_dollar_on_argless_command_is_command_word(expander):
    """!$ of a command with only word 0 yields that word (bash: no error)."""
    assert _expand(expander, ['true'], 'echo !$') == 'echo true'


def test_quoting_respected_in_word_split(expander):
    """A quoted span is one word; the quote chars stay part of the word."""
    history = ["echo 'quoted arg' last"]
    assert _expand(expander, history, 'echo !:1') == "echo 'quoted arg'"
    assert _expand(expander, history, 'echo !:2') == 'echo last'
    assert _expand(expander, history, 'echo !$') == 'echo last'


@pytest.mark.parametrize("expr", [
    'echo !!:5',     # word index out of range
    'echo !!:1-9',   # range end out of range
    'echo !!:2-1',   # reversed range
    'echo !^',       # !^ on an argless command (no word 1)
])
def test_bad_word_specifier_returns_none(expander, expr):
    # report_errors=False, but a bad word specifier still aborts (None).
    assert _expand(expander, ['true'], expr) is None


@pytest.mark.parametrize("text", [
    'a!=b',
    '[[ ! x ]]',
    'echo hi!',
    "echo '!$'",     # single-quoted: no expansion
])
def test_non_references_left_literal(expander, text):
    assert _expand(expander, ABG, text) == text


def test_event_not_found_returns_none(expander):
    assert _expand(expander, [], '!!') is None
    assert _expand(expander, ABG, '!nonexistent') is None
