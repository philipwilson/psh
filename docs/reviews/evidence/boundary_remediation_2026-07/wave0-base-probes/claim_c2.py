import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.expansion.pattern_engine import compile_cached
from psh.shell import Shell

print("=== Claim C end-to-end: poison the cache entry a live `case` uses ===")

sh = Shell()
print("before poisoning: case b in a) ...")
sh.run_command("case b in a) echo MATCHED;; *) echo no-match;; esac")

# The shell's case/[[ ]] compile 'a' via compile_cached with BOTH extglob
# variants depending on the `extglob` shopt. Poison every cached Literal('a')
# node reachable through the two keys the shell can produce.
for key in [('a', True), ('a', False)]:
    seq = compile_cached(*key)
    for node in seq.elements:
        if getattr(node, 'char', None) == 'a':
            node.char = 'b'   # rebind the shared cached node

print("after poisoning: case b in a) ...")
sh.run_command("case b in a) echo MATCHED;; *) echo no-match;; esac")
print("after poisoning: case a in a) ...  (should now NOT match its own literal)")
sh.run_command("case a in a) echo MATCHED;; *) echo no-match;; esac")
