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

CORPUS SHAPE (declared coverage change, ruling R6-A). This corpus was a full
5-axis cartesian of 1,944 rows. That was instrument OVERBUILD: axis-
quantification requires every axis to be VARIED, not every combination to be
ENUMERATED, and a 4x-overbuilt product buries the rows that carry signal. The
shape is now:

    full product   operator x delimiter x marker-quoting (12 x 9 x 3 = 324)
    orthogonal     command context, varied against every operator
    orthogonal     option state, varied by parametrize over the whole corpus
                                                        -> 731 tests

The three product axes are the ones that INTERACT: whether a marker opens a
here-document depends on the operator spelling, the delimiter spelling and
whether the whole marker is quoted, TOGETHER. Command context and option state
do not participate in that decision, so varying them against a baseline covers
them without multiplying the rest. Every axis below is still varied, and every
row class round-1 verification bounced on is still generated and asserted BY
NAME (`test_every_bounced_row_class_survived_the_trim`).

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
  arithmetic ``$((1<<2))``, fd-dup ``<&``/``0<&``;
* FD KIND -- none, DIGIT-prefixed (``0<<``) and NAMED (``{v}<<``,
  ``{v}<<-``, ``{v}<``). The named spelling is here because round-2
  verification found the fix had stopped detecting it entirely: the axis
  had been varied by digit only;
* COMMAND CONTEXT: bare command, after a pipe, inside ``$( )``, after ``&&``;
* OPTION STATE: default and ``posix``, threaded into BOTH sides -- the session
  through the shell's live option dict and the lexer through ``LexerConfig``.

WHAT THIS INSTRUMENT CANNOT DO -- stated because round-2 verification proved it
matters. It compares the SESSION against the LEXER, so it can only ever catch
those two DISAGREEING; it cannot catch the lexer being WRONG. Reverting the
round-2 named-fd fix (`{v}<<` unregistered) leaves this entire corpus GREEN --
session and lexer are then consistently wrong together -- while the
bash-differential instruments go red (8 PTY rows, 12 non-interactive rows;
mutation-measured, not assumed). The `{v}<<` entries below therefore earn their
place by pinning session/lexer AGREEMENT on that spelling, nothing more. The
ORACLE for lexer correctness is bash, via
tests/system/interactive/test_heredoc_detection_interactive_pty.py and
tests/unit/io_redirect/test_named_fd_heredoc.py. A green run HERE is not
evidence that heredoc detection is correct.

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
              "<&", "0<&",
              # NAMED-FD spellings (round-2 blocker R7-A). The fd-kind axis had
              # only ever been varied by DIGIT; `{v}<<` was the spelling the
              # retired regex knew and the lexer did not, so the one-grammar
              # fix silently stopped detecting it and executed bodies as
              # commands. The lesson generalises: when a decider is deleted,
              # ITS input space is the claim's universe.
              "{v}<<", "{v}<<-", "{v}<"]
_DELIMITERS = ["EOF", "'EOF'", '"EOF"', r"\EOF", 'E"O"F',
               # SUBSTITUTION-BEARING delimiters (round-1 blocker R4-B):
               # taken literally, so the terminator is the whole word. The
               # retired regex scanner stopped at `(` and cooked `<<$(x)`
               # to `$`; this axis is where that would have been caught.
               "$(x)", "`x`", "$V", "${V}"]
_MARKER_QUOTING = ["{op}{delim}", "'{op}{delim}'", '"{op}{delim}"']
_CONTEXTS = ["cat {marker}", "echo x | cat {marker}", "true && cat {marker}",
             "echo $(cat {marker})"]


# The BASELINE context/quoting the orthogonal axes vary against.
_BASE_CONTEXT = "cat {marker}"
_BASE_QUOTING = "{op}{delim}"
_BASE_DELIM = "EOF"

# Rows that round 1 BOUNCED on, named individually and asserted present by
# test_every_bounced_row_class_survived_the_trim. The generator below already
# produces every one of them; this list exists so that a FUTURE change to the
# generator cannot quietly drop a class that verification already paid for.
_BOUNCED_ROW_CLASSES = {
    "substitution-bearing delimiter (R4-B)": ["cat <<$(x)", "cat <<`x`",
                                              "cat <<$V", "cat <<${V}"],
    "`<&` adjacency (R4-E)": ["cat <&EOF", "cat 0<&EOF"],
    "named-fd heredoc (R7-A regression)": ["cat {v}<<EOF",
                                           "cat {v}<<-EOF"],
    "escaped spelling (the MEDIUM-3 defect)": [r"cat \<<EOF", r"cat <\<EOF"],
    "nested context": ["echo $(cat <<EOF)"],
    "quoted marker": ["cat '<<EOF'", 'cat "<<EOF"'],
    "arithmetic shift": ["echo $((1<<2))"],
}


def _corpus():
    """The generated lines.

    SHAPE (declared coverage change, ruling R6-A): a full 5-axis cartesian was
    1,944 rows — instrument overbuild. Axis-quantification requires every axis
    VARIED, not every combination ENUMERATED, and a 4x-overbuilt product
    obscures which rows carry signal. So:

    * FULL PRODUCT over the three GRAMMAR-DECIDING axes — operator x delimiter
      x marker-quoting (12 x 9 x 3 = 324, after the named-fd operators joined
      the axis in round 2). These interact: whether a marker is a
      heredoc depends on the operator spelling, the delimiter spelling, and
      whether the whole marker is quoted, together.
    * ORTHOGONAL for the axes that do NOT interact with the grammar decision:
      command CONTEXT is varied against every operator at the baseline
      delimiter/quoting, and OPTION STATE is varied over the whole corpus by
      the test's own parametrize.

    Every axis is still varied, and every round-1 bounced row class is still
    generated (asserted by name below).
    """
    seen = set()

    def emit(line):
        if line not in seen:
            seen.add(line)
            return True
        return False

    # 1. the interacting core
    for op, delim, quoting in itertools.product(
            _OPERATORS, _DELIMITERS, _MARKER_QUOTING):
        line = _BASE_CONTEXT.format(marker=quoting.format(op=op, delim=delim))
        if emit(line):
            yield line

    # 2. CONTEXT varied orthogonally, against every operator
    for ctx, op in itertools.product(_CONTEXTS, _OPERATORS):
        marker = _BASE_QUOTING.format(op=op, delim=_BASE_DELIM)
        line = ctx.format(marker=marker)
        if emit(line):
            yield line

    # 3. Arithmetic `<<` is a shift, never a heredoc — its own axis point.
    for extra in ["echo $((1<<2))", "echo $(( 1 << 2 ))", "(( x << 2 ))"]:
        if emit(extra):
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


def test_every_bounced_row_class_survived_the_trim():
    """ADVERSARIAL AUDIT HOOK for the R6-A coverage trim.

    The corpus was deliberately reduced from a 1,944-row cartesian to the
    shape declared in `_corpus`. Ruling R6-A makes losing a bounced row class
    an automatic round-2 blocker, so each class round 1 paid for is asserted
    present BY NAME rather than trusted to fall out of the generator.
    """
    missing = {
        name: [row for row in rows if row not in CORPUS]
        for name, rows in _BOUNCED_ROW_CLASSES.items()
    }
    missing = {k: v for k, v in missing.items() if v}
    assert not missing, f"the trim dropped bounced row classes: {missing}"


# EXPECTED axis values, written as LITERALS on purpose (round-2 nit 15). The
# first version of the test below iterated the live `_OPERATORS` /
# `_DELIMITERS` / `_CONTEXTS` lists, so deleting an entry deleted it from the
# assertion too -- a self-referential universe that could never go red. These
# literals are the independent statement of what the corpus must cover.
_EXPECTED_OPERATORS = ("<<", "\\<<", "<\\<", "\\\\<<", "<<-", "<<<", "0<<",
                       "<&", "0<&", "{v}<<", "{v}<<-", "{v}<")
_EXPECTED_DELIMITERS = ("EOF", "'EOF'", '"EOF"', "\\EOF", 'E"O"F',
                        "$(x)", "`x`", "$V", "${V}")
_EXPECTED_CONTEXT_HEADS = ("cat ", "echo x | cat ", "true && cat ",
                           "echo $(cat ")


def test_the_trim_kept_every_axis_varied():
    """Each axis must still take more than one value across the corpus --
    the property a trim could silently break.

    Asserted against LITERAL expectations, not against the live axis lists:
    deleting `{v}<<` from `_OPERATORS` must turn this RED, and it could not if
    the test enumerated `_OPERATORS` to decide what to look for.
    """
    assert sum(1 for line in CORPUS if line.startswith("cat <<")) > 1
    # EXACT lines, not substring membership. A substring test is insensitive
    # here: `"{v}<<" in line` is satisfied by a line containing `{v}<<-`, so
    # deleting `{v}<<` from the axis list left this green. The corpus is
    # generated, so the exact baseline line each axis value must produce is
    # known and can be demanded.
    corpus = set(CORPUS)
    for op in _EXPECTED_OPERATORS:
        expected = f"cat {op}EOF"
        assert expected in corpus, f"operator axis lost {op!r} ({expected!r})"
    for delim in _EXPECTED_DELIMITERS:
        expected = f"cat <<{delim}"
        assert expected in corpus, f"delimiter axis lost {delim!r}"
    for head in _EXPECTED_CONTEXT_HEADS:
        assert any(line.startswith(head) for line in corpus), \
            f"context axis lost {head!r}"
