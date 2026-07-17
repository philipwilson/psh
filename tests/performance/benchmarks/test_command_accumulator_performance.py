"""Timing sanity check for CommandAccumulator.feed (P7 item 1).

`CommandAccumulator.feed` re-parses the WHOLE buffer on every fed line
(correctness first — see its docstring), so gathering a logical command of
N physical lines is O(N^2) in the parser. That is an accepted, documented
bound; this guard is NOT a tight benchmark. It exists to catch a *future*
super-quadratic regression (e.g. an accidental extra re-lex per line, or a
preprocessing step that stops short-circuiting): a 500-line function must
still gather in a generous wall of CPU time.

Tier: CPU-time benchmark (campaign E1b) — `benchmark` + `serial` marked,
excluded from every standard-gate phase; run via
`python run_tests.py --benchmarks` (or `pytest tests/performance/`).

Measurement discipline (matches test_parsing_performance.py): time
`time.process_time()` (CPU only, immune to preemption) and take the min
over a few iterations to discard cache-cold / GC-interrupted runs.
"""
import time

import pytest

from psh.scripting.command_accumulator import CommandAccumulator
from psh.shell import Shell

pytestmark = [pytest.mark.benchmark, pytest.mark.serial]


def _feed_all(shell, lines):
    acc = CommandAccumulator(shell)
    for ln in lines:
        acc.feed(ln)


def _min_feed_time(shell, lines, iterations=3):
    best = float('inf')
    for _ in range(iterations):
        t0 = time.process_time()
        _feed_all(shell, lines)
        best = min(best, time.process_time() - t0)
    return best


@pytest.mark.performance
class TestCommandAccumulatorFeedPerformance:
    def test_500_line_function_gathers_within_budget(self):
        """Feeding a 500-line function body line-by-line stays well under a
        generous CPU budget. Guards against a super-quadratic regression in
        the whole-buffer re-parse; the accepted O(N^2) parse itself gathers
        this in a fraction of the budget."""
        shell = Shell()
        lines = (['myfunc() {']
                 + [f'  echo line {i}' for i in range(500)]
                 + ['}'])
        elapsed = _min_feed_time(shell, lines)
        # Generous: ~9s CPU on a 2026 dev machine; 60s leaves headroom for a
        # much slower nightly host, while a genuine algorithmic regression
        # (per-line re-lex blow-up) still blows past it. Coarse backstop,
        # not a tight benchmark.
        assert elapsed < 60.0, f"500-line feed took {elapsed:.2f}s CPU"

    def test_continuation_heavy_500_lines_within_budget(self):
        """The all-continuation-line shape (every physical line ends in a
        backslash) short-circuits the parse but re-runs the continuation
        fold over the whole buffer each line. It must also stay bounded."""
        shell = Shell()
        lines = (['myfunc() {']
                 + [f'  echo line {i} \\' for i in range(250)]
                 + ['  done', '}'])
        elapsed = _min_feed_time(shell, lines)
        # Same 60s slow-host headroom rationale as above (~4s measured).
        assert elapsed < 60.0, f"continuation-heavy feed took {elapsed:.2f}s CPU"
