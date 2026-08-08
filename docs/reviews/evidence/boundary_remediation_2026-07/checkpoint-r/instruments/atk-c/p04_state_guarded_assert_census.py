#!/usr/bin/env python3
"""atk-c p04: Gap 5 — fresh re-sweep of MEDIUM-13's companion claim
"state-guarded-assert census 1 -> 0 tree-wide".

Recorded definition (1.3-rescue/slot-ledger.md): flag asserts inside an `if`
with NO `else`; the STATE class = predicate reads runtime state the code under
test produces (the sole base-era member was
`if os.path.exists('bg_output.txt'):` in
tests/integration/subshells/test_subshell_basics.py::test_subshell_with_background_jobs).
At tip after the 1.3 fixes the recorded census was STATE=0, OTHER=26.

This is a FRESH instrument (original tmp/census_guarded_assert.py is not in
the tree). Classifier: predicate that syntactically reads external runtime
state — os.path.exists/isfile/isdir, Path(...).exists(), os.access,
psutil/proc checks — is STATE; every other else-less guarded assert is OTHER.
All hits are printed with their predicate so the classification is auditable.
Run from the worktree root: python3 p04_state_guarded_assert_census.py tests
"""
import ast
import os
import sys

STATE_CALL_ATTRS = {"exists", "isfile", "isdir", "islink", "access", "lexists"}


def pred_is_state(test: ast.expr) -> bool:
    for node in ast.walk(test):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in STATE_CALL_ATTRS:
                return True
            if isinstance(f, ast.Name) and f.id in STATE_CALL_ATTRS:
                return True
    return False


def contains_assert(stmts) -> bool:
    for s in stmts:
        for node in ast.walk(s):
            if isinstance(node, ast.Assert):
                return True
    return False


def main(root: str) -> None:
    state_hits, other_hits = [], []
    nfiles = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__",)]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            nfiles += 1
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except SyntaxError as e:
                print(f"[PARSE-ERROR] {path}: {e}")
                continue
            # attach enclosing function names
            func_of = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for child in ast.walk(node):
                        func_of.setdefault(child, node.name)
            for node in ast.walk(tree):
                if isinstance(node, ast.If) and not node.orelse and contains_assert(node.body):
                    pred = ast.unparse(node.test)
                    fname = func_of.get(node, "<module>")
                    rec = (path, node.lineno, fname, pred)
                    (state_hits if pred_is_state(node.test) else other_hits).append(rec)
    print(f"files scanned: {nfiles}")
    print(f"--- STATE-guarded asserts: {len(state_hits)} ---")
    for p, ln, fn, pred in state_hits:
        print(f"[STATE] {p}:{ln}: {fn}   if {pred}:")
    print(f"--- OTHER-guarded asserts: {len(other_hits)} ---")
    for p, ln, fn, pred in other_hits:
        print(f"[OTHER] {p}:{ln}: {fn}   if {pred}:")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tests")
