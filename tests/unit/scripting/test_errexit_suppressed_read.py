"""Unit arms for the raise-time suppression read (slot 2.4, ruling R6-F).

``SourceProcessor#_errexit_suppressed`` decides ONE bit — is errexit suppressed
at the instant the substitution abort is constructed — and its docstring makes
two claims about HOW it reads that bit. Both were prose only; the round-5
verifier flagged the no-executor arm and the missing-``context`` claim as
untested. They are cheap to check directly, so they are checked directly:

* NO LIVE EXECUTOR is a legitimate state (the outermost reader parse, before
  any command runs) and reads as UNSUPPRESSED.
* the ``context`` read is EXPLICIT: a live executor missing that attribute
  RAISES rather than degrading silently to "unsuppressed", which is the failure
  mode that would hide a rewiring.

The end-to-end behaviour these two arms underpin is pinned in the conformance
suite (the -c/file/stdin reader-parse rows); this file is the unit half.
"""

import types

import pytest

from psh.scripting.source_processor import SourceProcessor


def _processor(executor):
    """A SourceProcessor over the smallest shell that can answer the question."""
    shell = types.SimpleNamespace(state=types.SimpleNamespace(),
                                  _current_executor=executor)
    return SourceProcessor(shell)


def _executor(depth):
    return types.SimpleNamespace(
        context=types.SimpleNamespace(errexit_suppress=depth))


def test_no_live_executor_reads_as_unsuppressed():
    assert _processor(None)._errexit_suppressed() is False


def test_missing_current_executor_attribute_reads_as_unsuppressed():
    """The outermost reader parse can precede the attribute existing at all."""
    shell = types.SimpleNamespace(state=types.SimpleNamespace())
    assert SourceProcessor(shell)._errexit_suppressed() is False


@pytest.mark.parametrize("depth,expected", [
    (0, False),     # a live executor with no suppressing context open
    (1, True),      # one `||` / if-condition / `!`
    (2, True),      # a seeded fork depth plus an in-child context
])
def test_live_executor_reports_the_total_depth(depth, expected):
    assert _processor(_executor(depth))._errexit_suppressed() is expected


def test_a_live_executor_without_a_context_raises():
    """The claim the docstring makes about the EXPLICIT read, as a check.

    A ``getattr(executor, 'context', None)`` here would answer False — i.e. it
    would report "not suppressed" for a shell whose wiring had changed under
    it. The plain attribute access makes that loud instead."""
    with pytest.raises(AttributeError):
        _processor(types.SimpleNamespace())._errexit_suppressed()
