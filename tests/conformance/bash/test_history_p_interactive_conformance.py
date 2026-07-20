"""Interactive `history -p` / `-s` recording+removal conformance (CV3).

In the INTERACTIVE family, bash records the invoking line BEFORE the builtin
runs, then `history -p`/`-s` WITH OPERANDS strip their OWN just-recorded
invocation from the in-memory history — so a `!!` operand refers to the command
BEFORE the `history` call, and the invocation does not linger. psh recorded the
invocation and never removed it (so `history -p '!!'` printed itself and stayed
in `history`), fixed in v0.750.0.

These rows drive a REAL interactive shell (`-i` with piped stdin, which records
history in both shells) against live bash 5.2, each with an isolated HISTFILE
(psh run first — the banked-histfile gotcha). The non-interactive
`history -p` engine coverage stays in test_history_expansion_conformance.py.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from shell_oracle import resolve_bash

# Strip the argv0/location prefix a diagnostic line may carry.
_PREFIX_RE = re.compile(r'^[^:\n]*: (line \d+: )?', re.MULTILINE)
_PATH = os.environ.get('PATH', '/usr/bin:/bin')


def _run_i(argv, rc_flags, lines):
    with tempfile.NamedTemporaryFile(prefix='cv3hist', delete=True) as tf:
        histfile = tf.name  # a fresh, empty path — no banked history
    script = ''.join(line + '\n' for line in lines)
    # Isolated HOME + rc-skip flags so the ORACLE (bash) never sources the
    # user's real ~/.bashrc / ~/.bash_profile (HISTCONTROL, aliases, prompts
    # would make it a fragile oracle) — the harness controls the whole
    # environment (CV3 nit-6).
    with tempfile.TemporaryDirectory(prefix='cv3home') as home:
        r = subprocess.run(
            argv + rc_flags + ['-i'], input=script, capture_output=True,
            text=True, timeout=20,
            env={'HISTFILE': histfile, 'PATH': _PATH, 'TERM': 'dumb',
                 'HOME': home})
    Path(histfile).unlink(missing_ok=True)
    return _PREFIX_RE.sub('', r.stdout)


def _assert_same_interactive(lines):
    # psh FIRST (banked-histfile gotcha). Both skip rc files (bash also
    # --noprofile; psh has no profile files).
    psh = _run_i([sys.executable, '-m', 'psh'], ['--norc'], lines)
    bash = _run_i([resolve_bash().path], ['--norc', '--noprofile'], lines)
    assert psh == bash, f"psh {psh!r} != bash {bash!r}\nlines: {lines}"


class TestHistoryPInteractiveRemoval:
    def test_basic_p_expands_prev_and_removes_invocation(self):
        # bash prints `echo seed` (the prior command), and `history` does NOT
        # list the `history -p '!!'` invocation. RED ON BASE.
        _assert_same_interactive(['echo seed', "history -p '!!'", 'history'])

    def test_p_no_operands_retains_invocation(self):
        _assert_same_interactive(['echo seed', 'history -p', 'history'])

    def test_p_error_arg_still_removes_invocation(self):
        _assert_same_interactive(['echo seed', "history -p '!nope'", 'history'])

    def test_p_multi_operand(self):
        _assert_same_interactive(
            ['echo seed', "history -p '!!' abc '!!'", 'history'])

    def test_p_set_plus_H_still_force_expands_and_removes(self):
        _assert_same_interactive(
            ['echo seed', 'set +H', "history -p '!!'", 'history'])

    def test_p_twice_each_removes_its_own(self):
        _assert_same_interactive(
            ['echo one', "history -p '!!'", "history -p '!!'", 'history'])

    def test_p_literal_operand_removes_invocation(self):
        _assert_same_interactive(['echo seed', 'history -p hello', 'history'])

    def test_p_ignorespace_no_misfire(self):
        # The `history -p` line has a LEADING SPACE (HISTCONTROL=ignorespace ->
        # not recorded), so nothing is stripped and no prior entry is lost.
        _assert_same_interactive(
            ['echo seed', 'echo second', 'HISTCONTROL=ignorespace',
             " history -p '!!'", 'history'])


class TestHistorySInteractiveReplace:
    def test_s_with_args_replaces_invocation(self):
        # bash: `history -s stored cmd` replaces its own invocation with the
        # joined args. RED ON BASE (psh kept both).
        _assert_same_interactive(
            ['echo seed', 'history -s stored cmd', 'history'])

    def test_s_no_args_retains_invocation(self):
        _assert_same_interactive(['echo seed', 'history -s', 'history'])


class TestHistoryLineScopedStripB4:
    """CV3 B4: bash's history strip is a LINE-SCOPED PERSISTENT flag, not a
    single-shot verified marker. While a recorded line's flag is set, EACH
    `history -p <args>` on the line deletes the LAST (unverified) entry and KEEPS
    the flag; the FIRST `history -s <args>` deletes and CONSUMES it. So multiple
    invocations on one line delete THROUGH earlier entries. Divergent on base
    AND at the prior fix tip (the identity-verified single-shot model kept the
    prior entry) — RED ON BASE. bash 5.2-verified (-i piped)."""

    def test_two_p_one_line_deletes_through(self):
        _assert_same_interactive(
            ['echo seed', 'history -p a; history -p b', 'history'])

    def test_three_p_one_line_deletes_through(self):
        _assert_same_interactive(
            ['echo one', 'echo two',
             'history -p a; history -p b; history -p c', 'history'])

    def test_p_then_s_one_line(self):
        _assert_same_interactive(
            ['echo seed', "history -p '!!'; history -s BBB", 'history'])

    def test_s_consumes_flag_blocks_later_p(self):
        _assert_same_interactive(
            ['echo seed', 'history -s XXX; history -p a', 'history'])

    def test_p_midline_command_then_p_deletes_through(self):
        # `echo mid` mid-line does NOT record a new entry, so the second -p
        # deletes through `echo seed`.
        _assert_same_interactive(
            ['echo seed', 'history -p a; echo mid; history -p b', 'history'])

    def test_p_no_operands_one_line_retains(self):
        _assert_same_interactive(
            ['echo seed', 'history -p; history -p', 'history'])

    def test_eval_inherits_line_flag(self):
        _assert_same_interactive(
            ['echo seed', 'eval "history -p \'!!\'"', 'history'])

    def test_eval_on_line_after_p(self):
        _assert_same_interactive(
            ['echo seed', 'history -p a; eval "history -p b"', 'history'])


class TestHistoryStripCmdsubInheritanceB5:
    """CV3 B5: the line strip flag INHERITS across a subshell fork, so a
    `history -p` inside `$(...)` on a recorded line strips the invocation (its
    `!!` then refers to the command BEFORE the line). A `history -s` inside
    `$(...)` does not affect the parent history (its store/delete are on the
    discarded child copy) — kept-green. RED ON BASE (the clone reset the flag).
    """

    def test_cmdsub_p_inherits_and_strips(self):
        # bash prints 'got echo seed' (the -p inside $() saw the pre-line state).
        _assert_same_interactive(
            ['echo seed', "echo got $(history -p '!!')", 'history'])

    def test_cmdsub_s_does_not_affect_parent(self):
        _assert_same_interactive(
            ['echo seed', 'echo got $(history -s ZZZ)', 'history'])


class TestHistoryStripPhysicalLineR4:
    r"""CV3 R4: bash's `history -p` unverified delete fires ONLY when the
    invoking LOGICAL line was read as ONE physical line — a `\`-continued /
    multi-line command KEEPS its invocation. `history -s`'s delete has NO such
    restriction. The prior fix deleted on any recorded line (destructive on a
    continuation with multiple `-p`). RED at the fix tip. bash 5.2-verified."""

    def test_p_on_continuation_line_keeps_invocation(self):
        # `history -p \<nl>'!!'` spans 2 physical lines -> no delete; !! then
        # refers to the invocation itself (kept), matching bash.
        _assert_same_interactive(
            ['echo seed', "history -p \\", "'!!'", 'history'])

    def test_s_on_continuation_line_still_replaces(self):
        _assert_same_interactive(
            ['echo seed', 'history -s XXX \\', 'YYY', 'history'])

    def test_p_multi_then_history_keeps(self):
        _assert_same_interactive(
            ['echo one', 'echo two', 'history -p a \\', 'b', 'history'])

    def test_p_destructive_double_delete_on_continuation(self):
        # Two -p on a continuation line: the prior tip deleted THROUGH echo seed;
        # bash keeps everything (multi-physical -> no delete).
        _assert_same_interactive(
            ['echo seed', 'history -p a; history -p b \\', 'c', 'history'])


class TestHistoryStripDeleteFailureM3:
    r"""CV3 M3: when the strip is DUE but the history is EMPTY at that point
    (`history -c` cleared it earlier on the same line), the delete fails —
    bash's `-p` prints NOTHING and returns 1 (no operand expanded), and `-s`
    stores NOTHING and does NOT consume the flag. bash 5.2-verified."""

    def test_p_delete_failure_prints_nothing_rc1(self):
        _assert_same_interactive(
            ['echo seed', "history -c; history -p '!!'; echo rc=$?", 'history'])

    def test_s_delete_failure_stores_nothing(self):
        _assert_same_interactive(
            ['echo seed', 'history -c; history -s XXX; history'])

    def test_p_literal_delete_failure_prints_nothing(self):
        _assert_same_interactive(
            ['echo seed', 'history -c; history -p a; history'])


class TestHistorySInStringContextH1:
    r"""CV3 H1: `history -s`'s DELETE is gated on a RECORDING context — bash
    NEVER strips inside eval/source/`-c` string contexts (parse_and_execute
    clears remember_on_history), though its store still CONSUMES the line flag.
    `history -p` has NO such gate (a sourced/eval'd `-p` still strips). The
    round-1 flag inheritance made `-s` delete inside eval/source — data loss.
    RED at the fix tip. bash 5.2-verified."""

    def test_eval_s_does_not_delete_but_stores(self):
        # bash keeps the `eval "history -s SNEW"` invocation AND stores SNEW.
        _assert_same_interactive(
            ['echo seed', 'eval "history -s SNEW"', 'history'])

    def test_source_s_does_not_delete_user_entry(self):
        # The destructive row: a sourced `-s` must not delete a real entry.
        _assert_same_interactive(
            ['echo one', 'echo two',
             "source /dev/stdin <<< 'history -s SNEW'", 'history'])

    def test_eval_s_consumes_flag_blocking_later_p(self):
        # In eval, `-s` doesn't delete but STILL consumes the flag, so a
        # following `-p` on the same eval string strips nothing.
        _assert_same_interactive(
            ['echo seed', 'eval "history -s XXX; history -p \'!!\'"', 'history'])

    def test_eval_p_still_strips_control(self):
        # Control (kept-green): `-p` inside eval DOES strip (no recording gate).
        _assert_same_interactive(
            ['echo seed', 'eval "history -p \'!!\'"', 'history'])

    def test_source_then_toplevel_s_restores_recording(self):
        # After source returns, the top-level `-s` deletes again (restore).
        _assert_same_interactive(
            ['echo one', "source /dev/stdin <<< ':'; history -s XXX", 'history'])
