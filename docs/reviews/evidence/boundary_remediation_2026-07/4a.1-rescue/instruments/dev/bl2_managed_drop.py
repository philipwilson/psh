"""BL-2 reproduction: setup_signal_handlers() + drop WITHOUT close().

Does an unrelated later shell still run?  Base: yes (handlers leaked, but
ownership was never taken).  Tip: the MANAGED_SIGNALS lease is held by an
owner the SignalRegistry keeps alive, so it is never classified an orphan,
never swept, and every later shell is rejected.
"""
import gc
import os
import sys

import psh
print("DISCRIM", os.path.abspath(psh.__file__))
from psh.core.process_lease import LeaseError, get_coordinator  # noqa: E402
from psh.shell import Shell  # noqa: E402

coord = get_coordinator()


def leases():
    return sorted(c.kind.name for c in coord._components if not c.released)


a = Shell(norc=True)
a.state.is_script_mode = True
a.interactive_manager.signal_manager.setup_signal_handlers()
print("after setup      leases:", leases() or "-")
del a
gc.collect()
print("after drop+gc    leases:", leases() or "-",
      "| owner:", "ALIVE" if coord.current_owner() is not None else "COLLECTED")

b = Shell(norc=True)
try:
    rc = b.run_command("echo next >/dev/null")
    print("NEXT SHELL RAN   rc:", rc)
except LeaseError as exc:
    print("NEXT SHELL REJECTED:", str(exc).split(';')[0])
