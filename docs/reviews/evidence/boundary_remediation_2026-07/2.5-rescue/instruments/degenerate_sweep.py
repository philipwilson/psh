#!/usr/bin/env python3
"""DEGENERATE-AXIS SWEEP of both fd-prefix tables (round-4 blocker R10-A).

Every redirect operator in the named-fd and digit-fd tables, x operand
PRESENT / ABSENT, through the completeness oracle. The operand-absent corner is
the one the round-3 fix changed without anybody looking: an operator arm's
whole input space is the universe, INCLUDING its empty corner.

Usage: python3 degenerate_sweep.py <tree> <label>
"""
import sys

TREE = sys.argv[1]
LABEL = sys.argv[2]
sys.path.insert(0, TREE)

from psh.scripting.command_accumulator import CommandAccumulator, NeedMore  # noqa: E402
from psh.shell import Shell  # noqa: E402

_OPS = ["<<", "<<-", "<<<", "<", ">", ">>", "<>", ">|"]
_PREFIXES = [("plain", ""), ("digit", "0"), ("named", "{v}")]

print(f"=== {LABEL} ({TREE}) ===")
print(f"{'shape':26} {'operand':8} outcome")
for pname, prefix in _PREFIXES:
    for op in _OPS:
        for operand, oname in ((" EOF", "present"), ("", "ABSENT")):
            line = f"cat {prefix}{op}{operand}"
            sh = Shell(norc=True)
            acc = CommandAccumulator(sh)
            try:
                r = acc.feed(line)
                if isinstance(r, NeedMore):
                    out = f"NeedMore/{r.hint.kind.name}"
                else:
                    out = "Complete" + ("+ERROR" if r.error else "")
            except Exception as e:                            # noqa: BLE001
                out = f"RAISED {type(e).__name__}"
            print(f"{line:26} {oname:8} {out}")
