"""Typed HistoryExpansionResult — the four distinct outcomes (campaign I4).

The producer HistoryExpander.expand_history returns a typed result whose `kind`
(NONE / EXPANDED / PRINT_ONLY / ERROR) is the authority — not overloaded
sentinels, not a regex, not `expanded_text != original_text`. These pin the
producer directly (in-process, histexpand forced on); the bash-compared
end-to-end behavior lives in tests/conformance/bash/test_history_outcomes_i4.py.
"""

import dataclasses
import io

import pytest

from psh.interactive.history_result import (
    HistoryExpansionKind,
    HistoryExpansionResult,
)
from psh.shell import Shell


@pytest.fixture
def expander():
    sh = Shell(norc=True)
    sh.state.options["histexpand"] = True
    return sh.history_expander


def _seed(expander, *entries):
    expander.state.history[:] = list(entries)


# --- The four distinct outcomes ------------------------------------------

def test_none_when_no_reference(expander):
    _seed(expander, "echo prev")
    r = expander.expand_history("echo plain word")
    assert r.kind is HistoryExpansionKind.NONE
    assert r.text == "echo plain word"
    assert not r.changed
    assert r.recordable_text == "echo plain word"  # a plain line is recorded


def test_none_when_histexpand_off_keeps_literal_bang(expander):
    # set +H: `!!` is a literal command, NOT a reference. bash records it.
    expander.state.options["histexpand"] = False
    _seed(expander, "echo prev")
    r = expander.expand_history("!!")
    assert r.kind is HistoryExpansionKind.NONE
    assert r.text == "!!"
    assert r.recordable_text == "!!"  # the H-finding: NONE is still recordable


def test_expanded(expander):
    _seed(expander, "echo one two")
    r = expander.expand_history("!!")
    assert r.kind is HistoryExpansionKind.EXPANDED
    assert r.text == "echo one two"
    assert r.changed
    assert r.recordable_text == "echo one two"  # bash records the EXPANSION


def test_expanded_to_identical_text_is_still_expanded(expander):
    # THE type's reason for being: !! repeating a command that already reads
    # `echo x` expands to identical text, but it is EXPANDED (bash echoes and
    # records it as an expansion) — a string compare `text == original` misses
    # this. history[-1] == the input here.
    _seed(expander, "echo x")
    r = expander.expand_history("echo x")  # no bang -> NONE
    assert r.kind is HistoryExpansionKind.NONE
    # Now the real identical case: !! whose expansion equals the typed line.
    _seed(expander, "!!")  # (contrived) previous line literally `!!`
    _seed(expander, "echo x")
    r2 = expander.expand_history("!!")
    assert r2.kind is HistoryExpansionKind.EXPANDED
    assert r2.text == "echo x"
    assert r2.changed  # TRUE even though callers can't tell from text alone


def test_print_only(expander):
    _seed(expander, "echo hi")
    r = expander.expand_history("!!:p")
    assert r.kind is HistoryExpansionKind.PRINT_ONLY
    assert r.is_print_only
    assert r.text == "echo hi"
    assert r.changed
    assert r.recordable_text == "echo hi"  # :p IS recorded (bash)


def test_error_event_not_found(expander):
    _seed(expander, "echo hi")
    r = expander.expand_history("!nope")
    assert r.kind is HistoryExpansionKind.ERROR
    assert r.is_error
    assert r.error == "!nope: event not found"
    assert r.recordable_text is None  # a failed reference is NOT recorded


# --- The producer is PURE (no printing) ----------------------------------

def test_producer_never_prints(expander, capsys):
    _seed(expander, "echo hi")
    for expr in ("!!", "!!:p", "!nope", "!!:bad"):
        expander.expand_history(expr)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_producer_does_not_touch_shell_stdout(expander):
    # Even a :p (which historically printed to shell.stdout) writes nothing.
    buf = io.StringIO()
    expander.shell.stdout = buf
    _seed(expander, "echo hi")
    expander.expand_history("!!:p")
    assert buf.getvalue() == ""


# --- Source spans --------------------------------------------------------

def test_spans_locate_the_reference(expander):
    _seed(expander, "echo one")
    r = expander.expand_history("prefix !! suffix")
    assert r.kind is HistoryExpansionKind.EXPANDED
    assert r.text == "prefix echo one suffix"
    assert len(r.spans) == 1
    span = r.spans[0]
    assert (span.start, span.end) == (7, 9)  # the `!!` in the input


def test_none_has_no_spans(expander):
    _seed(expander, "echo one")
    r = expander.expand_history("nothing here")
    assert r.spans == ()


# --- New designators / modifiers (I4) ------------------------------------

def test_bang_zero_is_error(expander):
    _seed(expander, "cmd a b c")
    r = expander.expand_history("!0")
    assert r.is_error  # event numbers are 1-based; !0 is not an event


def test_bang_hash_is_current_line(expander):
    _seed(expander, "echo prev")
    r = expander.expand_history("echo pre !#")
    assert r.kind is HistoryExpansionKind.EXPANDED
    assert r.text == "echo pre echo pre "


def test_q_modifier_quotes_whole_selection(expander):
    _seed(expander, "echo a'b'c")
    r = expander.expand_history("!!:q")
    assert r.text == "'echo a'\\''b'\\''c'"


def test_x_modifier_quotes_each_word(expander):
    _seed(expander, "echo a b c")
    r = expander.expand_history("!!:x")
    assert r.text == "'echo' 'a' 'b' 'c'"


# --- Heredoc-body span scan (incl. the dq-cmdsub reopen; bounce blocker 2) --

def test_heredoc_body_spans_dquoted_cmdsub():
    # `$(` inside double quotes reopens command context (bash), so the heredoc
    # opened there is real: its body + terminator lines are suppressed spans.
    # RED at cd3ddb0b^ (flat quote flags saw the opener as quoted -> no spans).
    from psh.interactive.history_expansion import heredoc_body_spans
    cmd = 'echo "$(cat <<EOF\n!!\nEOF\n)"'
    assert heredoc_body_spans(cmd) == [(18, 20), (21, 24)]


def test_heredoc_body_expansion_suppressed_in_dquoted_cmdsub(expander):
    _seed(expander, "echo seed")
    r = expander.expand_history('echo "$(cat <<EOF\n!!\nEOF\n)"')
    assert r.kind is HistoryExpansionKind.NONE  # the body !! is NOT a reference
    assert "!!" in r.text                        # left literal


def test_heredoc_body_spans_controls():
    # Controls around the reopen delta: a dquoted marker WITHOUT a cmdsub is
    # not a heredoc; `$((` in dquotes is arithmetic (its << is a shift); an
    # unquoted cmdsub opener and a plain heredoc still detect (unchanged).
    from psh.interactive.history_expansion import heredoc_body_spans
    assert heredoc_body_spans('echo "<<EOF" done\n!!') == []
    assert heredoc_body_spans('echo "$((1<<2))"\n!!') == []
    assert heredoc_body_spans('echo $(cat <<EOF\n!!\nEOF\n)') == [(17, 19), (20, 23)]
    assert heredoc_body_spans('cat <<EOF\n!!\nEOF') == [(10, 12), (13, 16)]


# --- Frozen dataclass ----------------------------------------------------

def test_result_is_frozen():
    r = HistoryExpansionResult(HistoryExpansionKind.NONE, "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.kind = HistoryExpansionKind.EXPANDED  # type: ignore[misc]
