"""Lexer performance regression tests (v0.272.0).

The architecture review measured lexing time DOUBLING-squared with input
size: a single command line of N quoted words lexed in O(N^2) because
every quote/expansion character triggered a backward scan to the previous
command separator (_is_inside_potential_array_assignment). That scan is
now a lazily-built O(n) forward map; these tests pin the linear behavior.
"""

import time

from psh.lexer import tokenize


def _lex_time(n: int) -> float:
    # One long line, space-separated: no ';' barriers, the old scan's
    # worst case.
    src = 'echo ' + ' '.join(f'"w{i}"' for i in range(n))
    start = time.perf_counter()
    tokens = tokenize(src)
    elapsed = time.perf_counter() - start
    assert len(tokens) > n  # sanity: it actually lexed
    return elapsed


def test_long_quoted_line_lexes_fast():
    """4000 quoted words on one line must lex in well under a second.

    Linear behavior measures ~0.04s here; the old quadratic scan took
    ~3.8s. The 2s bound leaves room for slow CI machines while still
    failing decisively on an O(N^2) regression.
    """
    assert _lex_time(4000) < 2.0


def test_lexing_scales_roughly_linearly():
    """Doubling the input must not quadruple the time.

    A quadratic lexer shows a ratio of ~4 here; linear is ~2. The 3.2
    bound tolerates timer noise while catching superlinear blowup.
    """
    t1 = _lex_time(2000)
    t2 = _lex_time(4000)
    # Guard against measuring noise on a too-fast baseline
    if t1 < 0.005:
        t1 = max(t1, 0.005)
    assert t2 / t1 < 3.2, f"lexing scaled superlinearly: {t1:.4f}s -> {t2:.4f}s"
