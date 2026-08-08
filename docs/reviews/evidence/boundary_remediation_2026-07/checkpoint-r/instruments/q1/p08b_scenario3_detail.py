# Q1 probe 08b: scenario-3 follow-up — WHY is is_clean False after
# clear_quarantine? Enumerate each is_clean conjunct.
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
from psh.core.process_lease import get_coordinator, ComponentKind

coord = get_coordinator()
D = ShellState()
D.locale.ensure_applied = lambda *a, **k: None
la = D.activate()
la.release()


def raising_restore():
    raise OSError("INJECTED: restore failed")


coord.acquire_component(D, ComponentKind.STD_FDS,
                        restore=raising_restore, description="q1-test")
try:
    coord.release_owner(D)
except Exception as e:
    print("release_owner raised:", type(e).__name__)


def state(tag):
    print(tag,
          "| owner:", coord.current_owner() is not None,
          "| owner_is_D:", coord.current_owner() is D,
          "| depth:", coord.activation_depth,
          "| live:", len(coord._live_components()),
          "| quarantined:", len(coord._quarantined),
          "| is_clean:", coord.is_clean())


state("after failed release_owner")
cleared = coord.clear_quarantine()
print("cleared:", cleared)
state("after clear_quarantine   ")
# does a NEXT ownership event work after clearing?
E = ShellState()
E.locale.ensure_applied = lambda *a, **k: None
try:
    E.activate()
    print("next shell activate after clear: SUCCEEDED")
except Exception as e:
    print("next shell activate after clear:", type(e).__name__, str(e)[:100])
state("after E activate         ")
