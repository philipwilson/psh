#!/usr/bin/env python3
"""C1 — MEASUREMENT for R15's guard-widening ruling: how big is the blind spot?

The blocker (`docs/architecture/ast_data_flow.md:252`, a dangling
`io_manager.with_redirections(node.redirects)`) landed silently because the
doc-pointer guard's R4 matcher is

    CALL_RE = ^([a-z_][A-Za-z0-9_]*)\\(\\)$

— a BARE lowercase name with EMPTY parens. A cite that is DOTTED
(`obj.method(...)`) or ARGUMENT-BEARING (`name(arg)`) matches neither R4 nor
R3's DOTTED_RE (which needs `ClassName.member`, capitalised). It is invisible.

This measures a widened matcher over the guard's OWN DOC_FILES, reusing the
guard's own tokenizer (same fence-stripping, same inline-code extraction) so the
measurement shares the claim's substrate rather than approximating it.

Reported, per R15: HIT count (tokens the widening newly SEES) and WOULD-FAIL
count (of those, the ones whose callable resolves nowhere in the corpus). Small
⇒ widen in-slot, offender-proven. Large ⇒ successor row with this measurement
attached. The ruling is the integrator's; this only supplies the number.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path("/Users/pwilson/src/psh-r5c-2")
GUARD = ROOT / "tests/unit/tooling/test_doc_pointers.py"

spec = importlib.util.spec_from_file_location("dp", GUARD)
dp = importlib.util.module_from_spec(spec)
sys.modules["dp"] = dp
spec.loader.exec_module(dp)

# Same corpus the guard builds.
corpus = {}
for base in ("psh", "tests", "tools"):
    for p in (ROOT / base).rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        corpus[p] = p.read_text(encoding="utf-8", errors="replace")

# WIDENED matcher: optional dotted head, callable name, ANY argument text.
WIDE_RE = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*([a-z_][A-Za-z0-9_]*)\((.*)\)$")

already_seen = 0
new_hits = []
for doc in dp.DOC_FILES:
    text = dp.FENCE_RE.sub("", doc.read_text(encoding="utf-8"))
    for token in dp.INLINE_CODE_RE.findall(text):
        tok = token.strip()
        if dp.CALL_RE.match(tok) or dp.DOTTED_RE.match(tok):
            already_seen += 1
            continue
        m = WIDE_RE.match(tok)
        if not m:
            continue
        name = m.group(1)
        if name in getattr(dp, "OS_CALLS", ()):
            continue
        if tok in getattr(dp, "EXEMPT", ()):
            continue
        resolves = any(f"def {name}(" in t for t in corpus.values())
        new_hits.append((doc.relative_to(ROOT).as_posix(), tok, name, resolves))

would_fail = [h for h in new_hits if not h[3]]

print("=== R15 guard-widening measurement")
print(f"DOC_FILES scanned              : {len(dp.DOC_FILES)}")
print(f"tokens ALREADY matched (R3/R4) : {already_seen}")
print(f"NEW HITS the widening sees     : {len(new_hits)}")
print(f"of those, WOULD-FAIL           : {len(would_fail)}")

print("\n--- WOULD-FAIL (callable resolves to no `def name(` anywhere)")
if not would_fail:
    print("   NONE")
for rel, tok, name, _ in sorted(would_fail):
    print(f"   {rel}\n      `{tok}`   (callable: {name})")

print(f"\n--- NEW HITS THAT RESOLVE (would pass; listed for scale) "
      f"[{len(new_hits) - len(would_fail)}]")
for rel, tok, name, ok in sorted(new_hits):
    if ok:
        print(f"   {rel}: `{tok}`")
