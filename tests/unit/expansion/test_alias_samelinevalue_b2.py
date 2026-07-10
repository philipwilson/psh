"""B2 regression pins: same-line ``alias name=value; name`` keeps the value's
``$`` on a SIMPLE variable (both parsers).

psh expands a same-line alias definition-and-use (a psh feature; bash does not
expand an alias defined in the same parse unit). The overlay rebuilds the alias
value from the fused WORD's parts. Word fusion (v0.682.0) stores a SIMPLE
variable part as its bare NAME (``$v`` -> part value ``v``), so the old
concatenation dropped the ``$`` and ``alias e="echo pre$v"; e`` printed ``prev``
instead of ``preVAL``. The delimited expansions (``${v}``, ``$(...)``,
``$((...))``, backtick) keep their full source in the part value and were
unaffected. The fix re-prefixes ``$`` for variable-etype parts.

Reference values are the base (pre-fusion) psh behavior, which equals bash with
``shopt -s expand_aliases`` when the alias is defined on its OWN line (verified
here: preVAL / VALpost / xVALy / a3b / pVALq). The simple-``$v`` cases were RED
on the shipped SHA 3f5f3119 (printed the ``$``-stripped value).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

# (id, same-line command, expected stdout). psh expands the same-line alias.
_CASES = [
    # --- simple $var: the B2 regression (RED on 3f5f3119: '$' dropped) ---
    ("simple_var", 'v=VAL; alias e="echo pre$v"; e', "preVAL\n"),
    ("two_simple_vars", 'a=A; b=B; alias e="echo $a$b"; e', "AB\n"),
    ("var_between_literals", 'v=MID; alias e="echo [$v]"; e', "[MID]\n"),
    ("special_var_status", 'true; alias e="echo $?"; e', "0\n"),
    ("mixed_simple_and_braced", 'v=V; alias e="echo ${v}x $v-y"; e', "Vx V-y\n"),
    # --- delimited expansions: must STAY correct (source already in value) ---
    ("braced_var", 'v=VAL; alias e="echo ${v}post"; e', "VALpost\n"),
    ("command_sub", 'v=VAL; alias e="echo x$(echo $v)y"; e', "xVALy\n"),
    ("arith_sub", 'alias e="echo a$((1+2))b"; e', "a3b\n"),
    ("backtick_sub", 'v=VAL; alias e="echo p`echo $v`q"; e', "pVALq\n"),
    # --- plain literal value: unchanged ---
    ("plain_literal", 'alias e="echo hi"; e', "hi\n"),
]


def _run(parser, cmd):
    argv = [sys.executable, "-m", "psh"]
    if parser:
        argv += ["--parser", parser]
    p = subprocess.run(argv + ["-c", cmd], capture_output=True, text=True, cwd=_REPO)
    return p.returncode, p.stdout


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("cmd,expected",
                         [(c, e) for _, c, e in _CASES],
                         ids=[i for i, *_ in _CASES])
def test_same_line_alias_value_source_faithful(parser, cmd, expected):
    rc, out = _run(parser, cmd)
    assert (rc, out) == (0, expected)
