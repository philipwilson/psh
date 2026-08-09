#!/usr/bin/env python3
"""B12 — the category-gap sweep R10 requires: which guards key on SOURCE TEXT
inside the six seam files, and are their arms still FUNCTIONAL?

My D2.1 §1 moved-key enumeration covered three LEDGER guards and concluded
"zero keys move". It missed an entire category — MUTATION ANCHORS, which key
on source text rather than on a symbol name — and seam 6 proved the gap live:
the anchor was still PRESENT (so the presence test passed) while the arm had
stopped working, because deleting the line no longer produced a valid tree.

anchor-present != arm-functional. This enumerates the category so the claim is
measured rather than assumed.

Method: parse every module under tests/unit/tooling/, collect every string
literal >= 12 characters that also occurs verbatim in one of the six seam
files, and report it with its owning module. Long literals are the practical
signature of a source-text anchor; the report is then read by hand, because
the question "is this an anchor" is a judgement the sweep should surface, not
silently answer.

FUNCTIONALITY is proven separately and by execution: running the full
tests/unit/tooling suite at this commit exercises every mutation lock, and a
mutation that no longer applies fails there — which is exactly how seam 6's
gap surfaced.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path("/Users/pwilson/src/psh-r5c-2")
TOOLING = ROOT / "tests/unit/tooling"

SEAM_FILES = [
    "psh/builtins/parse_tree.py",
    "psh/builtins/test_command.py",
    "psh/builtins/print_builtin.py",
    "psh/lexer/recognizers/operator.py",
    "psh/invocation.py",
    "psh/io_redirect/file_redirect.py",
]

sources = {rel: (ROOT / rel).read_text() for rel in SEAM_FILES}

MIN_LEN = 12
hits = []
for path in sorted(TOOLING.glob("*.py")):
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if len(text.strip()) < MIN_LEN:
                continue
            for rel, src in sources.items():
                if text in src:
                    hits.append((path.name, node.lineno, rel, text))

print(f"=== source-text anchors from tests/unit/tooling/ found inside the "
      f"six seam files (literals >= {MIN_LEN} chars)")
if not hits:
    print("  NONE")
by_mod = {}
for mod, line, rel, text in hits:
    by_mod.setdefault(mod, []).append((line, rel, text))
for mod in sorted(by_mod):
    print(f"\n## {mod}")
    for line, rel, text in sorted(by_mod[mod]):
        shown = text if len(text) <= 78 else text[:75] + "..."
        print(f"   :{line}  -> {rel}")
        print(f"      {shown!r}")

print(f"\n=== TOTAL candidates: {len(hits)} across {len(by_mod)} tooling module(s)")

# DISCRIMINATOR. Most hits are SYMBOL names ('AttributeError', 'TYPE_CHECKING'):
# a guard keyed on a symbol survives a move, because the symbol moves with it.
# A MUTATION anchor is a full source LINE — it carries leading indentation and
# a trailing newline — and that is the shape whose arm can silently stop
# working when surrounding structure changes, which is the gap seam 6 proved.
def is_source_line(text):
    return text.endswith("\n") and (text.startswith(" ") or text.startswith("\t"))


lines = [(m, ln, rel, t) for m, ln, rel, t in hits if is_source_line(t)]
symbols = [h for h in hits if not is_source_line(h[3])]

print(f"\n=== CLASSIFIED")
print(f"  SOURCE-LINE anchors (mutation-shaped, the at-risk category): {len(lines)}")
for mod, ln, rel, text in sorted(lines):
    print(f"      {mod}:{ln} -> {rel}\n        {text!r}")
print(f"  SYMBOL-NAME references (move WITH the symbol, not at risk): {len(symbols)}")

print("\nArm FUNCTIONALITY is proven by EXECUTION, not by this listing: the full")
print("tests/unit/tooling suite runs every mutation lock at this commit, and a")
print("mutation that no longer applies fails there — which is how seam 6's gap")
print("surfaced in the first place.")
sys.exit(0)
