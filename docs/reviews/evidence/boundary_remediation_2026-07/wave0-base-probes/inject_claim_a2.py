"""CLAIM A consequence probes.

(1) TRANSFER poisoning: if the grant that fails is a TRANSFER from a
    quiescent previous owner A, activate rolls owner back to A but leaves the
    new owner's LOCALE component in _components. That poisons _ensure_owner's
    competing-owner guard so a THIRD shell's activation raises a spurious
    LeaseError.

(2) force-release-after-restore-raises: release_owner -> _force_release_components
    swallows a raising restore and clears ownership+components, leaving the
    process mutated with no owner able to repair.
"""
import os, sys
WORKTREE = '/Users/pwilson/src/psh-r22-verify'
sys.path.insert(0, WORKTREE)
os.environ['LC_ALL'] = 'C'  # A and C are C-locale (quiescent, no lease)
os.environ.pop('LC_CTYPE', None)
os.environ.pop('LC_COLLATE', None)

import psh.version
assert psh.version.__file__.startswith(WORKTREE), psh.version.__file__
assert psh.version.__version__ == '0.750.0', psh.version.__version__
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.core.state import ShellState
from psh.core.process_lease import (get_coordinator, ComponentKind,
                                    ComponentLease, LeaseError)

coord = get_coordinator()

# --- Scenario 1: transfer poisoning -----------------------------------
print("\n=== SCENARIO 1: transfer-grant failure poisons _components ===")
# Shell A: C-locale, becomes a QUIESCENT owner (activate then release lease).
A = ShellState()
A.locale.ensure_applied = lambda *a, **k: None
la = A.activate()
la.release()   # depth back to 0, A stays owner, no components (C locale)
print("A quiescent owner: owner_is_A=%s depth=%s components=%s"
      % (coord.current_owner() is A, coord.activation_depth, len(coord._components)))

# Shell B: non-C locale, so its grant will try to take a LOCALE lease; inject a
# failure in ensure_applied so the grant rolls back (transfer A->B fails).
os.environ['LC_ALL'] = 'en_US.UTF-8'
B = ShellState()
assert B.locale.pending_libc, "B should be pending non-C"
def _boom(*a, **k):
    raise RuntimeError("INJECTED: B locale apply failed")
B.locale.ensure_applied = _boom
try:
    B.activate()
except BaseException as e:
    print("B.activate raised:", type(e).__name__, str(e)[:50])
print("after B fail: owner_is_A=%s depth=%s components=%s"
      % (coord.current_owner() is A, coord.activation_depth, len(coord._components)))
for c in coord._components:
    print("   poisoning lease: kind=%s released=%s owner_is_B=%s owner_is_A=%s"
          % (c.kind.name, c.released, c.owner_ref() is B, c.owner_ref() is A))

# Now a THIRD shell C (plain C-locale) tries to activate. A is quiescent, so
# this SHOULD succeed (ownership transfers A->C). Does the leftover poison it?
os.environ['LC_ALL'] = 'C'
C = ShellState()
C.locale.ensure_applied = lambda *a, **k: None
try:
    C.activate()
    print("C.activate SUCCEEDED (owner_is_C=%s)" % (coord.current_owner() is C))
except LeaseError as e:
    print("C.activate RAISED LeaseError (SPURIOUS):", str(e)[:120])

# --- Scenario 2: force-release swallows a raising restore --------------
print("\n=== SCENARIO 2: force-release after restore raises ===")
coord2 = get_coordinator()
# fresh owner D holding a component whose restore RAISES
os.environ['LC_ALL'] = 'C'
D = ShellState()
D.locale.ensure_applied = lambda *a, **k: None
D.activate()
process_state = {'mutated': True}   # pretend D mutated a global
def _raising_restore():
    # a real restore that itself fails (e.g. setlocale of a now-invalid name,
    # or an fd close on a bad fd) -- leaves process_state['mutated'] True
    raise OSError("INJECTED: restore failed; global stays mutated")
lease = coord2.acquire_component(D, ComponentKind.STD_FDS,
                                 restore=_raising_restore, description="test")
print("D owner with 1 component; process 'mutated'=%s" % process_state['mutated'])
coord2.release_owner(D)   # Shell.close() path
print("after release_owner(D): owner=%s components=%s process_mutated=%s"
      % (coord2.current_owner(), len(coord2._components), process_state['mutated']))
print("  -> ownership + component cleared; restore raised & was swallowed;")
print("     process left mutated with no owner able to repair.")
