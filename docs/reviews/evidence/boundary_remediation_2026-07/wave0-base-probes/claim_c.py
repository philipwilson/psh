import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.expansion.pattern_engine import PatternCompiler, STRING, compile_cached

print("=== Claim C: cached AST nodes are writable; rebinding poisons later compiles ===")

# Baseline: 'a' matches 'a', not 'b'
cp = PatternCompiler.compile('a')
print("fresh compile('a'): full_match('a') =", cp.full_match('a', STRING),
      "; full_match('b') =", cp.full_match('b', STRING))

# The returned CompiledPattern.root is the SAME object cached by compile_cached.
root = cp.root
print("root is compile_cached('a'):", root is compile_cached('a'))
print("root elements:", root.elements, "-> node type mutable dataclass:",
      type(root.elements[0]).__name__)

# Adversarial mutation: rebind the cached Literal node's char from 'a' to 'b'.
root.elements[0].char = 'b'

# A FRESH compile of the SAME pattern 'a' now returns the poisoned cached AST.
cp2 = PatternCompiler.compile('a')
print("root is same after mutation:", cp2.root is root)
print("AFTER poisoning cache — fresh compile('a'):")
print("   full_match('a') =", cp2.full_match('a', STRING))
print("   full_match('b') =", cp2.full_match('b', STRING), "  <-- 'a' pattern now matches 'b'")

# Also demonstrate poisoning a real shell consumer: case / [[ == ]] go through
# the same compile_cached, so a poisoned 'a' pattern misroutes there too.
print()
print("=== via a live shell (case statement uses the same cache) ===")
from psh.shell import Shell
# Fresh process cache is already poisoned above because compile_cached is a
# module-level lru_cache. Show a shell 'case' now matching 'b' against pattern a.
sh = Shell()
rc = sh.run_command("case b in a) echo MATCHED-A-AGAINST-B;; *) echo no-match;; esac")
print("shell rc:", rc)
