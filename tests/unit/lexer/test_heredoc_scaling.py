"""Heredoc tokenization must be LINEAR in source length (campaign B / D4).

`HeredocLexer.tokenize_with_heredocs` used to re-lex the whole accumulated
command-text prefix once per physical command line while discovering pending
heredoc operators, so a script of N command lines before a heredoc lexed
~N^2/2 characters (measured chars_lexed/len(source) ratios of 51 / 101 / 201 /
401 at N = 100 / 200 / 400 / 800 — a clean quadratic signature, ~4x per
doubling of N).

This test is DETERMINISTIC: it counts the total characters handed to
`ModularLexer` constructions during one `tokenize_with_heredocs` call (an
instrumented operation count, not wall-clock, so it is stable under xdist)
and asserts a linear bound `chars_lexed <= K * len(source)`. The final
full-text pass alone is ~1x len(source); the incremental discovery pass adds
~1x more (each command line lexed once, plus one joining newline per line),
so a healthy implementation sits near 2x. K = 3 leaves generous headroom
while failing decisively on any per-prefix re-lexing regression.
"""

import psh.lexer.heredoc_lexer as heredoc_lexer_module
from psh.lexer.heredoc_lexer import HeredocLexer

# Generous linear bound: total characters lexed per source character.
K = 3


def _chars_lexed(source: str) -> int:
    """Total length of every input handed to a ModularLexer during one
    `tokenize_with_heredocs(source)` call."""
    total = 0
    original_init = heredoc_lexer_module.ModularLexer.__init__

    def counting_init(self, input_string, *args, **kwargs):
        nonlocal total
        total += len(input_string)
        return original_init(self, input_string, *args, **kwargs)

    heredoc_lexer_module.ModularLexer.__init__ = counting_init
    try:
        HeredocLexer(source).tokenize_with_heredocs()
    finally:
        heredoc_lexer_module.ModularLexer.__init__ = original_init
    return total


def _source(command_lines: int) -> str:
    """`command_lines` simple command lines, then a heredoc."""
    return ('\n'.join('echo x' for _ in range(command_lines))
            + '\ncat <<EOF\nbody\nEOF\n')


def test_heredoc_discovery_is_linear():
    """Characters lexed must stay within K * source length at every scale.

    A per-prefix re-lexing implementation blows the bound already at 100
    lines (ratio ~51); the linear implementation stays near 2.
    """
    for command_lines in (100, 200, 400, 800, 1600):
        source = _source(command_lines)
        chars = _chars_lexed(source)
        assert chars <= K * len(source), (
            f"heredoc tokenization is superlinear at {command_lines} command "
            f"lines: lexed {chars} chars for a {len(source)}-char source "
            f"(ratio {chars / len(source):.1f}, bound {K})")


def test_heredoc_discovery_does_not_grow_per_line():
    """Doubling the command-line count must not raise the per-char ratio.

    The ratio is scale-invariant for a linear lexer and grows ~linearly with
    N for the quadratic one, so the larger input's ratio must not exceed the
    smaller's by more than timer-free slack.
    """
    small = _source(200)
    large = _source(400)
    ratio_small = _chars_lexed(small) / len(small)
    ratio_large = _chars_lexed(large) / len(large)
    assert ratio_large <= ratio_small + 0.5, (
        f"per-character lexing cost grew with input size: "
        f"{ratio_small:.2f} -> {ratio_large:.2f}")
