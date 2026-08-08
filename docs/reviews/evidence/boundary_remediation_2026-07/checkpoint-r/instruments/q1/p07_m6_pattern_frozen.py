# Q1 probe 07 (MEDIUM-6 + HIGH-7 immutability face): pattern AST nodes and
# CompiledPattern frozen; cache poisoning impossible; live `case` unaffected.
# Fresh 0.773.0 equivalent of wave0-base-probes/claim_c.py / claim_c2.py.
# Axis: REGRESSION vs recorded base bug ('a' made to match 'b' via cache).
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.expansion.pattern_engine import PatternCompiler, STRING, compile_cached

cp = PatternCompiler.compile('a')
print("fresh compile('a'): full_match('a') =", cp.full_match('a', STRING),
      "; full_match('b') =", cp.full_match('b', STRING))
root = cp.root
node = root.elements[0]
print("node type:", type(node).__name__)

attempts = []
for label, fn in [
    ("node.char = 'b'", lambda: setattr(node, 'char', 'b')),
    ("node del char", lambda: delattr(node, 'char')),
    ("CompiledPattern.root = None", lambda: setattr(cp, 'root', None)),
    ("CompiledPattern new attr", lambda: setattr(cp, 'evil', 1)),
]:
    try:
        fn()
        attempts.append((label, "MUTATED (HOLE)"))
    except Exception as e:
        attempts.append((label, "REJECTED: %s" % type(e).__name__))
for kext in [('a', True), ('a', False)]:
    seq = compile_cached(*kext)
    for n in seq.elements:
        if getattr(n, 'char', None) == 'a':
            try:
                n.char = 'b'
                attempts.append(("compile_cached%s poison" % (kext,), "MUTATED (HOLE)"))
            except Exception as e:
                attempts.append(("compile_cached%s poison" % (kext,),
                                 "REJECTED: %s" % type(e).__name__))
for label, res in attempts:
    print("  %-36s -> %s" % (label, res))

from psh.shell import Shell
sh = Shell(norc=True)
print("live case after all poisoning attempts:")
sh.run_command("case b in a) echo MATCHED-A-AGAINST-B;; *) echo no-match-b;; esac")
sh.run_command("case a in a) echo MATCHED-A;; *) echo no-match-a;; esac")
holes = [a for a in attempts if a[1].startswith("MUTATED")]
print("HOLES:", len(holes))
sh.close()
