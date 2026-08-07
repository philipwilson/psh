# FROZEN BASE ARTIFACT — runs at base v0.750.0 (0215279c) ONLY. It exercises
# lookup().binding, REMOVED in v0.770.0 (slot 4B.1, ruling R1(b)); at any
# later version the AttributeError it raises is this header, not a defect.
# The version self-pin below enforces it.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.shell import Shell
from psh.core.variable_lookup import VariableLookup, LookupStatus

print("=== Claim B part 1: mutate a READONLY variable via lookup().binding.value ===")
sh = Shell()
sh.run_command("readonly RO=original")
print("initial   $RO =", repr(sh.state.get_variable('RO')))

# Legitimate write must be refused (readonly).
rc = sh.run_command("RO=viaassign 2>/dev/null")
print("assign rc =", rc, "(nonzero => readonly enforced); $RO =",
      repr(sh.state.get_variable('RO')))

# Now the bypass: lookup() hands back the LIVE Variable cell as .binding.
lk = sh.state.scope_manager.lookup('RO')
print("lookup status =", lk.status, "; binding is live cell =",
      type(lk.binding).__name__, "; binding.readonly =",
      getattr(lk.binding, 'readonly', '?'))
lk.binding.value = 'HACKED'          # write straight through the read view

print("after binding.value='HACKED':")
print("   shell read  $RO =", repr(sh.state.get_variable('RO')), " <-- changed, readonly bypassed")
# Show it also bypasses the exported environment (claim: reads change, env does not)
sh.run_command("export RO 2>/dev/null")
import os as _os
sh.run_command("RO2=x")  # force nothing; just inspect
sh2env = sh.state.scope_manager
print("   (readonly attr still set on cell:", getattr(lk.binding, 'readonly', '?'), ")")

print()
print("=== Claim B part 2: mutate the shared _MISSING sentinel ===")
sh2 = Shell()
miss1 = sh2.state.scope_manager.lookup('DEFINITELY_UNSET_NAME_1')
print("miss1 is VariableLookup.missing():", miss1 is VariableLookup.missing())
print("miss1.status before poison:", miss1.status, "is_set:", miss1.is_set)

# Poison the shared singleton in place (writable __slots__, no frozen).
miss1.status = LookupStatus.VALUE
miss1.value = 'POISON'

# Any later miss on ANY name returns the same singleton object, now poisoned.
miss2 = sh2.state.scope_manager.lookup('A_COMPLETELY_DIFFERENT_UNSET_NAME')
print("miss2 is miss1 (shared singleton):", miss2 is miss1)
print("miss2.status after poison:", miss2.status, "is_set:", miss2.is_set,
      "value:", repr(miss2.value), " <-- a genuine miss now reports VALUE 'POISON'")
