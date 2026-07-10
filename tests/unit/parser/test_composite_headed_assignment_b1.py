"""B1 regression pins: a composite word is NOT an array assignment (both parsers).

Word fusion (v0.682.0) merges a quoted/expansion PREFIX into one WORD, and the
array-assignment classifier keyed off the raw fused value — so `"q"a[0]=v`,
`${v}a[0]=v`, `a[0]$x=y` were silently array-ified (rc 0) though bash runs them
as a command (rc 127) or syntax-errors (rc 2). The fix guards the classifier to
require the head (NAME[subscript]op / NAME=() to be a valid identifier in the
word's UNQUOTED LEADING LITERAL. These pins were RED on the shipped SHA
3f5f3119 (both parsers rc 0) and match bash 5.2 here.

Every case is bash-5.2 verified (v, d unset). rc + stdout are asserted against
bash's exact values; both the recursive-descent and combinator parsers must match.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, command, bash_rc, bash_stdout) — a composite/expansion-headed word is a
# COMMAND (rc 127 not found) or a SYNTAX ERROR (rc 2), never an assignment.
_NOT_ASSIGNMENT = [
    ("dquote_prefix_element", '"q"a[0]=v', 127, ""),
    ("dquote_prefix_str_subscript", '"q"a["k"]=v', 127, ""),
    ("braced_var_prefix_element", '${v}a[0]=v', 127, ""),
    ("ansic_prefix_element", "p$'q'[0]=v", 127, ""),
    ("expansion_split_operator", 'a[0]$x=y', 127, ""),
    ("dquote_prefix_append", '"q"a[0]+=v', 127, ""),
    ("var_prefix_element", 'x=a; $x[0]=v', 127, ""),
    ("dquote_prefix_initializer", '"q"a=(1 2)', 2, ""),
    ("expansion_prefix_initializer", 'a$x=(1 2)', 2, ""),
    ("empty_name_initializer", 'a =(1 2)', 2, ""),
]

# Positive controls: the guard must NOT over-reject genuine array assignments.
_STILL_ASSIGNMENT = [
    ("plain_element", 'a[0]=v; printf %s "${a[0]}"', 0, "v"),
    ("indexed_init", 'arr=(1 2 3); printf %s "${arr[1]}"', 0, "2"),
    ("assoc_init", 'declare -A m=([k]=v); printf %s "${m[k]}"', 0, "v"),
    ("append_init", 'a+=(9); printf %s "${a[0]}"', 0, "9"),
    ("expansion_value_element", 'a[0]=pre$x"y"; printf %s "${a[0]}"', 0, "prey"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _NOT_ASSIGNMENT],
                         ids=[i for i, *_ in _NOT_ASSIGNMENT])
def test_composite_headed_word_is_not_array_assignment(parser, cmd, rc, out):
    got_rc, got_out = _run(parser, cmd)
    assert (got_rc, got_out) == (rc, out)


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,rc,out",
                         [(c, rc, o) for _, c, rc, o in _STILL_ASSIGNMENT],
                         ids=[i for i, *_ in _STILL_ASSIGNMENT])
def test_valid_array_assignment_still_parses(parser, cmd, rc, out):
    got_rc, got_out = _run(parser, cmd)
    assert (got_rc, got_out) == (rc, out)
