# Q1 probe 09 (LOW STD_FDS lease): a partially-failing `exec` must release
# exactly the STD_FDS state it itself acquired, and not poison later shells.
# Fresh 0.773.0 equivalent of wave0-base-probes/inject_claim_b.py.
# Base bug: failed exec RETAINED the lease; fd 7 stayed open.
# Axis: REGRESSION vs recorded base bug (bash closes fd 7 on full rollback).
import fcntl
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
os.environ['LC_ALL'] = 'C'
os.environ.pop('LC_CTYPE', None)
os.environ.pop('LC_COLLATE', None)
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.shell import Shell
from psh.core.process_lease import get_coordinator, ComponentKind, LeaseError


def fd_open(fd):
    try:
        fcntl.fcntl(fd, fcntl.F_GETFD)
        return True
    except OSError:
        return False


sh = Shell(norc=True)
coord = get_coordinator()
sh.run_command(":")
before = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("STD_FDS lease BEFORE exec:", before)
print("fd 7 open before:", fd_open(7), "| fd 8 open before:", fd_open(8))

okpath = os.path.join(WT, 'tmp', 'q1_claimb_ok')
rc = sh.run_command("exec 7>%s 8>/no/such/dir/x" % okpath)
print("exec exit code:", rc)

after = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("STD_FDS lease AFTER failed exec:", after)
if after is not None:
    print("  released flag:", getattr(after, 'released', 'n/a'))
print("fd 7 open after (bash closes on full rollback):", fd_open(7))
print("fd 8 open after:", fd_open(8))

from psh.core.state import ShellState
other = ShellState()
other.locale.ensure_applied = lambda *a, **k: None
try:
    other.activate()
    print("second shell activate: SUCCEEDED")
except LeaseError as e:
    print("second shell activate: SPURIOUS LeaseError:", str(e)[:120])

# discrimination cell: an EARLIER legitimate permanent redirect's lease
# must survive a LATER failing exec untouched.
sh2 = Shell(norc=True)
ok2 = os.path.join(WT, 'tmp', 'q1_claimb_ok2')
sh2.run_command("exec 9>%s" % ok2)
lease1 = coord.find_component(sh2.state, ComponentKind.STD_FDS)
print("legit lease after exec 9>ok:", lease1 is not None)
rc2 = sh2.run_command("exec 8>/no/such/dir/x")
lease2 = coord.find_component(sh2.state, ComponentKind.STD_FDS)
print("failing exec rc:", rc2,
      "| earlier lease still present and same:", lease2 is lease1,
      "| fd 9 still open:", fd_open(9))
sh2.close()
