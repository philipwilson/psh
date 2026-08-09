#!/usr/bin/env python3
"""B3 — TWO-AXIS for the ast_debug narrowing (masker row 7).

AXIS 1 (REGRESSION): the USER-REACHABLE unknown-format path keeps its exact
warning + DebugASTVisitor fallback.
AXIS 2 (RECLASSIFICATION): a defect inside a FORMATTER, which the old
(ValueError, TypeError, AttributeError) net downgraded to that same warning,
now surfaces.

ROOT from argv[1]; discriminator asserted.
"""
import io
import os
import sys

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, ROOT)
import psh  # noqa: E402

assert os.path.dirname(psh.__file__) == os.path.join(ROOT, "psh"), "discriminator"
print(f"# tree={ROOT}")

from psh.shell import Shell            # noqa: E402
from psh.utils.ast_debug import print_ast_debug  # noqa: E402


def render(seed=None):
    """Run print_ast_debug over a tiny AST, returning captured stderr."""
    sh = Shell(norc=True)
    undo = seed() if seed else (lambda: None)
    err = io.StringIO()
    real, sys.stderr = sys.stderr, err
    try:
        from psh.lexer import tokenize
        from psh.parser import parse
        ast = parse(tokenize("echo hi"))
        sh.state.scope_manager.set_variable("PSH_AST_FORMAT", "pretty")
        try:
            print_ast_debug(ast, None, sh)
            outcome = "(returned normally)"
        except BaseException as e:      # noqa: BLE001 - measuring
            outcome = f"SURFACED {type(e).__name__}: {str(e)[:52]}"
    finally:
        sys.stderr = real
        undo()
        sh.close()
    return outcome, err.getvalue()


def seed_formatter_typeerror():
    """A defect inside the SELECTED formatter (the shape the net masked)."""
    from psh.parser.visualization import ASTPrettyPrinter
    orig = ASTPrettyPrinter.visit

    def boom(self, node):
        raise TypeError("seeded defect inside ASTPrettyPrinter.visit")
    ASTPrettyPrinter.visit = boom
    return lambda: setattr(ASTPrettyPrinter, "visit", orig)


print("=== AXIS 1: unknown format (USER-REACHABLE) — warning must be identical ===")
def seed_unknown():
    return lambda: None
sh = Shell(norc=True)
try:
    from psh.lexer import tokenize
    from psh.parser import parse
    ast = parse(tokenize("echo hi"))
    err = io.StringIO(); real, sys.stderr = sys.stderr, err
    try:
        sh.state.scope_manager.set_variable("PSH_AST_FORMAT", "bogus")
        print_ast_debug(ast, None, sh)
    finally:
        sys.stderr = real
    warn = [ln for ln in err.getvalue().splitlines() if "Warning" in ln]
    print(f"  warning line: {warn[0] if warn else '(NONE)'}")
    print(f"  fallback rendered: {'Program' in err.getvalue()}")
finally:
    sh.close()

print("\n=== AXIS 2: defect inside the selected formatter ===")
outcome, err = render(seed_formatter_typeerror)
warn = [ln for ln in err.splitlines() if "Warning" in ln]
print(f"  outcome: {outcome}")
print(f"  masked-as-warning: {warn[0] if warn else '(no warning — NOT masked)'}")

print("\n=== CONTROL: no seed, known format ===")
outcome, err = render(None)
print(f"  outcome: {outcome}; rendered: {'Program' in err}")
