#!/usr/bin/env python3
"""Instrument 10 (slot 5B.2) — what the 12 campaign-added owner params TOUCH.

CR-R1 reshape 2 puts all 12 in the migration set; three of them carry recorded
5B.1-R0 ALLOWLIST justifications. The brief asks for measurement, not
adjudication: per param, every member reached through it, every place it is
passed on whole, and (for a forward) where it lands. Ruling (e) decides
migrate-vs-justified-keep on this.

A param's need is NARROW if every use is an attribute read/call that some
existing protocol's surface covers; it is WHOLE-SHELL if the binding is passed
on to something that needs the whole object, or used in a way no surface models
(construction through its own type being the extreme case).

Usage:  python 10_twelve_param_matrix.py <ROOT>
"""
import ast
import collections
import pathlib
import subprocess
import sys

TARGETS = [
    ("psh/builtins/shell_state.py", "HistoryBuiltin._dispatch_options", "shell"),
    ("psh/builtins/shell_state.py", "HistoryBuiltin._display_operand", "shell"),
    ("psh/builtins/shell_state.py", "HistoryBuiltin._parse_options", "shell"),
    ("psh/core/internal_errors.py", "fatal_expansion_child_status", "state"),
    ("psh/core/internal_errors.py", "substitution_abort_status", "state"),
    ("psh/core/internal_errors.py", "substitution_child_abort_status", "state"),
    ("psh/executor/child_policy.py", "sync_child_status_for_exit_trap", "state"),
    ("psh/executor/child_policy.py", "map_child_exception", "state"),
    ("psh/scripting/analysis_session.py", "AnalysisSession.__init__", "shell"),
    ("psh/scripting/analysis_session.py", "AnalysisSession._build_carrier",
     "shell"),
    ("psh/scripting/analysis_session.py", "parse_for_analysis", "shell"),
    ("psh/scripting/source_processor.py", "iter_command_units", "shell"),
]


def find_def(tree, qualname):
    want = qualname.split(".")

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                r = walk(child, prefix + [child.name])
                if r:
                    return r
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if prefix + [child.name] == want:
                    return child
                r = walk(child, prefix + [child.name])
                if r:
                    return r
        return None

    return walk(tree, [])


def analyse(fn, param):
    """(attr uses, bare uses) of *param* inside *fn*."""
    attrs, bares = [], []
    parents = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == param:
            p = parents.get(id(node))
            if isinstance(p, ast.Attribute) and p.value is node:
                gp = parents.get(id(p))
                kind = "CALL" if isinstance(gp, ast.Call) and gp.func is p \
                    else "ATTR"
                attrs.append((node.lineno, p.attr, kind))
            elif isinstance(p, ast.Call):
                callee = ast.unparse(p.func)
                bares.append((node.lineno, f"passed to {callee}(...)"))
            elif isinstance(p, ast.keyword):
                gp = parents.get(id(p))
                callee = ast.unparse(gp.func) if isinstance(gp, ast.Call) \
                    else "?"
                bares.append((node.lineno,
                              f"passed as {p.arg}= to {callee}(...)"))
            elif isinstance(p, ast.Assign):
                bares.append((node.lineno,
                              f"stored: {ast.unparse(p)[:60]}"))
            elif isinstance(p, ast.Compare):
                bares.append((node.lineno, "compared (is/is not)"))
            else:
                bares.append((node.lineno, f"bare use in {type(p).__name__}"))
    return attrs, bares


def annotation_of(fn, param):
    a = fn.args
    for p in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)):
        if p.arg == param:
            return ast.unparse(p.annotation) if p.annotation else "<UNANNOTATED>"
    return "<not a param>"


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    sys.path.insert(0, str(root))
    from tests.unit.tooling.test_shell_consumer_ratchet_q1 import (  # noqa
        ALLOWLIST,
    )
    print()

    for rel, qual, param in TARGETS:
        path = root / rel
        tree = ast.parse(path.read_text())
        fn = find_def(tree, qual)
        print("=" * 74)
        print(f"{rel}::{qual}({param})")
        print("=" * 74)
        if fn is None:
            print("  !! DEF NOT FOUND — enumeration is stale")
            print()
            continue
        ann = annotation_of(fn, param)
        dotted = rel[:-3].replace("/", ".")
        recorded = (dotted, qual) in ALLOWLIST
        print(f"  line {fn.lineno}   annotation: {ann}")
        print(f"  in ratchet ALLOWLIST: {recorded}")
        attrs, bares = analyse(fn, param)
        counter = collections.Counter(a for _, a, _ in attrs)
        print(f"  members reached ({len(attrs)} sites): "
              f"{dict(sorted(counter.items())) if counter else '{}'}")
        for ln, attr, kind in sorted(attrs):
            print(f"      L{ln:<5} {param}.{attr}   [{kind}]")
        print(f"  WHOLE-object uses ({len(bares)}):")
        for ln, what in sorted(bares):
            print(f"      L{ln:<5} {what}")
        if not bares:
            print("      (none — every use is a member reach)")
        print()


if __name__ == "__main__":
    main()
