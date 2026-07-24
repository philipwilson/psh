"""CLAIM A part 2 (isolated): force-release swallows a raising restore and
clears ownership+components, leaving the process mutated with no owner."""
import os, sys
WORKTREE = '/Users/pwilson/src/psh-r22-verify'
sys.path.insert(0, WORKTREE)
os.environ['LC_ALL'] = 'C'
os.environ.pop('LC_CTYPE', None); os.environ.pop('LC_COLLATE', None)

import psh.version
assert psh.version.__file__.startswith(WORKTREE) and psh.version.__version__ == '0.750.0'
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.core.state import ShellState
from psh.core.process_lease import get_coordinator, ComponentKind

coord = get_coordinator()
D = ShellState()
D.locale.ensure_applied = lambda *a, **k: None
la = D.activate()
la.release()   # depth back to 0: D is a QUIESCENT owner (real close path)
print("D quiescent: owner_is_D=%s depth=%s" % (coord.current_owner() is D, coord.activation_depth))

process_state = {'mutated': True}   # pretend D mutated a process global
def _raising_restore():
    # restore that itself fails (e.g. os.close of an already-bad fd, or a
    # setlocale to a now-invalid name) -- global stays mutated
    raise OSError("INJECTED: restore failed; global stays mutated")

coord.acquire_component(D, ComponentKind.STD_FDS,
                        restore=_raising_restore, description="test")
print("D owner, 1 component, process_mutated=%s" % process_state['mutated'])

coord.release_owner(D)   # Shell.close()/shutdown() path
print("after release_owner(D):")
print("  current_owner:", coord.current_owner())
print("  components:", len(coord._components))
print("  process_mutated (restore raised, was swallowed):", process_state['mutated'])
