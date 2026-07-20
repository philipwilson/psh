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


def _run_i(argv, lines):
    with tempfile.NamedTemporaryFile(prefix='cv3hist', delete=True) as tf:
        histfile = tf.name  # a fresh, empty path — no banked history
    script = ''.join(line + '\n' for line in lines)
    r = subprocess.run(argv + ['-i'], input=script, capture_output=True,
                       text=True, timeout=20, env={'HISTFILE': histfile,
                                                    'PATH': _PATH, 'TERM': 'dumb'})
    Path(histfile).unlink(missing_ok=True)
    return _PREFIX_RE.sub('', r.stdout)


def _assert_same_interactive(lines):
    # psh FIRST (banked-histfile gotcha).
    psh = _run_i([sys.executable, '-m', 'psh'], lines)
    bash = _run_i([resolve_bash().path], lines)
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
