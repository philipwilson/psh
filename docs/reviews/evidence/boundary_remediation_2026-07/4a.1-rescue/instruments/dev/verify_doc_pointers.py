"""Hand-run verification of the `file.py#symbol` pointers slot 4A.1 wrote.

Required by the brief: `tests/unit/tooling/test_doc_pointers.py` resolves
repo-rooted paths, relative .py paths, `Class.member` and bare `function()`,
but has NO rule that validates the SYMBOL half of a `file.py#symbol`
pointer, so a pointer naming a symbol that does not exist would pass the
suite. Until the D-3.5-s1 successor lands, this checks them by parsing the
named file's AST and looking the symbol up.

    python verify_doc_pointers.py           # every psh/**/CLAUDE.md
"""
import ast
import os
import re
import sys

ROOT = "/Users/pwilson/src/psh-r4a-1"

#: `path/to/file.py#Symbol`, `#Class.method`, optionally backticked.
POINTER = re.compile(r"`([A-Za-z0-9_./]+\.py)#([A-Za-z_][A-Za-z0-9_.]*)`")


def symbols_of(path):
    """Every top-level and nested-in-class name the module defines."""
    with open(path) as fh:
        tree = ast.parse(fh.read())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}.{sub.name}")
                    names.add(sub.name)          # bare-method spelling
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            names.add(f"{node.name}.{t.id}")
                if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                    names.add(f"{node.name}.{sub.target.id}")
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


#: A backticked pointer whose identifier got WRAPPED across a line break —
#: `#ProcessLease\nCoordinator.find_component` renders as a symbol with a
#: space in it and resolves to nothing. Cheap to check, and it caught a real
#: instance in this slot's own prose.
#: Restricted to POINTER-shaped content (leading `#`, or a `.py#` prefix):
#: an earlier draft matched any backticked two-word phrase spanning a line
#: break and reported ordinary prose like `except\nPshError` as broken.
WRAPPED = re.compile(r"`(?:[A-Za-z0-9_./]+\.py)?#[A-Za-z_][A-Za-z0-9_.]*\s*\n\s*"
                     r"[A-Za-z0-9_.]+`")

#: A bare `#symbol` continuation, the established convention after a full
#: pointer has named the file (see psh/expansion/CLAUDE.md). Resolved
#: against the most recently named .py file in the same document.
BARE = re.compile(r"`#([A-Za-z_][A-Za-z0-9_.]*)`")


def check_bare_and_wrapped(doc, rel_doc, text):
    """Returns (checked, bad) for the two rules the main loop does not cover."""
    checked = bad = 0
    for match in WRAPPED.finditer(text):
        line = text[:match.start()].count("\n") + 1
        print(f"WRAPPED SYMBOL {rel_doc}:{line}: {match.group(0)!r}")
        bad += 1
    current = None
    for match in re.finditer(r"`([A-Za-z0-9_./]+\.py)#|`#([A-Za-z_][A-Za-z0-9_.]*)`",
                             text):
        if match.group(1):
            current = match.group(1)
            continue
        symbol = match.group(2)
        if current is None:
            continue                      # no file named yet: not a pointer
        checked += 1
        matches = [os.path.join(dp, fn)
                   for base in ("psh", "tests")
                   for dp, _d, fs in os.walk(os.path.join(ROOT, base))
                   for fn in fs
                   if os.path.join(dp, fn).endswith(os.sep + current)]
        if not matches:
            continue
        names = symbols_of(matches[0])
        if symbol not in names and symbol.split('.')[-1] not in names:
            line = text[:match.start()].count("\n") + 1
            print(f"MISSING BARE   {rel_doc}:{line}: {current}#{symbol}")
            bad += 1
    return checked, bad


def main():
    docs = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "psh")):
        for name in files:
            if name == "CLAUDE.md":
                docs.append(os.path.join(dirpath, name))
    checked = bad = 0
    for doc in sorted(docs):
        rel_doc = os.path.relpath(doc, ROOT)
        text = open(doc).read()
        extra_checked, extra_bad = check_bare_and_wrapped(doc, rel_doc, text)
        checked += extra_checked
        bad += extra_bad
        for match in POINTER.finditer(text):
            target, symbol = match.group(1), match.group(2)
            checked += 1
            # Resolve relative to the doc's own package first, then repo root.
            candidates = [os.path.join(os.path.dirname(doc), target),
                          os.path.join(ROOT, target),
                          os.path.join(ROOT, "psh", target)]
            path = next((c for c in candidates if os.path.isfile(c)), None)
            if path is None:
                # A doc may legitimately point at a file in ANOTHER package
                # (io_redirect's doc naming interactive/signal_manager.py).
                # Search the tree by path suffix before calling it drift —
                # otherwise this instrument reports its own resolution
                # limits as documentation rot.
                matches = [os.path.join(dp, fn)
                           for base in ("psh", "tests")
                           for dp, _d, fs in os.walk(os.path.join(ROOT, base))
                           for fn in fs
                           if os.path.join(dp, fn).endswith(os.sep + target)]
                path = matches[0] if len(matches) >= 1 else None
            if path is None:
                print(f"MISSING FILE  {rel_doc}: {target}#{symbol}")
                bad += 1
                continue
            names = symbols_of(path)
            if symbol not in names and symbol.split('.')[-1] not in names:
                print(f"MISSING SYMBOL {rel_doc}: {target}#{symbol}")
                bad += 1
    print(f"\nDERIVED: pointers checked = {checked}, unresolved = {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
