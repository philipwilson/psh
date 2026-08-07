#!/usr/bin/env python3
"""4A.2 doc-pointer verification (D-3.5-s1 hand-run instrument).

`tests/unit/tooling/test_doc_pointers.py` has no rule for the `file.py#symbol`
form yet, so this slot's pointers get a scripted check of their own rather than
a hand assurance.  Every `path.py#Symbol` and every test-file path in the
section 4A.2 added to `psh/core/CLAUDE.md` is resolved against the tree and its
symbol looked up by AST -- not by grepping for the name, which would match a
mention in a comment.

House convention in that file (confirmed against pre-existing pointers such as
`scope.py#ScopeManager` and `executor/child_policy.py#map_child_exception`):
paths are relative to `psh/`, or to `psh/core/` for a bare filename; test-tree
paths are repo-relative.

    python tmp/w4a2-probes/verify_doc_pointers.py     # exit 0 = all resolve
"""
import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "psh" / "core" / "CLAUDE.md"
SECTION_START = "### Shutdown phases"
SECTION_END = "### Terminal Detection"

#: Bare identifiers the prose names, and the file each must appear in.
IDENTS = [
    ("_HISTORY_SAVING_SHUTDOWNS", "psh/shell.py"),
    ("shutdown('signal-hup')", "psh/interactive/signal_manager.py"),
]


def resolve(path: str):
    for cand in (ROOT / path, ROOT / "psh" / path, ROOT / "psh" / "core" / path):
        if cand.is_file():
            return cand
    return None


def main() -> int:
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"# tree: {ROOT}  tip: {sha}")
    text = DOC.read_text()
    start = text.index(SECTION_START)
    section = text[start:text.index(SECTION_END, start)]

    bad: list[str] = []
    checked = 0
    for path, symbol in re.findall(r"`([\w/\.]+\.(?:py|md))(?:#([\w\.]+))?`",
                                   section):
        target = resolve(path)
        if target is None:
            bad.append(f"MISSING FILE {path}")
            continue
        checked += 1
        if not symbol:
            print(f"ok  file   {path}")
            continue
        names = {node.name for node in ast.walk(ast.parse(target.read_text()))
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef))}
        if symbol.split(".")[-1] in names:
            print(f"ok  symbol {path}#{symbol}")
        else:
            bad.append(f"MISSING SYMBOL {path}#{symbol}")

    for ident, where in IDENTS:
        checked += 1
        if ident in (ROOT / where).read_text():
            print(f"ok  ident  {ident!r} in {where}")
        else:
            bad.append(f"MISSING IDENT {ident} in {where}")

    print(f"\nchecked={checked} failures={len(bad)}")
    for item in bad:
        print(f"  {item}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
