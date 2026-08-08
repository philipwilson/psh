# Q1 probe 08c: the quarantine-blocks-grants claim must BITE — with a
# quarantined lease NOT cleared, the next ownership grant must be refused.
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

from psh.core.state import ShellState
from psh.core.process_lease import get_coordinator, ComponentKind, LeaseError

coord = get_coordinator()
D = ShellState()
D.locale.ensure_applied = lambda *a, **k: None
la = D.activate()
la.release()
coord.acquire_component(D, ComponentKind.STD_FDS,
                        restore=lambda: (_ for _ in ()).throw(OSError("boom")),
                        description="q1-blocks")
try:
    coord.release_owner(D)
except Exception as e:
    print("release_owner raised:", type(e).__name__)
print("quarantined:", coord.quarantine_report())

E = ShellState()
E.locale.ensure_applied = lambda *a, **k: None
try:
    E.activate()
    print("E.activate WITHOUT clear: SUCCEEDED  <-- quarantine did NOT block (claim fails)")
except LeaseError as e:
    print("E.activate WITHOUT clear: REFUSED (LeaseError):", str(e)[:140])
