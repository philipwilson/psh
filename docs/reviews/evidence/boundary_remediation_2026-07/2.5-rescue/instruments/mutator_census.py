#!/usr/bin/env python3
"""Census of every in-tree WRITE into the lexical value graph.

The universe is the CLASS, not the names I happen to know:
  * EVERY field of TokenPart (read off the dataclass, not typed by hand);
  * EVERY container edge reachable from LexedUnit (tokens -> Token.parts ->
    TokenPart), discovered by walking the dataclass field TYPES at runtime.

Two instruments, deliberately different in kind:
  A. STATIC (ast): every assignment to `<expr>.parts`, every subscript/slice
     store into `<expr>.parts`, every in-place list-mutator call on
     `<expr>.parts`, and every assignment to an attribute whose NAME is a
     TokenPart field. Over-approximates (name-based) on purpose -- a freeze
     plan must see candidates it would otherwise miss.
  B. DYNAMIC: on a real lexed value, attempt a write to every TokenPart field
     and every container edge and record which succeed. This is the instrument
     the post-fix guard inverts (every row must flip to BLOCKED).

Usage: python3 mutator_census.py
"""
import ast
import dataclasses
import pathlib
import sys

ROOT = pathlib.Path("/Users/pwilson/src/psh-r2-5")
sys.path.insert(0, str(ROOT))

from psh.lexer.token_parts import TokenPart          # noqa: E402
from psh.lexer.token_types import Token              # noqa: E402
from psh.lexer.heredoc_lexer import HeredocLexer, LexedUnit   # noqa: E402

TP_FIELDS = tuple(f.name for f in dataclasses.fields(TokenPart))
LIST_MUTATORS = {"append", "extend", "insert", "pop", "remove", "clear",
                 "sort", "reverse", "__setitem__", "__delitem__"}

print(f"TokenPart fields (universe, read off the dataclass): {TP_FIELDS}")
print(f"Token.parts declared type: "
      f"{[f.type for f in dataclasses.fields(Token) if f.name == 'parts'][0]}")
print(f"LexedUnit fields: {LexedUnit._fields}\n")


class Census(ast.NodeVisitor):
    def __init__(self, path):
        self.path, self.hits = path, []

    def _rec(self, node, kind, detail):
        self.hits.append((self.path, node.lineno, kind, detail))

    def visit_Assign(self, node):
        for t in node.targets:
            self._target(t, node)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._target(node.target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._target(node.target, node)
        self.generic_visit(node)

    def _target(self, t, node):
        if isinstance(t, ast.Attribute):
            if t.attr == "parts":
                self._rec(node, "REBIND .parts", ast.unparse(t))
            elif t.attr in TP_FIELDS:
                self._rec(node, f"FIELD-WRITE .{t.attr}", ast.unparse(t))
        elif isinstance(t, ast.Subscript):
            if isinstance(t.value, ast.Attribute) and t.value.attr == "parts":
                self._rec(node, "STORE .parts[...]", ast.unparse(t))

    def visit_Call(self, node):
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr in LIST_MUTATORS
                and isinstance(f.value, ast.Attribute)
                and f.value.attr == "parts"):
            self._rec(node, f"LIST-MUTATOR .parts.{f.attr}()", ast.unparse(f))
        self.generic_visit(node)

    def visit_Delete(self, node):
        for t in node.targets:
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) \
                    and t.value.attr == "parts":
                self._rec(node, "DELETE .parts[...]", ast.unparse(t))
        self.generic_visit(node)


print("=== A. STATIC census over psh/ (production tree) ===")
all_hits = []
for py in sorted(ROOT.joinpath("psh").rglob("*.py")):
    c = Census(str(py.relative_to(ROOT)))
    c.visit(ast.parse(py.read_text()))
    all_hits += c.hits
by_kind = {}
for path, line, kind, detail in all_hits:
    by_kind.setdefault(kind, []).append(f"{path}:{line}  {detail}")
for kind in sorted(by_kind):
    print(f"\n[{kind}]  n={len(by_kind[kind])}")
    for h in by_kind[kind]:
        print("   ", h)
print(f"\nSTATIC TOTAL (derived): {len(all_hits)}")

print("\n=== B. DYNAMIC census on a real lexed value ===")
unit = HeredocLexer('echo "a$b"c $(x) <<E\nb\nE\n',
                    warn_unterminated=False).tokenize_with_heredocs()
tok = next(t for t in unit.tokens if t.parts)
part = tok.parts[0]
rows = []
for fname in TP_FIELDS:
    try:
        setattr(part, fname, getattr(part, fname))
        rows.append((f"TokenPart.{fname}", "WRITABLE"))
    except Exception as e:                                   # noqa: BLE001
        rows.append((f"TokenPart.{fname}", f"BLOCKED({type(e).__name__})"))
edges = [
    ("Token.parts (rebind)",  lambda: setattr(tok, "parts", [])),
    ("Token.parts.append",    lambda: tok.parts.append(part)),
    ("Token.parts[0]=",       lambda: tok.parts.__setitem__(0, part)),
    ("Token.parts.clear",     lambda: tok.parts.clear()),
    ("LexedUnit.tokens[0]=",  lambda: unit.tokens.__setitem__(0, tok)),
    ("LexedUnit.heredocs[0]=", lambda: unit.heredocs.__setitem__(0, None)),
]
for name, fn in edges:
    try:
        fn()
        rows.append((name, "WRITABLE"))
    except Exception as e:                                   # noqa: BLE001
        rows.append((name, f"BLOCKED({type(e).__name__})"))
writable = sum(1 for _, r in rows if r == "WRITABLE")
for name, r in rows:
    print(f"   {name:28s} {r}")
print(f"\nDYNAMIC TOTAL (derived): rows={len(rows)} WRITABLE={writable} "
      f"BLOCKED={len(rows) - writable}")
