# Q1 probe 09b (LOW STD_FDS, discrimination cell, fresh process): an EARLIER
# legitimate permanent redirect's lease must survive a LATER failing exec.
# (p09 ran this in the same process as an un-released ShellState activation;
# the resulting competing-owner LeaseError was the probe's own sequencing
# error — the guard firing correctly — so the cell reruns here isolated.)
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
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.shell import Shell
from psh.core.process_lease import get_coordinator, ComponentKind


def fd_open(fd):
    try:
        fcntl.fcntl(fd, fcntl.F_GETFD)
        return True
    except OSError:
        return False


coord = get_coordinator()
sh = Shell(norc=True)
ok2 = os.path.join(WT, 'tmp', 'q1_claimb_ok2')
rc0 = sh.run_command("exec 9>%s" % ok2)
lease1 = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("legit exec 9>ok rc:", rc0, "| lease present:", lease1 is not None,
      "| fd 9 open:", fd_open(9))
rc1 = sh.run_command("exec 8>/no/such/dir/x")
lease2 = coord.find_component(sh.state, ComponentKind.STD_FDS)
print("failing exec rc:", rc1,
      "| earlier lease still present:", lease2 is not None,
      "| same lease object:", lease2 is lease1,
      "| fd 9 still open:", fd_open(9),
      "| fd 8 open:", fd_open(8))
print("RESULT:", "PASS" if (rc1 != 0 and lease2 is lease1 and fd_open(9)
                            and not fd_open(8)) else "FAIL")
sh.close()
