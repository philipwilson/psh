"""HISTCONTROL / HISTIGNORE filtering in HistoryManager (reappraisal #14 H7).

Previously psh had no HISTCONTROL/HISTIGNORE support and unconditionally
dropped a command equal to the immediately previous one. bash records EVERY
line by default (no dedup) and only filters when HISTCONTROL/HISTIGNORE ask.
These drive add_to_history directly (history is interactive-only); semantics
pinned to bash 5.2's documented behavior.
"""


from psh.shell import Shell


def _hist(histcontrol=None, histignore=None, commands=()):
    shell = Shell(norc=True)
    if histcontrol is not None:
        shell.state.set_variable('HISTCONTROL', histcontrol)
    if histignore is not None:
        shell.state.set_variable('HISTIGNORE', histignore)
    shell.state.history = []
    hm = shell.interactive_manager.history_manager
    hm._file_synced_len = 0
    for c in commands:
        hm.add_to_history(c)
    return shell.state.history


def test_default_records_consecutive_duplicates():
    # bash default: no dedup — both `echo a` kept.
    assert _hist(commands=["echo a", "echo a", "echo b"]) == ["echo a", "echo a", "echo b"]


def test_ignoredups_drops_consecutive_only():
    assert _hist("ignoredups", commands=["echo a", "echo a", "echo b", "echo a"]) == \
        ["echo a", "echo b", "echo a"]


def test_ignorespace_drops_leading_space():
    assert _hist("ignorespace", commands=["keep", " secret", "keep2"]) == ["keep", "keep2"]


def test_ignoreboth_is_space_plus_dups():
    assert _hist("ignoreboth", commands=["echo a", " sp", "echo a", "echo a"]) == ["echo a"]


def test_erasedups_removes_all_prior_copies():
    assert _hist("erasedups", commands=["echo a", "echo b", "echo a", "echo c"]) == \
        ["echo b", "echo a", "echo c"]


def test_histignore_glob_patterns():
    assert _hist(histignore="ls:history*", commands=["keep", "ls", "history 5", "keep2"]) == \
        ["keep", "keep2"]


def test_histignore_exact_and_question_mark():
    assert _hist(histignore="??", commands=["ab", "abc", "xy"]) == ["abc"]


def test_histignore_ampersand_matches_previous():
    # `&` matches the immediately previous history line.
    assert _hist(histignore="&", commands=["echo a", "echo a", "echo b", "echo b"]) == \
        ["echo a", "echo b"]


def test_unknown_histcontrol_value_is_ignored():
    # An unrecognized token has no effect: dups are kept (bash).
    assert _hist("bogusvalue", commands=["x", "x"]) == ["x", "x"]


def test_histcontrol_unset_keeps_everything():
    assert _hist(commands=["a", "a", "a"]) == ["a", "a", "a"]
