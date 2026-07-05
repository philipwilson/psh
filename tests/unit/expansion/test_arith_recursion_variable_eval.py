"""A self-referential expression variable trips a BOUNDED arithmetic error.

Distinct from the arithmetic PARSER's nesting guard (parentheses/ternary; see
test_arith_depth_guard.py): this is the EVALUATOR re-entrancy axis. A variable
whose value is itself an expression is evaluated recursively
(`x="x+1"; $((x))` -> evaluate "x+1" -> read x -> evaluate "x+1" -> ...), so a
self-referential or too-deeply-chained expression used to blow the interpreter
stack and leak a RecursionError as "unexpected error", aborting the line. It
now trips a clean "expression recursion level exceeded" arithmetic error
(status 1, the line resumes) at bash's EXPR_NEST_MAX (1024). Probe-verified
against bash 5.2 (tmp/probes-r18t2-arith/): a reference chain 1000 deep
evaluates, one 1024 deep trips.
"""

import subprocess
import sys


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=30)


class TestSelfReferentialExpression:
    def test_paren_command_continues(self):
        # `(( x ))` fails (status 1) and the line CONTINUES (bash) — no leak.
        r = _psh_c('x="x+1"; (( x )); echo rc=$?; echo alive')
        assert r.stdout == "rc=1\nalive\n"
        assert "expression recursion level exceeded" in r.stderr
        assert "unexpected error" not in r.stderr
        assert "RecursionError" not in r.stderr
        assert "Traceback" not in r.stderr
        assert r.returncode == 0

    def test_expansion_discards_line(self):
        # `$(( x ))` is word expansion: a discard-line error (bash) — the
        # rest of the current line is dropped, status 1.
        r = _psh_c('x="x+1"; echo $((x)) tail; echo alive')
        assert r.stdout == ""
        assert "expression recursion level exceeded" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 1

    def test_let_continues(self):
        r = _psh_c('x="x+1"; let x; echo rc=$?; echo alive')
        assert r.stdout == "rc=1\nalive\n"
        assert "expression recursion level exceeded" in r.stderr
        assert r.returncode == 0

    def test_mutual_reference(self):
        # a -> b -> a -> ... also trips the bound, not a RecursionError.
        r = _psh_c('a="b"; b="a+1"; echo $((a)); echo alive')
        assert r.stdout == ""
        assert "expression recursion level exceeded" in r.stderr
        assert "unexpected error" not in r.stderr
        assert r.returncode == 1


class TestLegitReferenceChainBoundary:
    """The exact self-reference trip depth matches bash 5.2.26 (probe:
    tmp/probes-r18t2-arith/recursion_boundary.py). For the chain
    a0=0; a1="a0+1"; ...; aN="a{N-1}+1" then $(( aN )), BOTH shells evaluate
    a 1022-deep chain and BOTH trip at 1023-deep. These tests PIN that
    boundary so the +1-offset regression (psh tripping one level late) cannot
    return."""

    _MAX_OK = 1022    # deepest chain that still evaluates (bash == psh)
    _FIRST_TRIP = 1023  # shallowest chain that trips (bash == psh)

    def _chain(self, depth, tail):
        return (f'a0=0; for i in $(seq 1 {depth}); do '
                f'eval "a$i=a$((i-1))+1"; done; {tail}')

    def test_chain_at_max_ok_depth_evaluates(self):
        n = self._MAX_OK
        r = _psh_c(self._chain(n, f'echo $(( a{n} )); echo alive'))
        assert r.stdout == f"{n}\nalive\n"
        assert "recursion level exceeded" not in r.stderr
        assert r.returncode == 0

    def test_chain_at_first_trip_depth_trips(self):
        n = self._FIRST_TRIP
        # $(( )) word expansion: a discard-line error drops the rest of the
        # line (the trailing `x`/`echo alive`), status 1 — not a crash.
        r = _psh_c(self._chain(n, f'echo $(( a{n} )) x; echo alive'))
        assert r.stdout == ""
        assert "expression recursion level exceeded" in r.stderr
        assert "RecursionError" not in r.stderr
        assert "Traceback" not in r.stderr
        assert r.returncode == 1
