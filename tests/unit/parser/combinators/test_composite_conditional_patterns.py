"""Combinator behavior pins for composite operands in case/[[ ]] (WordToken R3).

Word fusion emits ONE WORD per shell word, which INCIDENTALLY widened what the
combinator parser accepts: before R3 the combinator raised a parse error on a
composite (multi-piece) pattern in a ``case`` arm or a composite operand in a
``[[ ]]`` ``==``/``=~`` test (an educational-scope gap — the pieces arrived as
separate adjacent tokens the combinator's case/test grammar did not re-join).
Post-fusion the composite is a single WORD, so the combinator parses it and
produces the bash-correct result — matching the recursive-descent parser, which
already handled these.

These are the RD-vs-combinator divergences the base↔branch execution
differential surfaced (13 fragments across 3 SHAPES). Each is a real behavior
change (base combinator = parse error → branch combinator = bash-verified
output), so it gets a dedicated pin: red on base (rc 2, parse error), green on
branch. The expected outputs are bash 5.2 verified (v, x, d unset).

SHAPE→cases:
  A  combinator `case SUBJ in <composite-pattern>)`  -> the 6 CASE_* cases
  B  combinator `[[ lhs == <composite-operand> ]]`   -> the 5 TEST_EQ_* + GLOB case
  C  combinator `[[ lhs =~ <composite-regex> ]]`     -> the REGEX case
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]

# (id, command, expected_stdout) — expected is bash 5.2 verified.
_CASES = [
    # SHAPE A: composite case pattern (concatenations of literal + expansion /
    # backtick / quoted pieces); none match SUBJECT `xyz`, so the arm is `n`.
    ("case_backtick_concat", "case xyz in a`echo z`b) echo m;; *) echo n;; esac", "n\n"),
    ("case_braced_var_concat", "case xyz in ${v}post) echo m;; *) echo n;; esac", "n\n"),
    ("case_param_expansion_concat", "case xyz in ${v:-d}x) echo m;; *) echo n;; esac", "n\n"),
    ("case_arith_concat", "case xyz in x$((1+2))y) echo m;; *) echo n;; esac", "n\n"),
    ("case_dquote_var_concat", 'case xyz in "$x"y) echo m;; *) echo n;; esac', "n\n"),
    ("case_multi_quote_concat", "case xyz in a'b'\"c\"$d) echo m;; *) echo n;; esac", "n\n"),
    # SHAPE B: composite `==` operand in [[ ]]. abc != composite -> rc 1, except
    # the multi-quote case where d is unset so the RHS is `abc` (equal -> rc 0),
    # and the quoted-glob case where the quoted `?` is a literal (matches).
    ("test_eq_braced_var", "[[ abc == ${v}post ]]; echo rc=$?", "rc=1\n"),
    ("test_eq_param_expansion", "[[ abc == ${v:-d}x ]]; echo rc=$?", "rc=1\n"),
    ("test_eq_arith", "[[ abc == x$((1+2))y ]]; echo rc=$?", "rc=1\n"),
    ("test_eq_dquote_var", '[[ abc == "$x"y ]]; echo rc=$?', "rc=1\n"),
    ("test_eq_multi_quote_equal", '[[ abc == a\'b\'"c"$d ]]; echo rc=$?', "rc=0\n"),
    ("test_eq_quoted_glob_literal", '[[ ab? == ab"?" ]] && echo Y || echo N', "Y\n"),
    # SHAPE C: composite `=~` regex operand — the quoted `.` is a literal dot.
    ("test_regex_quoted_dot", '[[ "a.c" =~ a"."c ]] && echo Y || echo N', "Y\n"),
]


@pytest.mark.parametrize("cmd,expected", [(c, e) for _, c, e in _CASES],
                         ids=[i for i, _, _ in _CASES])
def test_combinator_composite_conditional(cmd, expected):
    """The combinator parser executes a composite case/`[[ ]]` operand to the
    bash-verified result (base combinator raised a parse error here)."""
    result = subprocess.run(
        [sys.executable, "-m", "psh", "--parser", "combinator", "-c", cmd],
        capture_output=True, text=True, cwd=_REPO)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
