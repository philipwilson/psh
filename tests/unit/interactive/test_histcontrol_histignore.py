"""HISTCONTROL / HISTIGNORE filtering through the REAL entry path.

bash 5.2 (the oracle; probe battery in reappraisal #17 H7) stores each
history line VERBATIM — leading spaces/tabs and trailing whitespace are
preserved — and every HISTCONTROL/HISTIGNORE decision looks at that raw
text: ``ignorespace`` fires only on a literal leading SPACE (a leading tab
does not trigger it), ``ignoredups`` compares verbatim, and HISTIGNORE
patterns must match the verbatim line (``HISTIGNORE=ls`` does NOT drop
`` ls``).

These tests drive ``shell.run_command`` — the full source-processor path —
NOT ``HistoryManager.add_to_history`` directly. The previous version of
this file drove the leaf method and was a false positive (reappraisal #17
H7): the source processor ``.strip()``ped the command before the leaf's
leading-space check, so HISTCONTROL=ignorespace silently never fired in
real use (a privacy leak) while these tests stayed green. Recording
happens before parsing/execution, so lines that fail to run (e.g. unknown
commands) are still legitimate history fixtures, like bash.
"""

import os

from psh.shell import Shell


def _shell(histcontrol=None, histignore=None):
    shell = Shell(norc=True)
    if histcontrol is not None:
        shell.state.set_variable('HISTCONTROL', histcontrol)
    if histignore is not None:
        shell.state.set_variable('HISTIGNORE', histignore)
    # In-place reset only — the line editor aliases this list (alias
    # contract, see HistoryManager docstring).
    shell.interactive_manager.history_manager.clear_history()
    return shell


def _hist(histcontrol=None, histignore=None, commands=()):
    shell = _shell(histcontrol, histignore)
    for c in commands:
        shell.run_command(c)
    return shell.state.history


# --- HISTCONTROL semantics (all through run_command) ---

def test_default_records_consecutive_duplicates():
    # bash default: no dedup — both `echo a` kept.
    assert _hist(commands=["echo a", "echo a", "echo b"]) == ["echo a", "echo a", "echo b"]


def test_ignoredups_drops_consecutive_only():
    assert _hist("ignoredups", commands=["echo a", "echo a", "echo b", "echo a"]) == \
        ["echo a", "echo b", "echo a"]


def test_ignorespace_drops_leading_space():
    # THE reappraisal #17 H7 regression pin: ` secret` typed with a leading
    # space must NOT be recorded (privacy feature). Fails on the pre-fix
    # code, which stripped the command before the ignorespace check.
    assert _hist("ignorespace", commands=["echo keep", " echo secret", "echo keep2"]) == \
        ["echo keep", "echo keep2"]


def test_ignorespace_multiple_leading_spaces_drop():
    assert _hist("ignorespace", commands=["  echo secret2", "echo keep"]) == ["echo keep"]


def test_ignorespace_does_not_fire_on_leading_tab():
    # bash: only a literal leading space triggers ignorespace; a tab-led
    # line is recorded VERBATIM (tab included). Space-then-tab drops.
    assert _hist("ignorespace",
                 commands=["\techo tab", "\t echo tabspace", " \techo spacetab"]) == \
        ["\techo tab", "\t echo tabspace"]


def test_ignoreboth_is_space_plus_dups():
    assert _hist("ignoreboth", commands=["echo a", " echo sp", "echo a", "echo a"]) == ["echo a"]


def test_erasedups_removes_all_prior_copies():
    assert _hist("erasedups", commands=["echo a", "echo b", "echo a", "echo c"]) == \
        ["echo b", "echo a", "echo c"]


def test_ignoredups_compares_verbatim():
    # ` echo a` (leading space, ignorespace off) differs from `echo a` —
    # both kept; the repeat of ` echo a` is the only drop (bash).
    assert _hist("ignoredups", commands=["echo a", " echo a", " echo a", "echo a"]) == \
        ["echo a", " echo a", "echo a"]


# --- verbatim storage (HISTCONTROL unset) ---

def test_stores_lines_verbatim_including_whitespace():
    # bash stores the raw line: leading spaces, leading tab, trailing
    # spaces all preserved when no filter drops the line.
    cmds = ["echo plain", " echo lead1", "  echo lead2", "\techo tab", "echo trail   "]
    assert _hist(commands=cmds) == cmds


def test_whitespace_only_command_not_recorded():
    # Deliberate psh divergence: bash records a whitespace-only line;
    # psh's empty-command guard skips it (nothing useful to recall).
    assert _hist(commands=["   ", "echo real"]) == ["echo real"]


# --- HISTIGNORE on the verbatim line ---

def test_histignore_glob_patterns():
    assert _hist(histignore="true:history*",
                 commands=["echo keep", "true", "history 5", "echo keep2"]) == \
        ["echo keep", "echo keep2"]


def test_histignore_exact_and_question_mark():
    assert _hist(histignore="??", commands=["ab", "abc", "xy"]) == ["abc"]


def test_histignore_matches_verbatim_line():
    # bash matches HISTIGNORE against the raw line: ` true` (leading
    # space) does NOT match the pattern `true`, so it is kept.
    assert _hist(histignore="true", commands=["true", " true", "truex"]) == \
        [" true", "truex"]


def test_histignore_plus_ignorespace():
    # ignorespace drops ` true` first; HISTIGNORE drops `true`.
    assert _hist("ignorespace", histignore="true",
                 commands=["true", " true", "truex"]) == ["truex"]


def test_histignore_ampersand_matches_previous():
    # `&` matches the immediately previous history line.
    assert _hist(histignore="&", commands=["echo a", "echo a", "echo b", "echo b"]) == \
        ["echo a", "echo b"]


def test_unknown_histcontrol_value_is_ignored():
    # An unrecognized token has no effect: dups are kept (bash).
    assert _hist("bogusvalue", commands=["echo x", "echo x"]) == ["echo x", "echo x"]


def test_histcontrol_unset_keeps_everything():
    assert _hist(commands=["echo a", "echo a", "echo a"]) == ["echo a", "echo a", "echo a"]


# --- multi-line commands (cmdhist join happens AFTER the filters) ---

def test_multiline_leading_space_preserved_in_joined_entry():
    # bash joins ` if true` / `then echo x` / `fi` into one entry that
    # keeps the first line's leading space verbatim.
    assert _hist(commands=[" if true\nthen echo x\nfi"]) == \
        [" if true; then echo x; fi"]


def test_multiline_ignorespace_drops_whole_compound():
    # With ignorespace, a leading space on the FIRST line drops the whole
    # logical command (bash records none of its lines).
    assert _hist("ignorespace", commands=[" if true\nthen echo x\nfi", "echo after"]) == \
        ["echo after"]


def test_multiline_no_leading_space_still_recorded_under_ignorespace():
    assert _hist("ignorespace", commands=["if true\nthen echo x\nfi"]) == \
        ["if true; then echo x; fi"]


# --- HISTFILE round trip: what is stored is what persists ---

def test_histfile_roundtrip_preserves_verbatim_whitespace(tmp_path):
    shell = _shell()
    for c in ["echo plain", " echo lead", "\techo tab", "echo trail  "]:
        shell.run_command(c)
    shell.state.history_file = str(tmp_path / "psh_history")
    shell.interactive_manager.history_manager.save_to_file()
    with open(shell.state.history_file) as f:
        stored = f.read().split("\n")
    assert stored == ["echo plain", " echo lead", "\techo tab", "echo trail  ", ""]


def test_histfile_roundtrip_ignorespace_never_persists_secret(tmp_path):
    shell = _shell("ignorespace")
    shell.run_command("echo keep")
    shell.run_command(" echo secret")
    shell.state.history_file = str(tmp_path / "psh_history")
    shell.interactive_manager.history_manager.save_to_file()
    with open(shell.state.history_file) as f:
        content = f.read()
    assert "secret" not in content
    assert content == "echo keep\n"
    assert os.path.exists(shell.state.history_file)


# --- HISTIGNORE routes through the ONE pattern engine (campaign W3) ---
# bash 5.2 truth (live interactive probe, archived:
# tmp/boundary-ledgers/W3-probes/namefilter-probe.txt): HISTIGNORE patterns
# honor extglob groups ONLY when `shopt -s extglob` is set (bash compiles them
# with FNM_EXTMATCH conditionally), and backslash escapes a metacharacter.
# The former stdlib-fnmatch path did neither.

def test_histignore_extglob_group_honored_when_extglob_on():
    # RED on base (fnmatch: '@(ls|pwd)' matches neither line -> both kept).
    shell = _shell(histignore="@(ls|pwd)")
    shell.state.options['extglob'] = True
    for c in ["ls", "pwd", "echo keep"]:
        shell.run_command(c)
    assert shell.state.history == ["echo keep"]


def test_histignore_extglob_group_literal_when_extglob_off():
    # extglob OFF (default): '@(ls|pwd)' does not act as a group, so the
    # lines are recorded (parity with the old fnmatch path AND with bash).
    assert _hist(histignore="@(ls|pwd)",
                 commands=["ls", "pwd", "echo keep"]) == \
        ["ls", "pwd", "echo keep"]


def test_histignore_backslash_escapes_metacharacter():
    # RED on base: with HISTIGNORE='a\*b' the engine treats '\*' as an
    # ESCAPED (literal) star, so the literal line 'a*b' is dropped and
    # 'aXb' is kept; stdlib fnmatch read '\' as an ordinary character and
    # kept both. (bash: backslash escapes in HISTIGNORE patterns.)
    assert _hist(histignore=r"a\*b", commands=["a*b", "aXb", "echo keep"]) == \
        ["aXb", "echo keep"]


def test_histignore_unescaped_star_still_wildcards():
    # Control row: an unescaped '*' is a live wildcard (both lines dropped).
    assert _hist(histignore="a*b", commands=["a*b", "aXb", "echo keep"]) == \
        ["echo keep"]
