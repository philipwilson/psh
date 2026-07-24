"""Audit fd-0 KIND fidelity across the oracle migration (slot 1.2).

A migrated call that passes ``stdin_data`` WITHOUT an explicit ``stdin_mode``
gets the runner's default — a regular, SEEKABLE file. Where the pre-migration
code used ``subprocess.run(..., input=...)`` the child had a PIPE, so such a
call silently changes fd-0 kind, and with it any test whose subject is
seekability.

This is CALL-SITE aware on purpose: an earlier module-level substring check for
"stdin_mode" produced a false negative, because a module can mention the name in
an unrelated place (a TEST NAME, ``test_stdin_mode_fires_exit_trap``) while its
actual call site still uses the default.

Usage:  python tests/harness/stdin_kind_audit.py [tests_root]
"""
import ast
import os
import sys

RUNNERS = {"run_psh", "run_bash", "run_shell_case"}


def call_sites_missing_mode(tree):
    """[(lineno, func)] for runner calls passing stdin_data but no stdin_mode."""
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = (n.func.attr if isinstance(n.func, ast.Attribute)
              else getattr(n.func, "id", ""))
        if fn not in RUNNERS:
            continue
        kw = {k.arg for k in n.keywords if k.arg}
        if "stdin_data" in kw and "stdin_mode" not in kw:
            out.append((n.lineno, fn))
    return out


def main(root="tests"):
    flagged = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in sorted(fn):
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except SyntaxError:
                continue
            hits = call_sites_missing_mode(tree)
            if hits:
                flagged.append((rel, hits))
    for rel, hits in flagged:
        for lineno, fn in hits:
            print(f"{rel}:{lineno}: {fn}(stdin_data=..., <default file mode>)")
    print(f"TOTAL call sites passing stdin_data with the DEFAULT mode: "
          f"{sum(len(h) for _, h in flagged)} in {len(flagged)} module(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tests"))
