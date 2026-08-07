"""Hand-run verification for the `file.py#symbol` pointers this slot adds.

`tests/unit/tooling/test_doc_pointers.py` has no rule for the `#symbol` form
yet (D-3.5-s1), so the brief requires the pointers to carry their own scripted
check. Resolves THREE forms, because earlier versions of this script produced
two false results by handling fewer:
  * `module.py#Class.method` — qualified
  * `#Symbol` / `#Class.method` — bare, resolved against EVERY module in the
    package (a first version hard-coded one module and reported a pre-existing
    signal_manager pointer as broken)
  * attributes (`#HistoryManager._owed`) — matched as `self.<name>` assignments,
    not only as `def`/`class` (a second version knew only def/class and reported
    a real attribute pointer as broken)
"""
import pathlib
import re
import sys

PKG = pathlib.Path(__file__).resolve().parents[2] / 'psh' / 'interactive'
doc = (PKG / 'CLAUDE.md').read_text()
sources = {p.name: p.read_text() for p in PKG.glob('*.py')}


def defines(src: str, leaf: str) -> bool:
    return (f"def {leaf}" in src or f"class {leaf}" in src
            or re.search(rf"self\.{re.escape(leaf)}\s*[:=]", src) is not None)


bad = []
qualified = set(re.findall(r'`([a-z_]+\.py)#([A-Za-z_.]+)`', doc))
for fname, sym in sorted(qualified):
    leaf = sym.split('.')[-1]
    if fname not in sources:
        bad.append(f"{fname}#{sym}: no such module")
    elif not defines(sources[fname], leaf):
        bad.append(f"{fname}#{sym}: {leaf} not defined in {fname}")

bare = set(re.findall(r'`#([A-Za-z_][A-Za-z_.]*)`', doc))
for sym in sorted(bare):
    leaf = sym.split('.')[-1]
    if not any(defines(src, leaf) for src in sources.values()):
        bad.append(f"#{sym}: {leaf} not defined anywhere in psh/interactive/")

repo = pathlib.Path(__file__).resolve().parents[2]
# ONE regex, used for both the count and the existence check. A second,
# over-escaped copy of it previously reported "referenced test files: 0" beside
# a correct "MISSING: NONE" — a display number that was quietly wrong while the
# check beside it was right.
TEST_REF = re.compile(r'`(tests/[^`]+\.py)`')
test_refs = sorted(set(TEST_REF.findall(doc)))
missing = [m for m in test_refs if not (repo / m).exists()]

print(f"qualified pointers: {len(qualified)}   bare pointers: {len(bare)}")
print(f"referenced test files: {len(test_refs)}")
print("POINTER FAILURES:", bad or "NONE")
print("MISSING TEST FILES:", missing or "NONE")
sys.exit(1 if (bad or missing) else 0)
