"""Conformance tests for interactive history expansion (bash).

Reappraisal #16 H7: ch17 claimed history-expansion designators were "not
implemented" when in fact psh implements the full set (event designators,
word designators, `:h`/`:t`/`:r`/`:e`/`:s`/`:g&` modifiers, and `^old^new`
quick substitution). The row was flipped to "Full support"; this file is the
proving conformance test the meta-test demands.

History expansion is INTERACTIVE-ONLY in both shells (bash and psh disable it
for non-interactive `-c`/scripts), so the standard `assert_identical_behavior`
`-c` harness cannot exercise it. Instead we use bash's own non-interactive
expansion engine as the oracle: `history -s EVENT` seeds the event list and
`history -p EXPR` performs (and prints) the expansion without a tty. psh has no
`history -p`, so we drive psh's real expansion engine (`HistoryExpander`) in
process against the same seeded history. Both sides are thus the shells' actual
expansion code, compared byte-for-byte.
"""

import os
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash  # noqa: E402

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from psh.shell import Shell  # noqa: E402


def _shq(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _bash_expand(history, expr):
    """(text, failed) from bash `history -p` after seeding `history -s`."""
    script = "".join(f"history -s {_shq(h)}\n" for h in history)
    script += f"history -p -- {_shq(expr)}\n"
    r = subprocess.run([resolve_bash().path, "-c", script],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.rstrip("\n"), r.returncode != 0


def _psh_expand(history, expr):
    """(text, failed) from psh's HistoryExpander on the same seeded history."""
    sh = Shell()
    sh.state.options["histexpand"] = True
    sh.state.history[:] = list(history)
    out = sh.history_expander.expand_history(
        expr, print_expansion=False, report_errors=False)
    if out is None:
        return None, True
    return out.rstrip("\n"), False


def _assert_expands(history, expr):
    """psh's expansion of `expr` (given `history`) must match bash's."""
    b_text, b_failed = _bash_expand(history, expr)
    p_text, p_failed = _psh_expand(history, expr)
    assert p_failed == b_failed, (
        f"expansion success/failure differs for {expr!r} "
        f"(bash failed={b_failed}, psh failed={p_failed})")
    if not b_failed:
        assert p_text == b_text, (
            f"expansion of {expr!r} differs:\n"
            f"  bash: {b_text!r}\n  psh : {p_text!r}")


ABG = ["echo alpha beta gamma"]
MULTI = ["ls /usr/bin", "grep foo bar.txt baz.txt", "cat a.c b.c"]


@pytest.mark.parametrize("history,expr", [
    # Event designators.
    (ABG, "!!"),
    (MULTI, "!1"),
    (MULTI, "!3"),
    (MULTI, "!-1"),
    (MULTI, "!-3"),
    (MULTI, "!ls"),
    (MULTI, "!grep"),
    (MULTI, "!?foo?"),
    # Word designators (word 0 is the command; $ is last; * is 1..last).
    (ABG, "!!:0"),
    (ABG, "!!:1"),
    (ABG, "!!:$"),
    (ABG, "!!:^"),
    (ABG, "!!:*"),
    (ABG, "!!:1-2"),
    (ABG, "!!:2-"),
    (ABG, "!!:2*"),
    (ABG, "!$"),
    (ABG, "!^"),
    (ABG, "!*"),
    (MULTI, "!grep:2"),
    (MULTI, "!grep:$"),
    # :h/:t/:r/:e pathname modifiers.
    (["cat /a/b/c.txt"], "!!:$:h"),
    (["cat /a/b/c.txt"], "!!:$:t"),
    (["cat /p/q/r.tar.gz"], "!!:$:r"),
    (["cat /p/q/r.tar.gz"], "!!:$:e"),
    # :s substitution (first-only and :g global) and chaining.
    (["echo hello world"], "!!:s/hello/goodbye/"),
    (["echo aa aa aa"], "!!:gs/aa/bb/"),
    (["one two three"], "!!:s/two/2/:s/three/3/"),
    # ^old^new quick substitution.
    (["echo hello world"], "^hello^goodbye"),
    (["ECHO x"], "^ECHO^echo"),
    # Reference embedded mid-line.
    (["make build"], "sudo !!"),
    # Errors: event not found / bad word specifier -> failed expansion.
    (ABG, "!99"),
    (ABG, "!nope"),
    (["a b c"], "!!:5"),
    # No expansion: literal !, quoting.
    (ABG, "echo a!=b"),
    (ABG, "[[ ! -f x ]]"),
    (ABG, "echo 'literal !!'"),
])
def test_history_expansion_matches_bash(history, expr):
    _assert_expands(history, expr)
