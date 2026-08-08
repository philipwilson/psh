"""Q3 fresh probe: VariableLookup set/del rejection on ALL THREE surfaces (slot 4B.1).

Surfaces reached through REAL shell state (not the suite's constructors):
  1. a VALUE result from a live lookup,
  2. the MISSING singleton from a live lookup of an absent name,
  3. the PRESENT_UNSET singleton from a live declared-unset export.
Attempts: property assignment, deletion, new-attribute attach; then proves the
NEXT lookup is clean and singleton identity is shared. Run with cwd = worktree.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)

import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

from psh.shell import Shell  # noqa: E402
from psh.core.variable_lookup import LookupStatus, VariableLookup  # noqa: E402

shell = Shell()
shell.run_command('qx=hello')
shell.run_command('export QDECL')   # declared-unset export -> PRESENT_UNSET

sm = shell.state.scope_manager
value_lk = sm.lookup('qx')
missing_lk = sm.lookup('q3_no_such_name_zz')
unset_lk = sm.lookup('QDECL')

assert value_lk.status is LookupStatus.VALUE and value_lk.value == 'hello'
assert missing_lk.status is LookupStatus.MISSING
assert unset_lk.status is LookupStatus.PRESENT_UNSET, unset_lk

# singleton identity through live lookups
assert missing_lk is VariableLookup.missing()
assert missing_lk is sm.lookup('another_absent_name_zz')
assert unset_lk is VariableLookup.present_unset()

results = []


def attempt(label, fn):
    try:
        fn()
    except AttributeError as e:
        results.append((label, "REJECTED", type(e).__name__))
        return
    except Exception as e:
        results.append((label, "UNEXPECTED-EXC", type(e).__name__))
        return
    results.append((label, "MUTATION-SUCCEEDED", "-"))


for name, lk in (("VALUE", value_lk), ("MISSING", missing_lk),
                 ("PRESENT_UNSET", unset_lk)):
    attempt(f"{name}: .status =", lambda lk=lk: setattr(lk, "status", LookupStatus.VALUE))
    attempt(f"{name}: .value =", lambda lk=lk: setattr(lk, "value", "poison"))
    attempt(f"{name}: .is_set =", lambda lk=lk: setattr(lk, "is_set", True))
    attempt(f"{name}: del .status", lambda lk=lk: delattr(lk, "status"))
    attempt(f"{name}: del .value", lambda lk=lk: delattr(lk, "value"))
    attempt(f"{name}: new attr", lambda lk=lk: setattr(lk, "pwned", 1))
    assert not hasattr(lk, "__dict__"), f"{name} has an instance dict"

# after the attempts, the next reads are clean
lk2 = sm.lookup('qx')
assert lk2.status is LookupStatus.VALUE and lk2.value == 'hello'
lk3 = sm.lookup('q3_no_such_name_zz')
assert lk3.status is LookupStatus.MISSING and lk3.value is None
lk4 = sm.lookup('QDECL')
assert lk4.status is LookupStatus.PRESENT_UNSET and lk4.value is None
# and ${QDECL-u} behaves as unset through the real operator
shell.run_command('echo "${QDECL-u}" > /dev/null; rr=${QDECL-u}')
assert shell.state.get_variable('rr') == 'u'

ok = all(v == "REJECTED" for _, v, _ in results)
for label, verdict, exc in results:
    print(f"{'PASS' if verdict == 'REJECTED' else 'FAIL':4} {label:32} {verdict} ({exc})")
print("post-attempt lookups clean; singletons shared:", True)
print("P03-RESULT:", "ALL-REJECTED" if ok else "HOLE-FOUND")
sys.exit(0 if ok else 1)
