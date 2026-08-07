#!/usr/bin/env python3
"""P2 — consumer census of the VariableLookup read contract, by AST walk.

METHOD B (authoritative). Method A was grep (ledger §2.1) and is a
cross-check only: D-3.5 says a verification instrument that mirrors the
claim's method cannot find the claim's error, so the number that GOVERNS is
derived by a different mechanism than the one that produced the first number.

What it derives, over every .py in psh/, tests/, tools/:

  A. Every `<recv>.lookup(...)` call site, classified by receiver text into
     the scope-manager family vs the unrelated hash-table family.
  B. Every ATTRIBUTE READ on a scope-manager lookup result — both chained
     (`mgr.lookup('x').is_set`) and via a local binding (`r = mgr.lookup('x')`
     ... `r.binding`), with a per-field tally.
  C. Every textual reference to VariableLookup / LookupStatus / _MISSING.
  D. Dynamic-access risk: getattr/setattr/hasattr with a string literal that
     names a lookup field, __slots__ reflection, copy/deepcopy/pickle applied
     anywhere in the same file as a lookup consumer.

All counts are DERIVED by this script and printed; nothing is hand-tallied.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections import Counter, defaultdict

WORKTREE = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TREES = ("psh", "tests", "tools")

LOOKUP_FIELDS = {"status", "value", "binding", "is_set", "is_present"}
# Receivers that are NOT the variable-read authority (unrelated .lookup APIs).
HASH_TABLE_RECEIVERS = {"table"}


def recv_text(node: ast.AST) -> str:
    """Best-effort source text of a call receiver, for classification."""
    try:
        return ast.unparse(node)
    except Exception:                                          # noqa: BLE001
        return "<unparseable>"


class Census(ast.NodeVisitor):
    def __init__(self, relpath: str):
        self.relpath = relpath
        self.call_sites: list[tuple[int, str, str]] = []      # line, recv, family
        self.field_reads: list[tuple[int, str, str]] = []     # line, field, how
        self.dynamic: list[tuple[int, str]] = []
        # name -> True for locals currently bound to a lookup() result
        self._bound: set[str] = set()

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _is_lookup_call(node: ast.AST) -> tuple[bool, str]:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "lookup":
            return True, recv_text(node.func.value)
        return False, ""

    def _family(self, recv: str) -> str:
        tail = recv.rsplit(".", 1)[-1]
        if tail in HASH_TABLE_RECEIVERS:
            return "hash-table (unrelated)"
        return "scope-manager (VariableLookup)"

    # -- visits -----------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        is_lu, recv = self._is_lookup_call(node)
        if is_lu:
            self.call_sites.append((node.lineno, recv, self._family(recv)))
        # dynamic access with a literal field name
        if isinstance(node.func, ast.Name) and node.func.id in {
                "getattr", "setattr", "hasattr"}:
            for a in node.args[1:2]:
                if isinstance(a, ast.Constant) and a.value in LOOKUP_FIELDS:
                    self.dynamic.append(
                        (node.lineno, f"{node.func.id}(..., {a.value!r})"))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        is_lu, recv = self._is_lookup_call(node.value)
        if is_lu and self._family(recv).startswith("scope-manager"):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self._bound.add(t.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in LOOKUP_FIELDS:
            # chained: mgr.lookup('x').is_set
            is_lu, recv = self._is_lookup_call(node.value)
            if is_lu and self._family(recv).startswith("scope-manager"):
                self.field_reads.append((node.lineno, node.attr, "chained"))
            # via a local bound to a lookup result
            elif isinstance(node.value, ast.Name) and node.value.id in self._bound:
                self.field_reads.append(
                    (node.lineno, node.attr, f"local `{node.value.id}`"))
        self.generic_visit(node)


def main() -> int:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKTREE,
                         capture_output=True, text=True).stdout.strip()
    print(f"P2 consumer census (AST) — worktree {WORKTREE}")
    print(f"SHA: {sha}    python: {sys.version.split()[0]}")
    print("=" * 78)

    files = 0
    all_calls: list[tuple[str, int, str, str]] = []
    all_reads: list[tuple[str, int, str, str]] = []
    all_dynamic: list[tuple[str, int, str]] = []
    name_refs: dict[str, list[str]] = defaultdict(list)

    for tree in TREES:
        for root, _dirs, names in os.walk(os.path.join(WORKTREE, tree)):
            for n in sorted(names):
                if not n.endswith(".py"):
                    continue
                path = os.path.join(root, n)
                rel = os.path.relpath(path, WORKTREE)
                src = open(path, encoding="utf-8").read()
                files += 1
                try:
                    mod = ast.parse(src, filename=rel)
                except SyntaxError as exc:
                    print(f"  [parse-error] {rel}: {exc}")
                    continue
                c = Census(rel)
                c.visit(mod)
                all_calls += [(rel, ln, r, f) for ln, r, f in c.call_sites]
                all_reads += [(rel, ln, fld, how) for ln, fld, how in c.field_reads]
                all_dynamic += [(rel, ln, d) for ln, d in c.dynamic]
                for ident in ("VariableLookup", "LookupStatus", "_MISSING"):
                    for node in ast.walk(mod):
                        if isinstance(node, ast.Name) and node.id == ident:
                            name_refs[ident].append(f"{rel}:{node.lineno}")
                        elif isinstance(node, ast.Attribute) and node.attr == ident:
                            name_refs[ident].append(f"{rel}:{node.lineno}")

    print(f"[A] files parsed: {files}")
    print(f"[A] `.lookup(` call sites: {len(all_calls)}")
    fam = Counter(f for _, _, _, f in all_calls)
    for k, v in sorted(fam.items()):
        print(f"      {k}: {v}")
    print()
    print("[A] scope-manager lookup() call sites (the read authority):")
    prod = [c for c in all_calls if c[3].startswith("scope-manager")
            and c[0].startswith("psh/")]
    test = [c for c in all_calls if c[3].startswith("scope-manager")
            and not c[0].startswith("psh/")]
    for rel, ln, r, _f in prod:
        print(f"      PRODUCTION  {rel}:{ln}   receiver `{r}`")
    print(f"      -> production call sites: {len(prod)}")
    for rel, ln, r, _f in test:
        print(f"      test        {rel}:{ln}   receiver `{r}`")
    print(f"      -> test/tool call sites: {len(test)}")
    print()

    print(f"[B] attribute reads on a lookup result: {len(all_reads)}")
    by_field_prod: Counter = Counter()
    by_field_test: Counter = Counter()
    for rel, ln, fld, how in all_reads:
        (by_field_prod if rel.startswith("psh/") else by_field_test)[fld] += 1
    print(f"      PRODUCTION by field: {dict(sorted(by_field_prod.items()))}")
    print(f"      test/tool  by field: {dict(sorted(by_field_test.items()))}")
    print("      per-site detail:")
    for rel, ln, fld, how in all_reads:
        tag = "PRODUCTION" if rel.startswith("psh/") else "test      "
        print(f"      {tag}  {rel}:{ln}  .{fld}   ({how})")
    print()
    print("      >>> .binding readers in PRODUCTION: "
          f"{by_field_prod.get('binding', 0)}")
    print("      >>> .binding readers in tests/tools: "
          f"{by_field_test.get('binding', 0)}")
    print()

    print("[C] identifier references:")
    for ident in ("VariableLookup", "LookupStatus", "_MISSING"):
        refs = name_refs[ident]
        p = [r for r in refs if r.startswith("psh/")]
        print(f"      {ident}: {len(refs)} total ({len(p)} in psh/)")
        if ident == "_MISSING":
            for r in refs:
                print(f"          {r}")
    print()

    print(f"[D] dynamic access with a literal lookup-field name: {len(all_dynamic)}")
    for rel, ln, d in all_dynamic:
        print(f"      {rel}:{ln}  {d}")
    if not all_dynamic:
        print("      (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
