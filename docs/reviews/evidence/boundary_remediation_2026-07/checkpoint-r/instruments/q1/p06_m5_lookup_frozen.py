# Q1 probe 06 (MEDIUM-5): VariableLookup read-only on all three surfaces;
# binding OMITTED (ruling R1(b)); MISSING/PRESENT_UNSET frozen shared singletons.
# Fresh 0.773.0 probe (committed claim_b.py/claim_b2.py are 0.750.0-frozen).
# Axis: REGRESSION vs recorded base bug (readonly bypass via .binding.value;
# _MISSING poisoning). Probe composed from OUTSIDE the suite's own cells.
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

from psh.shell import Shell
from psh.core.variable_lookup import VariableLookup

results = []


def attempt(label, fn):
    try:
        fn()
        results.append((label, "MUTATED (HOLE)"))
    except (AttributeError, TypeError) as e:
        results.append((label, "REJECTED: %s: %s" % (type(e).__name__, e)))


sh = Shell(norc=True)
sh.run_command("readonly RO=original")
lk = sh.state.scope_manager.lookup('RO')
print("VALUE surface:", type(lk).__name__, "status:", lk.status,
      "value:", repr(lk.value))
print("has .binding attr:", hasattr(lk, 'binding'),
      " (ruling R1(b): must be absent)")
attempt("VALUE set .value", lambda: setattr(lk, 'value', 'HACKED'))
attempt("VALUE set ._value", lambda: setattr(lk, '_value', 'HACKED'))
attempt("VALUE del .value", lambda: delattr(lk, 'value'))
attempt("VALUE set .status", lambda: setattr(lk, 'status', None))
attempt("VALUE set arbitrary attr", lambda: setattr(lk, 'evil', 1))

miss1 = sh.state.scope_manager.lookup('DEFINITELY_UNSET_NAME_Q1')
print("MISSING is shared singleton:", miss1 is VariableLookup.missing())
attempt("MISSING set .status", lambda: setattr(miss1, 'status', 'X'))
attempt("MISSING set ._status", lambda: setattr(miss1, '_status', 'X'))
attempt("MISSING set .value", lambda: setattr(miss1, 'value', 'POISON'))

pu = VariableLookup.present_unset()
attempt("PRESENT_UNSET set .status", lambda: setattr(pu, 'status', 'X'))
attempt("PRESENT_UNSET set .value", lambda: setattr(pu, 'value', 'POISON'))
attempt("PRESENT_UNSET del ._value", lambda: delattr(pu, '_value'))

# a second miss still reports missing (no poisoning possible)
miss2 = sh.state.scope_manager.lookup('ANOTHER_UNSET_NAME_Q1')
print("post-attempts: second miss is_set =", miss2.is_set,
      "status =", miss2.status)
print("shell still reads RO =", repr(sh.state.get_variable('RO')))

holes = [r for r in results if r[1].startswith("MUTATED")]
for label, res in results:
    print("  %-28s -> %s" % (label, res))
print("HOLES:", len(holes))
sh.close()
