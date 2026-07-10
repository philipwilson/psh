"""N3: full disclosure of the word-fusion (R3) improvement surface.

The base->branch execution differential (tmp/r3_differential_fixed.py, HEAD vs
34bd8c21) surfaced 27 combinator divergences and, in the verifier's larger
fragment set, 3 recursive-descent divergences — ALL improvements (base = parse
error, branch = the bash-verified result). The R3 branch already pinned 13 of
the combinator case/[[ composites in
tests/unit/parser/combinators/test_composite_conditional_patterns.py; this file
discloses the REST of the surface so nothing is unpinned:

  * the remaining case / [[ ]] composite-operand shapes (ANSI-C $'x', a
    single-quote run, $USER, an unquoted-var + double-quoted concat), which the
    combinator rejected pre-fusion — representative of the 22-wide case/[[ family;
  * the 5-wide bracket-word family (a word STARTING with ``]``): base wrongly
    parse-errored (``]`` was an RBRACKET the command grammar rejected); post-
    fusion ``]x`` etc. is one WORD run as a command, matching bash (rc 127). The
    lone exception ``]]`` is a KNOWN divergence — see the module note below —
    and is deliberately NOT asserted here;
  * the 3-wide recursive-descent ``[[ ~ax= ]]`` family: a ``[[ ]]`` operand
    containing ``~`` and ``=`` (``~ax=``) that base RD rejected (rc 2) and branch
    RD now accepts as bash does (rc 0).

Every expected value is bash 5.2 verified (v, x, d, USER-insensitive: the
patterns are chosen not to match). Each case is RED on base 34bd8c21 (parse
error) and green on branch.

KNOWN DIVERGENCE, NOT fixed here (ledgered in tmp/fixforward_ledger.md): a bare
``]]`` command yields psh rc 127 (both parsers treat ``]]`` as a command word)
vs bash rc 2 (syntax error). This is PRE-EXISTING on recursive descent (base RD
also rc 127); fusion merely converged the combinator (base rc 2) onto RD. It is
an obscure edge (``]]`` with no opening ``[[``) and out of R3's scope.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, command, rc, stdout) — bash 5.2 verified; RED on base (rc 2, parse error).
# Composite case/[[ shapes NOT already covered by the 13 combinator pins.
_COMPOSITE = [
    ("case_dollar_user", 'case xyz in pre$USER"x") echo m;; *) echo n;; esac', 0, "n\n"),
    ("case_ansic", "case xyz in p$'x'q) echo m;; *) echo n;; esac", 0, "n\n"),
    ("case_single_quote_run", "case xyz in p'q'r) echo m;; *) echo n;; esac", 0, "n\n"),
    ("case_var_dquote", 'case xyz in a$x"b"c) echo m;; *) echo n;; esac', 0, "n\n"),
    ("test_eq_ansic", "[[ abc == p$'x'q ]]; echo rc=$?", 0, "rc=1\n"),
    ("test_eq_single_quote_run", "[[ abc == p'q'r ]]; echo rc=$?", 0, "rc=1\n"),
    # a$x"b"c with x unset -> abc == abc -> rc 0
    ("test_eq_var_dquote", '[[ abc == a$x"b"c ]]; echo rc=$?', 0, "rc=0\n"),
    ("test_eq_backtick", '[[ abc == a`echo z`b ]]; echo rc=$?', 0, "rc=1\n"),
]

# Bracket-word family: a word starting with ']' is a command post-fusion (rc 127
# / runs), NOT a parse error. ']]' excluded (see module note).
_BRACKET_WORD = [
    ("rbrack_word_runs", "]x; echo done", 0, "done\n"),
    ("rbrack_assign_runs", "]=x; echo done", 0, "done\n"),
    ("rbrack_nameassign_runs", "]a=b; echo done", 0, "done\n"),
    ("rbrack_lbrack_command", "][", 127, ""),
]

# Recursive-descent [[ ~ax= ]] family: base RD rc 2 -> branch RD rc 0 (== bash).
_RD_TILDE = [
    ("cond_tilde_eq", "[[ ~ax= ]]; echo rc=$?", 0, "rc=0\n"),
    ("cond_tilde_both", "[[ a~x= == a~x= ]]; echo rc=$?", 0, "rc=0\n"),
    ("cond_tilde_n", "[[ -n ~ax= ]]; echo rc=$?", 0, "rc=0\n"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _COMPOSITE],
                         ids=[i for i, *_ in _COMPOSITE])
def test_composite_operand_surface(parser, cmd, rc, out):
    assert _run(parser, cmd) == (rc, out)


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _BRACKET_WORD],
                         ids=[i for i, *_ in _BRACKET_WORD])
def test_bracket_word_is_command(parser, cmd, rc, out):
    assert _run(parser, cmd) == (rc, out)


# The ~ax= family is a recursive-descent improvement; assert on rd (and confirm
# the combinator agrees, since fusion feeds both).
@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _RD_TILDE],
                         ids=[i for i, *_ in _RD_TILDE])
def test_tilde_conditional_operand(parser, cmd, rc, out):
    assert _run(parser, cmd) == (rc, out)
