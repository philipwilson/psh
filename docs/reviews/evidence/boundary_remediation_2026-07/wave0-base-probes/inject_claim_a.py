"""CLAIM A fault injection: locale-apply failure during activate().

Structural claim: acquire_component appends a LOCALE ComponentLease, THEN
ensure_applied() is called. If ensure_applied raises, coordinator.activate
rolls back owner + activation stack but NOT the component list -> leftover
live lease, no restore call.
"""
import os, sys
WORKTREE = '/Users/pwilson/src/psh-r22-verify'
sys.path.insert(0, WORKTREE)
# Force a non-C locale so pending_libc is True (lease is taken during grant).
os.environ['LC_ALL'] = 'en_US.UTF-8'
os.environ.pop('LC_CTYPE', None)
os.environ.pop('LC_COLLATE', None)

import psh.version
assert psh.version.__file__.startswith(WORKTREE), psh.version.__file__
assert psh.version.__version__ == '0.750.0', psh.version.__version__
print("DISCRIMINATOR OK:", psh.version.__file__, psh.version.__version__)

import psh.core.state as state_mod
from psh.core.state import ShellState
from psh.core.process_lease import get_coordinator, ComponentKind

# Count restore invocations at the module seam the _restore closure uses.
restore_calls = {'n': 0}
_orig_restore = state_mod.restore_libc_locale
def _counting_restore(names):
    restore_calls['n'] += 1
    return _orig_restore(names)
state_mod.restore_libc_locale = _counting_restore

st = ShellState()
print("pending_libc before activate:", st.locale.pending_libc)
print("profile:", st.locale.profile.ctype_mode, st.locale.profile.collate_mode)

coord = get_coordinator()
print("coord owner BEFORE:", coord.current_owner(), "depth:", coord.activation_depth,
      "components:", len(coord._components))

# INJECT: make the libc application step raise.
def _boom(*a, **k):
    raise RuntimeError("INJECTED: setlocale application failed")
st.locale.ensure_applied = _boom

raised = None
try:
    st.activate()
except BaseException as e:
    raised = e

print("\n--- AFTER failed activate() ---")
print("activate raised:", type(raised).__name__, str(raised))
print("coord.current_owner():", coord.current_owner())
print("coord.activation_depth:", coord.activation_depth)
print("len(coord._components):", len(coord._components))
for c in coord._components:
    print("   leftover component: kind=%s released=%s owner_alive=%s owner_is_st=%s"
          % (c.kind.name, c.released, c.owner_ref() is not None, c.owner_ref() is st))
print("restore_libc_locale calls:", restore_calls['n'])
print("active_locale() is st.locale:", state_mod.active_locale() is st.locale)

# Consequence probe 1: does close() (release_owner) clean the leftover?
print("\n--- release_owner(st) [the Shell.close path] ---")
coord.release_owner(st)
print("after release_owner: owner=%s depth=%s components=%s restore_calls=%s"
      % (coord.current_owner(), coord.activation_depth, len(coord._components),
         restore_calls['n']))

# Consequence probe 2: does a DIFFERENT shell activating clean it?
if len(coord._components) > 0:
    os.environ['LC_ALL'] = 'C'
    st2 = ShellState()
    st2.locale.ensure_applied = lambda *a, **k: None  # no real setlocale
    try:
        st2.activate()
    except BaseException as e:
        print("st2.activate raised:", e)
    print("after st2.activate: owner_is_st2=%s depth=%s components=%s restore_calls=%s"
          % (coord.current_owner() is st2, coord.activation_depth,
             len(coord._components), restore_calls['n']))
