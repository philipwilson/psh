"""CLAIM B: a failed permanent-redirect (exec) leaks the STD_FDS component lease.

apply_permanent_redirections acquires the STD_FDS lease (line ~984) BEFORE the
redirect loop; the except (lines ~1050-1055) rolls back streams+fds but never
releases the lease. A partially-failing exec therefore retains it.
"""
import os, sys
WORKTREE = '/Users/pwilson/src/psh-r22-verify'
sys.path.insert(0, WORKTREE)
os.environ['LC_ALL'] = 'C'
os.environ.pop('LC_CTYPE', None); os.environ.pop('LC_COLLATE', None)

import psh.version
assert psh.version.__file__.startswith(WORKTREE) and psh.version.__version__ == '0.750.0'
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.shell import Shell
from psh.core.process_lease import get_coordinator, ComponentKind
import fcntl

def fd_open(fd):
    try:
        fcntl.fcntl(fd, fcntl.F_GETFD)
        return True
    except OSError:
        return False

sh = Shell(norc=True)
coord = get_coordinator()

# Activate + baseline check (harmless command).
sh.run_command(":")
before = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("STD_FDS lease BEFORE exec:", before)
print("fd 7 open before:", fd_open(7), "| fd 8 open before:", fd_open(8))

# Partially-failing permanent redirect: 7>ok succeeds, 8>/bad/x fails.
okpath = os.path.join(WORKTREE, 'tmp', 'claimb_ok')
rc = sh.run_command("exec 7>%s 8>/no/such/dir/x" % okpath)
print("\nexec exit code:", rc)

after = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("STD_FDS lease AFTER failed exec:", after)
print("  lease released flag:", getattr(after, 'released', 'n/a'))
print("len(coord._components):", len(coord._components))
print("fd 7 open after (bash closes it on full rollback):", fd_open(7))
print("fd 8 open after:", fd_open(8))

# Consequence: does this poison a second shell's activation (competing-owner)?
if after is not None:
    # make sh a quiescent owner (it already is between commands: depth 0)
    print("\nactivation_depth (should be 0, quiescent owner):", coord.activation_depth)
    os.environ['LC_ALL'] = 'C'
    from psh.core.state import ShellState
    from psh.core.process_lease import LeaseError
    other = ShellState()
    other.locale.ensure_applied = lambda *a, **k: None
    try:
        other.activate()
        print("second shell activate SUCCEEDED (owner transferred)")
    except LeaseError as e:
        print("second shell activate RAISED LeaseError (SPURIOUS):", str(e)[:130])
