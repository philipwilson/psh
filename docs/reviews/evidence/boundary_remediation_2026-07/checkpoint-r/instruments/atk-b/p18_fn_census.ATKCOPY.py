# Q1 probe 18 (MEDIUM-15/16 base-fact one-liners): quick AST census —
# functions >= 100 lines in psh/ (baseline claim: 54 exact at v0.749.0),
# and untyped defs (no return annotation) as a crude M16 magnitude check
# against the recorded 510-623-by-methodology band.
import ast
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt')
assert os.getcwd() == WT

long_fns = []
untyped = 0
total_defs = 0
for root, dirs, files in os.walk(os.path.join(WT, 'psh')):
    for f in sorted(files):
        if not f.endswith('.py'):
            continue
        path = os.path.join(root, f)
        with open(path) as fh:
            try:
                tree = ast.parse(fh.read())
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_defs += 1
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length >= 100:
                    long_fns.append((length, os.path.relpath(path, WT), node.name))
                if node.returns is None:
                    untyped += 1
long_fns.sort(reverse=True)
print("functions >=100 lines in psh/:", len(long_fns))
for length, path, name in long_fns[:10]:
    print("   %4d  %s:%s" % (length, path, name))
print("total defs:", total_defs, "| defs without return annotation:", untyped)
