#!/usr/bin/env python3
"""Census of EVERY second-heredoc-grammar site in psh/ (round-1 blocker R4-C).

My round-1 census claimed "two consumers" and was FALSE: it enumerated only
`from ..utils import`-style consumers of the named helpers, so it missed
`psh/interactive/history_expansion.py`, which imports HEREDOC_MARKER_RE
directly and carries a hand-written MIRROR of scan_line_heredoc_markers. A
name-based grep for the helper names cannot find a COPY -- the copy has its own
name.

Three instruments, deliberately different in kind, because the failure was an
under-enumerated universe:

  (A) IMPORTS   -- anything importing from utils.heredoc_detection.
  (B) REGEX USE -- anything referencing HEREDOC_MARKER_RE (the grammar itself),
                   which is how the mirror is reachable at all.
  (C) COPIES    -- structural hunt for re-implementations: any module that
                   (i) names a heredoc/marker-ish scanning function, or
                   (ii) contains a `<<` regex literal of its own, or
                   (iii) says "mirror"/"mirrors" near heredoc code.
                   (C) is the instrument (A) lacked.

Each hit is then classified SESSION-PATH-REACHABLE or not, by asking whether
CommandAccumulator's feed path can reach it.

Usage: python3 second_grammar_census.py
"""
import ast
import pathlib
import re
import subprocess

ROOT = pathlib.Path("/Users/pwilson/src/psh-r2-5")
PSH = ROOT / "psh"


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


print("SHA:", sh("git", "rev-parse", "HEAD"))
print()

# --- (A) imports of the module -------------------------------------------
#
# THE UNIVERSE IS DERIVED, NOT LISTED (fixed at R12-D-AMENDED). The previous
# version counted a DEEP importer (`from ..utils.heredoc_detection import X`)
# for ANY name X, but counted a PACKAGE importer (`from ..utils import X`) only
# when X was one of five hardcoded SCANNER names. So the answer depended on
# IMPORT SPELLING rather than on consumption: unifying session.py's split
# import to the package re-export (R12-A, a cosmetic change ordered by a NIT)
# silently dropped psh/parser/session.py out of the census and took the total
# from 14 to 13 -- a consumer disappearing because of how it spells an import
# is precisely the "instrument must match the claim's UNIVERSE" failure this
# census was BUILT for, one level down.
#
# The name set is now derived from the module's own top-level definitions, so
# it cannot drift from what the module actually exports.
EXPORTED = set()
_mod = ast.parse((PSH / "utils" / "heredoc_detection.py").read_text())
for _n in _mod.body:
    if isinstance(_n, (ast.FunctionDef, ast.ClassDef)):
        EXPORTED.add(_n.name)
    elif isinstance(_n, ast.Assign):
        for _t in _n.targets:
            if isinstance(_t, ast.Name):
                EXPORTED.add(_t.id)
EXPORTED = {n for n in EXPORTED if not n.startswith("_")}

print("=== (A) importers of utils.heredoc_detection ===")
print(f"    [universe: {len(EXPORTED)} exported names, derived from the "
      f"module; import SPELLING is not part of the test]")
a_hits = set()
for py in sorted(PSH.rglob("*.py")):
    if py.name == "heredoc_detection.py":
        continue
    tree = ast.parse(py.read_text())
    for n in ast.walk(tree):
        if not isinstance(n, ast.ImportFrom):
            continue
        names = {al.name for al in n.names}
        deep = "heredoc_detection" in (n.module or "")
        via_pkg = (n.module or "").endswith("utils") and bool(names & EXPORTED)
        if deep or via_pkg:
            a_hits.add(str(py.relative_to(ROOT)))
for h in sorted(a_hits):
    print("   ", h)

# --- (B) uses of the regex itself ----------------------------------------
print("\n=== (B) references to HEREDOC_MARKER_RE (the grammar object) ===")
b = sh("git", "grep", "-n", "HEREDOC_MARKER_RE", "--", "psh/")
print(b or "   (none)")

# --- (C) structural COPY hunt --------------------------------------------
print("\n=== (C) COPIES: re-implementations that never import the helpers ===")
copy_hits = []
FUNC_RE = re.compile(r"heredoc|marker", re.I)
for py in sorted(PSH.rglob("*.py")):
    if py.name == "heredoc_detection.py":
        continue
    src = py.read_text()
    rel = str(py.relative_to(ROOT))
    reasons = []
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and FUNC_RE.search(n.name) and "scan" in n.name.lower():
            reasons.append(f"scanner-shaped fn {n.name}() at :{n.lineno}")
        # A `<<` regex literal of its OWN = its own grammar. Only strings
        # that are actually COMPILED count: the first version tested every
        # string constant, so it reported a "regex literal" at
        # input_preprocessing.py:13, which is a DOCSTRING (round-2 nit 7). A
        # census that invents particulars is worse than one that misses them.
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "compile" \
                and isinstance(getattr(n.func.value, "id", None), str) \
                and n.func.value.id == "re" \
                and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str) \
                and "<<" in n.args[0].value:
            reasons.append(f"own compiled `<<` regex at :{n.lineno}")
    # The word "mirror" alone is far too broad: process_sub.py mirrors a
    # SCOPE-cleanup behaviour and the combinator mirrors the RD PARSER, neither
    # of which is a heredoc grammar. Require the claim to name the heredoc
    # SCANNER specifically (round-3 nit 13 -- the labels were wrong, and a
    # census that mislabels is as bad as one that invents).
    if re.search(r"[Mm]irrors?\b[^.]{0,80}"
                 r"(?:scan_line_heredoc_markers|heredoc_detection|"
                 r"heredoc scanner)", src):
        reasons.append("says it MIRRORS the heredoc SCANNER by name")
    if reasons:
        copy_hits.append((rel, reasons))
for rel, reasons in copy_hits:
    print(f"    {rel}")
    for r in reasons:
        print(f"        - {r}")
if not copy_hits:
    print("    (none)")

print("\n=== UNION (derived) ===")
union = sorted(a_hits | {l.split(":")[0] for l in b.splitlines() if l}
               | {r for r, _ in copy_hits})
for u in union:
    print("   ", u)
print("TOTAL DISTINCT SITES:", len(union))
