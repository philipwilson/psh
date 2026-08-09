#!/usr/bin/env python3
"""B2 — emit the hub-ledger LEDGER literal from the A14 disposition matrix.

Hand-typing 60 rows into the guard is exactly the transcription step that
produces read-it-off errors, so the literal is GENERATED from the matrix that
was already reviewed, and the guard's own arms then re-derive every number from
the tree. Nominal/executable figures are NOT baked in — the guard measures them
— so this only emits (file, qualname) -> (disposition, reason).

Usage: B2_emit_ledger.py > ledger_literal.py
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a14", HERE / "A14_disposition_matrix.py")
sys.argv = ["a14", str(HERE / "A1_census_base.json"), "/Users/pwilson/src/psh-r5c-2"]
mod = importlib.util.module_from_spec(spec)

# A14 prints its report on import; suppress that, we only want its M table.
import contextlib
import io
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(mod)

M = mod.M

import re

print("LEDGER = {")
for (f, q), (txn, shape, disp, why) in sorted(M.items()):
    # Strip any leading "NN exec;" / "NN exec," figure: the GUARD measures
    # executable length and reports it, so a number frozen into the reason
    # text is a stale-figure hazard of exactly the kind this ledger exists
    # to catch. The prose keeps the argument, the guard keeps the count.
    reason = re.sub(r"^\d+\s+exec[;,]\s*", "", why)
    reason = reason[0].upper() + reason[1:] if reason else reason

    print(f"    ({f!r},")
    print(f"     {q!r}):")
    print(f"        ({disp!r},")
    # wrap at ~66 chars; each fragment keeps its trailing space so adjacent
    # string literals concatenate into readable prose, not run-on words.
    words = reason.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 66:
            lines.append(cur + " ")
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    for i, ln in enumerate(lines):
        suffix = ")," if i == len(lines) - 1 else ""
        print(f"         {ln!r}{suffix}")
print("}")
