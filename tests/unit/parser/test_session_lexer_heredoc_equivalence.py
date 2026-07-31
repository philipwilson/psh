"""ONE heredoc grammar: the session agrees with the lexer (slot 2.5, #22 MEDIUM-3).

The completeness oracle used to answer "does this line open a here-document?"
with a SECOND, regex-based grammar (``utils/heredoc_detection.py``'s
``scan_line_heredoc_markers`` reached through ``open_heredoc_specs``) before the
real lexer ever ran. The two grammars disagreed: on ``echo \\<<EOF`` the regex
reported a pending heredoc on ``EOF`` while the real lexer -- correctly, and
like bash -- produced ``WORD '\\<'``, ``REDIRECT_IN '<'``, ``WORD 'EOF'``. The
session then swallowed the next physical line as a phantom body.

The session now derives its pending heredocs from LEXER EVENTS
(``parser/session.py#_lexer_pending_heredocs``, reading the lexer's own heredoc
collector via the injected lex seam). These tests are the executable statement
that there is only ONE grammar left: for every generated line, the session's
heredoc decision equals the lexer's own registration.

GENERATED DOMAIN -- every axis this corpus varies, named (ruling R1-E):

* SPELLING of the operator: bare ``<<``, escaped ``\\<<``, escaped-second
  ``<\\<``, escaped-escape ``\\\\<<``;
* QUOTING of the whole marker: unquoted, ``'...'``, ``"..."``;
* QUOTING of the DELIMITER: bare ``EOF``, ``'EOF'``, ``"EOF"``, ``\\EOF``,
  ``E"O"F``;
* SUBSTITUTION-BEARING delimiters: ``$(x)``, ``` `x` ```, ``$V``, ``${V}`` --
  taken LITERALLY, so the whole word is the terminator. This axis exists
  because round-1 verification caught its absence: the retired regex scanner
  stopped at ``(`` and cooked ``<<$(x)`` down to ``$``, and a quoting-only
  delimiter axis could never have surfaced that;
* OPERATOR ADJACENCY: plain, tab-strip ``<<-``, here-string ``<<<``,
  digit-prefixed fd ``0<<``, fd-dup ``<&``/``0<&``, arithmetic ``$((1<<2))``;
* COMMAND CONTEXT: bare command, after a pipe, inside ``$( )``, after ``&&``;
* OPTION STATE: default and ``posix``, threaded into BOTH sides -- the session
  through the shell's live option dict and the lexer through ``LexerConfig``.

NOT in the domain, and each with the instrument that DOES cover it:

* multi-line bodies -- the queue's head-of-queue close policy is pinned by
  tests/unit/lexer/test_heredoc_transaction_s2.py;
* interactive PS2 rendering -- pinned at a real terminal by
  tests/system/interactive/test_heredoc_detection_interactive_pty.py;
* HEREDOC + UNCLOSED QUOTE on one line (``cat <<EOF "abc``) -- this corpus
  structurally cannot express it, because ``_lexer_says_pending`` would raise
  on text that does not tokenize. The behavior IS pinned, at a real terminal,
  by the ``heredoc_unclosed_dq`` row of the PTY module named above. Declared
  here rather than left to be discovered (round-1 blocker R4-B).
"""
import itertools

import pytest

from psh.lexer.heredoc_lexer import HeredocLexer
from psh.lexer.position import LexerConfig
from psh.scripting.command_accumulator import (
    CommandAccumulator,
    HintKind,
    NeedMore,
)
from psh.shell import Shell
from psh.utils.heredoc_detection import HeredocTermination

# --- the generated corpus -------------------------------------------------

_OPERATORS = ["<<", r"\<<", r"<\<", "\\\\<<", "<<-", "<<<", "0<<",
              # `<&` adjacency (brief axis; round-1 blocker R4-E).
              "<&", "0<&"]
_DELIMITERS = ["EOF", "'EOF'", '"EOF"', r"\EOF", 'E"O"F',
               # SUBSTITUTION-BEARING delimiters (round-1 blocker R4-B):
               # taken literally, so the terminator is the whole word. The
               # retired regex scanner stopped at `(` and cooked `<<$(x)`
               # to `$`; this axis is where that would have been caught.
               "$(x)", "`x`", "$V", "${V}"]
_MARKER_QUOTING = ["{op}{delim}", "'{op}{delim}'", '"{op}{delim}"']
_CONTEXTS = ["cat {marker}", "echo x | cat {marker}", "true && cat {marker}",
             "echo $(cat {marker})"]


def _corpus():
    seen = set()
    for op, delim, quoting, ctx in itertools.product(
            _OPERATORS, _DELIMITERS, _MARKER_QUOTING, _CONTEXTS):
        line = ctx.format(marker=quoting.format(op=op, delim=delim))
        if line not in seen:
            seen.add(line)
            yield line
    # Arithmetic `<<` is a shift, never a heredoc — its own axis point.
    for extra in ["echo $((1<<2))", "echo $(( 1 << 2 ))", "(( x << 2 ))"]:
        yield extra


CORPUS = sorted(_corpus())


def _lexer_says_pending(line, posix):
    """The LEXER's own answer: heredocs still awaiting a terminator line.

    The option state is threaded into the lexer config, so the axis the
    domain statement quantifies over is actually varied on BOTH sides of
    the comparison (round-1 nit 4: it used to be accepted and ignored
    here, which made the oracle side option-blind).
    """
    config = LexerConfig(posix_mode=posix)
    unit = HeredocLexer(line, config=config,
                        warn_unterminated=False).tokenize_with_heredocs()
    heredocs = unit.heredocs or {}
    return tuple(
        entry.spec.cooked for _, entry in sorted(heredocs.items())
        if entry.collected.termination is HeredocTermination.EOF)


def _session_says_pending(line, posix):
    """The SESSION's answer, as the gathering layers observe it."""
    shell = Shell(norc=True)
    if posix:
        shell.state.options['posix'] = True
    acc = CommandAccumulator(shell)
    acc.history_expansion_eligible = False
    result = acc.feed(line)
    if isinstance(result, NeedMore) and result.hint.kind is HintKind.HEREDOC:
        return (result.hint.detail,)
    return ()


@pytest.mark.parametrize("posix", [False, True], ids=["default", "posix"])
@pytest.mark.parametrize("line", CORPUS, ids=CORPUS)
def test_session_heredoc_decision_equals_the_lexers(line, posix):
    """THE property: one grammar. The session's pending-heredoc answer is the
    lexer's, for every generated line and both option states."""
    assert _session_says_pending(line, posix) == _lexer_says_pending(line, posix)


def test_the_corpus_actually_covers_both_answers():
    """A guard on the guard: a corpus that never opens a heredoc — or never
    declines to — would make the equivalence property vacuous."""
    answers = {bool(_lexer_says_pending(line, False)) for line in CORPUS}
    assert answers == {True, False}, answers


def test_the_defect_spelling_is_in_the_corpus_and_opens_nothing():
    """The exact #22 MEDIUM-3 shape, asserted directly rather than trusted to
    fall out of the generator."""
    assert any(r"\<<" in line for line in CORPUS)
    assert _lexer_says_pending(r"echo \<<EOF", False) == ()
    assert _session_says_pending(r"echo \<<EOF", False) == ()


def test_a_true_heredoc_still_opens_one():
    """The control: the fix must not work by never detecting heredocs."""
    assert _session_says_pending("cat <<EOF", False) == ("EOF",)
    assert _lexer_says_pending("cat <<EOF", False) == ("EOF",)
