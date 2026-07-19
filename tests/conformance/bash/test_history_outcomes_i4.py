"""psh-vs-bash history-expansion OUTCOME matrix (campaign I4).

Channel: `-i` reading piped stdin activates the interactive family, bang-expands
AND records for BOTH shells (subprocess-friendly, no PTY). Each case feeds input
lines then `history`, so STDOUT carries both the command output and the recorded
history image — the semantic surface these pins compare.

These pin the distinct-outcomes / activation / designator / quote-suppression
behavior the reappraisal-20 history finding names. Eight rows were RED on the
pre-I4 base (see tmp/boundary-ledgers/I4.md): :p recording+single-print, `set +H`
recording, `!#`, `!0`, `:q`, `:x`, heredoc-body suppression.

HYGIENE: per-shell HISTFILE in a fresh temp dir, PSH RUNS FIRST (interactive bash
writes its session back on exit — a shared histfile would contaminate psh; the
F1 banked trap). Bash oracle via resolve_bash() (E2 ratchet). Bounded timeout.
"""

import os
import subprocess
import sys
import tempfile

import pytest
from shell_oracle import resolve_bash

_BASH = resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="no bash oracle")

_PSH_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _run(argv, lines, env_extra):
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "PS1": "", "PS2": "", "HISTFILE": os.path.join(d, "hf")}
        env.update(env_extra)
        script = "".join(line + "\n" for line in lines)
        p = subprocess.run(argv, input=script, capture_output=True, text=True,
                           env=env, cwd=d, timeout=30)
        return p.stdout


def _psh(lines):
    return _run([sys.executable, "-m", "psh", "-i"], lines,
                {"PYTHONPATH": _PSH_ROOT, "PSH_STRICT_ERRORS": "1"})


def _bash(lines):
    return _run([_BASH.path, "-i"], lines, {})


# label -> input lines (history dumped last so recording is observable)
CASES = {
    # --- distinct outcomes ---
    "normal_expand": ["echo one", "!!", "history"],
    "identical_expand": ["echo same", "!!", "history"],
    "event_not_found_not_recorded": ["echo first", "!nope", "history"],
    "print_only_recorded_not_executed": ["echo hi", "!!:p", "history"],
    "quick_substitution": ["echo foo", "^foo^bar", "history"],
    # --- event designators ---
    "bang_n": ["echo a1", "echo a2", "!1", "history"],
    "bang_neg_n": ["echo b1", "echo b2", "!-2", "history"],
    "bang_string": ["echo apple", "echo banana", "!ec", "history"],
    "bang_qmark": ["echo needle", "echo hay", "!?nee?", "history"],
    "bang_zero_is_error": ["echo z", "!0", "history"],
    "bang_hash_current_line": ["echo cur !#", "history"],
    # --- word designators & modifiers ---
    "word_dollar": ["echo w1 w2 w3", "echo !$", "history"],
    "word_star": ["echo s1 s2 s3", "echo !*", "history"],
    "word_range": ["echo r0 r1 r2 r3", "echo !!:1-2", "history"],
    "mod_head": ["echo /a/b/c", "echo !!:$:h", "history"],
    "mod_subst": ["echo hello", "!!:s/ello/i/", "history"],
    "mod_global_subst": ["echo aXbXc", "echo !!:gs/X/-/", "history"],
    "mod_q_quote": ["echo one two", "echo !!:2:q done", "history"],
    "mod_x_quote": ["echo one two", "echo !!:x done", "history"],
    # --- quote suppression ---
    "squote_literal": ["echo a", "echo '!!'", "history"],
    "dquote_expands": ["echo a", 'echo "!!"', "history"],
    "backslash_suppresses": ["echo a", r"echo \!!", "history"],
    # --- activation ---
    "set_plus_H_records_literal": ["set +H", "echo one", "!!", "history"],
    "set_minus_H_reenables": ["set +H", "set -H", "echo one", "!!", "history"],
}


@pytest.mark.parametrize("label", sorted(CASES))
def test_history_outcome_matches_bash(label):
    lines = CASES[label]
    assert _psh(lines) == _bash(lines)


def test_heredoc_body_not_expanded():
    # bash never history-expands heredoc BODY lines; psh joins opener+body into
    # one buffer, so the scanner must skip the body span. (The full history-dump
    # comparison carries a pre-existing cmdhist trailing-newline artifact that is
    # history-expansion-independent, so this targets the observable behavior:
    # the body `!!` is passed to `cat` verbatim, NOT expanded.)
    lines = ["echo seed", "cat <<EOF", "!!", "EOF"]
    out = _psh(lines)
    assert "!!" in out            # the literal body line reached cat
    assert "echo seed\n" not in out.split("seed", 1)[1]  # not expanded to prev cmd


def test_non_interactive_c_never_expands():
    # -c is not the interactive family: bash never bang-expands it (nor does psh).
    script = 'echo one; !!'
    p = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": _PSH_ROOT}, timeout=20)
    b = subprocess.run([_BASH.path, "-c", script],
                       capture_output=True, text=True, timeout=20)
    # both run `echo one` then fail on the literal `!!` command.
    assert p.stdout == b.stdout == "one\n"
