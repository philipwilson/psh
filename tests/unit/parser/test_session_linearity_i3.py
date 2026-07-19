"""Operation-count pins for the incremental completeness engine (campaign I3).

`parser.session.ParseSession` is the one multiline-completeness engine. These
pins assert its WORK with deterministic counters (`SessionOps`) — tokens lexed
and tokens parsed across feeds — not wall-clock time, so they are stable under
xdist and machine noise.

Two families are genuinely LINEAR and pinned as such:

* a heredoc BODY line costs no lex and no parse (matched against the pending
  queue, S2) — ``parse_calls``/``tokens_parsed`` stay CONSTANT as the body
  grows;
* a multi-command stream commits and drops each complete command, so N complete
  commands cost O(N) — ``tokens_parsed`` doubles when N doubles.

One family is the fenced RESIDUAL and pinned with a doubling-ratio
CHARACTERIZATION (see ``test_open_construct_residual_is_quadratic_by_design``):
a single OPEN logical command re-lexes+re-parses its own accumulated text on
every fed line → O(k²). That residual is oracle-forced and lexer-bound, not a
defect (full rationale in that test's docstring). The ratio band brackets O(k²)
so an accidental worsening to O(k³) fails, and a future resumable-parser
improvement to O(k) flips it consciously.
"""

import pytest

from psh.parser.session import ParserDriver, SessionInputs
from psh.scripting.lex_parse import lex_and_expand
from psh.shell import Shell


def _make_session(shell):
    """A real completeness session wired to the production lex seam."""
    def lex(preview, base_line):
        return lex_and_expand(
            preview, shell, base_line=base_line,
            lexer_options=shell.state.options, warn_unterminated=False)
    return ParserDriver.start_session(
        SessionInputs(lex=lex, lexer_options=shell.state.options))


def _feed_heredoc_body(shell, n):
    s = _make_session(shell)
    s.feed("cat <<EOF")
    for i in range(n):
        s.feed(f"body line {i}")
    s.feed("EOF")
    return s.ops


def _feed_multi_command(shell, n):
    s = _make_session(shell)
    for i in range(n):
        s.feed(f"echo {i}")
    return s.ops


def _feed_open_if(shell, n):
    s = _make_session(shell)
    s.feed("if true; then")
    for i in range(n):
        s.feed(f"echo {i}")
    # deliberately never fed `fi`: the command stays OPEN, so every feed
    # re-parses the whole accumulated body (the residual under measurement).
    return s.ops


# === LINEAR family 1: heredoc bodies cost O(1) per body line ===

@pytest.mark.parametrize("n", [50, 100, 200])
def test_heredoc_body_line_is_o1(n):
    """A heredoc BODY line triggers no trial parse — the pending-queue match is
    O(1). So parse work is CONSTANT no matter how large the body grows."""
    ops = _feed_heredoc_body(Shell(), n)
    # Exactly one trial parse happens (the final line, after EOF terminates the
    # body); the N body lines and the `cat <<EOF` opener never trial-parse.
    assert ops.parse_calls == 1
    # Parse work does not grow with body size.
    assert ops.tokens_parsed == _feed_heredoc_body(Shell(), 50).tokens_parsed
    # Every body line (plus the terminating EOF line) was queue-matched, O(1).
    assert ops.heredoc_body_lines == n + 1


def test_heredoc_body_parse_work_is_constant_across_sizes():
    small = _feed_heredoc_body(Shell(), 100).tokens_parsed
    large = _feed_heredoc_body(Shell(), 400).tokens_parsed
    assert small == large  # O(1) in body size — genuinely linear overall


# === LINEAR family 2: a multi-command stream is O(N) ===

def test_multi_command_stream_is_linear():
    """N complete one-line commands commit-and-drop, so total parse work is
    O(N): doubling N doubles tokens_parsed (ratio ~2, never ~4)."""
    shell = Shell()
    t100 = _feed_multi_command(shell, 100).tokens_parsed
    t200 = _feed_multi_command(Shell(), 200).tokens_parsed
    t400 = _feed_multi_command(Shell(), 400).tokens_parsed
    # one trial parse per complete command
    assert _feed_multi_command(Shell(), 100).parse_calls == 100
    r1, r2 = t200 / t100, t400 / t200
    assert 1.8 <= r1 <= 2.3, f"200/100 ratio {r1} not ~2 (linear)"
    assert 1.8 <= r2 <= 2.3, f"400/200 ratio {r2} not ~2 (linear)"


# === RESIDUAL: a single open construct is O(k^2) BY DESIGN (fenced) ===

def test_open_construct_residual_is_quadratic_by_design():
    """A single OPEN logical command (a growing `if…fi` never closed) re-lexes
    and re-parses its whole accumulated body on EVERY fed line → O(k²) total.

    This is the H15 residual and it is CAUSED by an oracle constraint, not a
    defect:

    * bash reports a mid-construct syntax error IMMEDIATELY (PTY-proven — see
      ``tests/conformance/bash/test_multiline_immediate_error_i3_conformance``:
      `if true; then echo )` errors on the offending line, not deferred to
      `fi`), so the completeness trial CANNOT be deferred to structural close —
      it must run on every feed to stay faithful;
    * psh's ModularLexer is forward-only and cannot resume mid-construct (its
      fusion/keyword post-passes are whole-list), so the lex cannot be made
      incremental within one open construct.

    Linearising this needs a resumable lexer+parser (bash's re-entrant model) —
    a grammar rewrite outside the campaign's S1–S5 fences, recorded on the
    post-campaign register as the path to FULL H15 closure. The ratio band
    below brackets O(k²): it rejects an accidental O(k³) worsening (~8×) and
    would fail — flagging a CONSCIOUS review — if a future resumable engine
    brings it down toward O(k) (~2×).
    """
    t50 = _feed_open_if(Shell(), 50).tokens_parsed
    t100 = _feed_open_if(Shell(), 100).tokens_parsed
    t200 = _feed_open_if(Shell(), 200).tokens_parsed
    r1, r2 = t100 / t50, t200 / t100
    assert 3.0 <= r1 <= 5.0, f"100/50 ratio {r1} not ~4 (quadratic residual)"
    assert 3.0 <= r2 <= 5.0, f"200/100 ratio {r2} not ~4 (quadratic residual)"
