#!/usr/bin/env python3
"""Instrument 01 (slot 5B.2) — PER-DEFINITION consumer census for the protocols
whose members §A6 orders narrowed.

5B.1 point 4 (instrument-mirror caution): NAME HITS ARE NOT CONSUMERS. This
instrument resolves consumers by DEFINITION:

  * a module CONSUMES a protocol if it imports the protocol's name FROM the
    module that defines it (absolute or relative), and then either declares it
    as a class base or names it in an annotation.

For each consumer of ``VariableExpanderProtocol`` it then enumerates every
attribute access through the two members §A6 targets (``self.shell`` /
``self.state``), so the REMOVE row can be decided on measured need rather than
on assertion.

ROOT comes from argv (CR-D5 instrument-portability class): no hardcoded paths.

Usage:  python 01_protocol_consumer_census.py <ROOT>
"""
import ast
import collections
import pathlib
import sys


def iter_modules(psh_root):
    for path in sorted(psh_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def module_dotted(path, root):
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_relative(cur_mod, node, is_package):
    parts = cur_mod.split(".")
    pkg_parts = list(parts) if is_package else parts[:-1]
    up = node.level - 1
    if up > 0:
        pkg_parts = pkg_parts[:-up] if up <= len(pkg_parts) else []
    target = ".".join(pkg_parts)
    if node.module:
        target = target + "." + node.module if target else node.module
    return target


def imports_of(tree, module, is_package):
    """{imported_name: source_module} for every `from X import name`."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            src = (resolve_relative(module, node, is_package)
                   if node.level else node.module)
            for a in node.names:
                out[a.asname or a.name] = (src, a.name)
    return out


def base_names(cls):
    return {ast.unparse(b) for b in cls.bases}


def protocol_aliases(tree, proto_name):
    """Module-level names bound to *proto_name*.

    INSTRUMENT DEFECT FOUND AND FIXED BEFORE USE (recorded, not buried): the
    first version of this instrument matched a ClassDef base against the
    protocol NAME only and reported 0 consumers for three protocols §A6 records
    as having 4/4/3. The real shape is the TYPE_CHECKING alias

        if TYPE_CHECKING:
            from ._protocols import VariableExpanderProtocol
            _Base = VariableExpanderProtocol
        else:
            _Base = object
        class ArrayOpsMixin(_Base): ...

    so the base is the ALIAS. A name-shaped consumer census would have missed
    every mixin consumer in the tree — the mirror of 5B.1's caution.
    """
    aliases = {proto_name}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                    isinstance(node.targets[0], ast.Name) and \
                    isinstance(node.value, ast.Name) and \
                    node.value.id in aliases and \
                    node.targets[0].id not in aliases:
                aliases.add(node.targets[0].id)
                changed = True
    return aliases


def annotation_names(tree):
    """Every identifier appearing in any annotation position (incl. strings)."""
    names = collections.defaultdict(list)

    def record(ann):
        if ann is None:
            return
        for n in ast.walk(ann):
            if isinstance(n, ast.Name):
                names[n.id].append(getattr(ann, "lineno", -1))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                try:
                    sub = ast.parse(n.value, mode="eval")
                except SyntaxError:
                    continue
                for m in ast.walk(sub):
                    if isinstance(m, ast.Name):
                        names[m.id].append(getattr(ann, "lineno", -1))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            for p in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                      + ([a.vararg] if a.vararg else [])
                      + ([a.kwarg] if a.kwarg else [])):
                record(p.annotation)
            record(node.returns)
        elif isinstance(node, ast.AnnAssign):
            record(node.annotation)
    return names


def consumers_of(psh_root, root, proto_name, defining_module):
    """Modules that import proto_name FROM defining_module and USE it."""
    found = []
    for path in iter_modules(psh_root):
        module = module_dotted(path, root)
        if module == defining_module:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        imps = imports_of(tree, module, path.name == "__init__.py")
        if proto_name not in imps:
            continue
        src, orig = imps[proto_name]
        if src != defining_module:
            continue
        uses = {"as_base": [], "in_annotation": []}
        aliases = protocol_aliases(tree, proto_name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and (base_names(node) & aliases):
                uses["as_base"].append((node.name, node.lineno))
        anns = annotation_names(tree)
        if proto_name in anns:
            uses["in_annotation"] = sorted(set(anns[proto_name]))
        if uses["as_base"] or uses["in_annotation"]:
            found.append((module, str(path.relative_to(root)), uses))
    return found


def member_reach(path, member):
    """Every `self.<member>.<attr>` access and every BARE `self.<member>` use,
    with the enclosing function qualname."""
    tree = ast.parse(path.read_text())
    attr_hits = []      # (lineno, attr, qualname)
    bare_hits = []      # (lineno, context, qualname)

    stack = []

    class V(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Attribute(self, node):
            # self.<member>.<attr>
            v = node.value
            if (isinstance(v, ast.Attribute) and v.attr == member
                    and isinstance(v.value, ast.Name) and v.value.id == "self"):
                attr_hits.append((node.lineno, node.attr, ".".join(stack)))
            self.generic_visit(node)

    V().visit(tree)

    # BARE self.<member>: an Attribute node self.<member> whose PARENT is not
    # another Attribute (i.e. the whole object is used, not a sub-attribute).
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    stack2 = []

    class W(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            stack2.append(node.name)
            self.generic_visit(node)
            stack2.pop()

        def visit_FunctionDef(self, node):
            stack2.append(node.name)
            self.generic_visit(node)
            stack2.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Attribute(self, node):
            if (node.attr == member and isinstance(node.value, ast.Name)
                    and node.value.id == "self"):
                p = parents.get(id(node))
                if not isinstance(p, ast.Attribute):
                    kind = type(p).__name__ if p is not None else "?"
                    bare_hits.append((node.lineno, kind, ".".join(stack2)))
            self.generic_visit(node)

    W().visit(tree)
    return attr_hits, bare_hits


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    psh_root = root / "psh"
    print(f"ROOT={root}")
    print(f"psh tree exists: {psh_root.is_dir()}")
    print()

    targets = [
        ("VariableExpanderProtocol", "psh.expansion._protocols"),
        ("CommandParsersProtocol", "psh.parser.combinators.commands._protocols"),
        ("ControlStructureProtocol",
         "psh.parser.combinators.control_structures._protocols"),
        ("VariableAccess", "psh.protocols"),
        ("ExpansionRuntime", "psh.protocols"),
        ("IOContext", "psh.protocols"),
        ("JobRuntime", "psh.protocols"),
        ("LocaleAccess", "psh.protocols"),
    ]

    for proto, defmod in targets:
        cons = consumers_of(psh_root, root, proto, defmod)
        print(f"=== {proto}  (defined in {defmod}) ===")
        print(f"    production consumers (per definition): {len(cons)}")
        for module, rel, uses in cons:
            bits = []
            if uses["as_base"]:
                bits.append("base of " + ", ".join(
                    f"{c}@L{ln}" for c, ln in uses["as_base"]))
            if uses["in_annotation"]:
                bits.append("annotation@L" + ",".join(
                    str(x) for x in uses["in_annotation"]))
            print(f"      - {rel}: {'; '.join(bits)}")
        print()

    # --- member reach for the VariableExpanderProtocol consumers ------------
    print("=== MEMBER REACH: self.shell / self.state in each "
          "VariableExpanderProtocol consumer ===")
    cons = consumers_of(psh_root, root, "VariableExpanderProtocol",
                        "psh.expansion._protocols")
    for module, rel, _uses in cons:
        path = root / rel
        for member in ("shell", "state"):
            attrs, bares = member_reach(path, member)
            counter = collections.Counter(a for _, a, _ in attrs)
            print(f"  {rel}  self.{member}:  "
                  f"{len(attrs)} attr-access, {len(bares)} bare-use")
            if counter:
                print(f"      attrs: {dict(sorted(counter.items()))}")
            for ln, attr, qn in attrs:
                print(f"        L{ln:<5} self.{member}.{attr}    [{qn}]")
            for ln, kind, qn in bares:
                print(f"        L{ln:<5} BARE self.{member} (parent {kind})"
                      f"    [{qn}]")
        print()


if __name__ == "__main__":
    main()
