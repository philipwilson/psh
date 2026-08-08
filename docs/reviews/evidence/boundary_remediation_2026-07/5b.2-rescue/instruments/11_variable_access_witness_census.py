#!/usr/bin/env python3
"""Instrument 11 (slot 5B.2) — the `VariableAccess` witness search (R1 ruling
(c1), authorized and bounded).

R1's specification, implemented literally: an AST census over production `psh/`
for functions/methods taking a ShellState-typed parameter (or reading a
ShellState-typed attribute) whose member usage through that binding is strictly
a subset of `VariableAccess`'s surface — {get_variable, set_variable,
get_special_variable} — with at least one site.

Decision rule is PRE-RULED (R1), not mine to invent:
  >= 1 clean site -> adopt the best (prefer zero whole-object forwarding,
                    smallest surface, clearest read); pre-authorized.
  ZERO clean sites -> STOP and report the empty census; R2 rules the fallback.

"Clean" is reported with its evidence so the choice is reviewable: every member
touched, and every place the binding is passed on whole (a forward means the
callee's needs are unknown here, so such a site is ranked below a leaf).

Usage:  python 11_variable_access_witness_census.py <ROOT>
"""
import ast
import pathlib
import subprocess
import sys

SURFACE = {"get_variable", "set_variable", "get_special_variable"}


def ann_mentions(node, name):
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == name:
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            try:
                sub = ast.parse(n.value, mode="eval")
            except SyntaxError:
                continue
            for m in ast.walk(sub):
                if isinstance(m, ast.Name) and m.id == name:
                    return True
    return False


def state_params(fn):
    a = fn.args
    params = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    return [p.arg for p in params if ann_mentions(p.annotation, "ShellState")]


def binding_usage(fn, binding):
    """(members touched, whole-object uses) for a NAME binding inside fn."""
    members, wholes = [], []
    parents = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == binding:
            p = parents.get(id(node))
            if isinstance(p, ast.Attribute) and p.value is node:
                members.append((node.lineno, p.attr))
            elif isinstance(p, (ast.Call, ast.keyword)):
                gp = p if isinstance(p, ast.Call) else parents.get(id(p))
                callee = ast.unparse(gp.func) if isinstance(gp, ast.Call) else "?"
                wholes.append((node.lineno, f"forwarded to {callee}(...)"))
            elif isinstance(p, ast.Assign):
                wholes.append((node.lineno, f"stored: {ast.unparse(p)[:50]}"))
            elif isinstance(p, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
                pass          # `if state is None` — a guard, not a reach
            else:
                wholes.append((node.lineno, f"bare in {type(p).__name__}"))
    return members, wholes


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print(f"VariableAccess surface: {sorted(SURFACE)}")
    print()

    clean, near_miss = [], []
    for path in sorted((root / "psh").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue

        def walk(node, prefix):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    walk(child, prefix + [child.name])
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = ".".join(prefix + [child.name])
                    for param in state_params(child):
                        members, wholes = binding_usage(child, param)
                        touched = {m for _, m in members}
                        if not touched:
                            continue
                        row = (rel, qual, param, child.lineno, sorted(touched),
                               members, wholes)
                        if touched <= SURFACE:
                            clean.append(row)
                        elif touched & SURFACE:
                            near_miss.append(row)
                    walk(child, prefix + [child.name])

        walk(tree, [])

    print("=" * 74)
    print("CLEAN SITES — member usage strictly within the VariableAccess surface")
    print("=" * 74)
    if not clean:
        print("  *** ZERO CLEAN SITES *** -> R1 says STOP and report; R2 rules.")
    for rel, qual, param, ln, touched, members, wholes in clean:
        print(f"  {rel}:{ln}  {qual}({param}: ShellState)")
        print(f"      members: {touched}   sites: "
              f"{[(l, m) for l, m in members]}")
        print(f"      whole-object uses: {len(wholes)}"
              f"{'  <-- LEAF (none)' if not wholes else ''}")
        for l, w in wholes:
            print(f"          L{l}: {w}")
    print()
    print(f"  CLEAN COUNT: {len(clean)}")
    print()

    print("=" * 74)
    print("NEAR MISSES — touch the surface but ALSO reach outside it")
    print("=" * 74)
    for rel, qual, param, ln, touched, members, wholes in near_miss:
        print(f"  {rel}:{ln}  {qual}({param})  members={touched}"
              f"   outside={sorted(set(touched) - SURFACE)}")
    print(f"  NEAR-MISS COUNT: {len(near_miss)}")
    print()

    # --- ARM B: the ATTRIBUTE arm, which R1's spec also names ---------------
    # "functions/methods taking a ShellState-typed param (OR A SHELLSTATE-TYPED
    # ATTR THEY READ)". Arm A above covers only params; declaring ZERO on that
    # alone would be stopping on half the specified census. A class whose
    # ENTIRE usage of a ShellState-typed attribute stays inside the surface can
    # have the ATTRIBUTE typed `VariableAccess` — that is the natural
    # annotation site, so whole-class usage is the condition, not per-method.
    print("=" * 74)
    print("ARM B — classes holding a ShellState-typed attribute")
    print("=" * 74)
    arm_b_clean = []
    for path in sorted((root / "psh").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = set()
            # class-level `state: 'ShellState'`
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and \
                        isinstance(stmt.target, ast.Name) and \
                        ann_mentions(stmt.annotation, "ShellState"):
                    attrs.add(stmt.target.id)
            # `self.x = <ShellState param>` in any method
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sp = set(state_params(sub))
                    for n in ast.walk(sub):
                        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                                and isinstance(n.targets[0], ast.Attribute) \
                                and isinstance(n.targets[0].value, ast.Name) \
                                and n.targets[0].value.id == "self" \
                                and isinstance(n.value, ast.Name) \
                                and n.value.id in sp:
                            attrs.add(n.targets[0].attr)
                    if isinstance(sub, ast.AnnAssign):
                        pass
            for attr in sorted(attrs):
                touched, wholes = set(), []
                parents = {}
                for a in ast.walk(node):
                    for c in ast.iter_child_nodes(a):
                        parents[id(c)] = a
                for n in ast.walk(node):
                    if isinstance(n, ast.Attribute) and n.attr == attr and \
                            isinstance(n.value, ast.Name) and \
                            n.value.id == "self":
                        p = parents.get(id(n))
                        if isinstance(p, ast.Attribute) and p.value is n:
                            touched.add(p.attr)
                        elif isinstance(p, ast.Assign) and n in p.targets:
                            pass          # the store itself
                        else:
                            wholes.append(n.lineno)
                if touched and touched <= SURFACE:
                    arm_b_clean.append((rel, node.name, attr,
                                        sorted(touched), wholes))
                    print(f"  CLEAN  {rel}  {node.name}.{attr}  "
                          f"members={sorted(touched)}  wholes={len(wholes)}")
    if not arm_b_clean:
        print("  (no class keeps its ShellState attribute usage inside the "
              "surface)")
    print(f"  ARM B CLEAN COUNT: {len(arm_b_clean)}")
    print()
    print("=" * 74)
    print(f"CENSUS TOTAL — arm A (params): {len(clean)}   "
          f"arm B (attributes): {len(arm_b_clean)}")
    print("=" * 74)
    if not clean and not arm_b_clean:
        print("  *** ZERO CLEAN SITES ACROSS BOTH ARMS ***")
        print("  R1 (c1): STOP on this item, report the empty census, do NOT")
        print("  execute a delete without R2.")
    print()

    if clean:
        print("=" * 74)
        print("RANKING (R1 preference: zero forwarding, smallest surface)")
        print("=" * 74)
        ranked = sorted(clean, key=lambda r: (len(r[6]), len(r[4]), r[0]))
        for i, (rel, qual, param, ln, touched, members, wholes) in \
                enumerate(ranked[:8], 1):
            print(f"  {i}. {rel}:{ln} {qual}({param})  "
                  f"members={touched}  forwards={len(wholes)}")
        best = ranked[0]
        print()
        print(f"  BEST: {best[0]}:{best[3]}  {best[1]}({best[2]})")
        print(f"        members={best[4]}  whole-object uses={len(best[6])}")


if __name__ == "__main__":
    main()
