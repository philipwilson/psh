"""Q3 fresh probe: pattern node / CompiledPattern mutation from OUTSIDE the suite (slot 3.2).

Reaches the cache through a REAL Shell run (no engine API in the poisoning
setup), then attempts depth>=2 mutations on cached nodes the suite's cells do
not use ('ab*' / '[abc]' via a shell-driven compile), and proves a later
identical shell command is unchanged. Run with cwd = worktree.
"""
import dataclasses
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)

import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

from psh.shell import Shell  # noqa: E402
from psh.expansion import pattern_engine as pe  # noqa: E402
from psh.expansion.pattern_engine import PatternCompiler  # noqa: E402

results = []


def attempt(label, fn):
    try:
        fn()
    except (dataclasses.FrozenInstanceError, TypeError, AttributeError) as e:
        results.append((label, "REJECTED", type(e).__name__))
        return
    except Exception as e:
        results.append((label, "UNEXPECTED-EXC", type(e).__name__))
        return
    results.append((label, "MUTATION-SUCCEEDED", "-"))


shell = Shell()
shell.run_command('v=abzz; r=${v//ab*/HIT}; s=${v/[abc]/Q}')
assert shell.state.get_variable('r') == 'HIT', shell.state.get_variable('r')

# the cached roots the shell just built/used
root = pe.compile_cached('ab*', True)
attempt("Sequence.elements[0] attr write", lambda: setattr(root.elements[0], next(iter(
    f.name for f in dataclasses.fields(root.elements[0]))), "z"))
attempt("Sequence.nullable flip", lambda: setattr(root, "nullable", not root.nullable))
attempt("Sequence.has_extglob flip", lambda: setattr(root, "has_extglob", True))
attempt("Sequence.elements rebind", lambda: setattr(root, "elements", ()))
attempt("Sequence new attr", lambda: setattr(root, "pwned", 1))

broot = pe.compile_cached('[abc]', True)
br = broot.elements[0]
attempt("Bracket.content write", lambda: setattr(br, "content", "xyz"))
attempt("Bracket.negated flip", lambda: setattr(br, "negated", True))

cp = PatternCompiler.compile('ab*')
attempt("CompiledPattern.root rebind",
        lambda: setattr(cp, "root", PatternCompiler.compile('zz').root))
attempt("CompiledPattern new attr", lambda: setattr(cp, "pwned", 1))

# extglob routing bits at depth >= 2 (Extglob nested inside Sequence)
xroot = pe.compile_cached('*!(a)', True)
xg = next(e for e in xroot.elements if type(e).__name__ == "Extglob")
attempt("Extglob.enclosed flip (depth 2)", lambda: setattr(xg, "enclosed", True))
attempt("Sequence.bash_quirk flip", lambda: setattr(xroot, "bash_quirk", False))

# the criterion that matters: the same command still answers the same
shell.run_command('v=abzz; r2=${v//ab*/HIT}')
same = shell.state.get_variable('r2') == 'HIT'
ok = all(v == "REJECTED" for _, v, _ in results) and same

for label, verdict, exc in results:
    print(f"{'PASS' if verdict == 'REJECTED' else 'FAIL':4} {label:42} {verdict} ({exc})")
print("later identical shell command unchanged:", same)
print("P02-RESULT:", "ALL-REJECTED" if ok else "HOLE-FOUND")
sys.exit(0 if ok else 1)
