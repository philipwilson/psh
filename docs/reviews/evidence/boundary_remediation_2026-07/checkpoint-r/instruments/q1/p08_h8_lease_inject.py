# Q1 probe 08 (HIGH-8): lease rollback / orphan sweep / quarantine at tip.
# Fresh 0.773.0 equivalents of wave0-base-probes/inject_claim_a{,2,3}.py.
# Run each scenario in a FRESH process: python p08... <1|2|3> (driver below).
# Base bugs: (1) failed activate left a live LOCALE lease w/ no restore;
# (2) that leftover poisoned a third shell's activation (spurious LeaseError);
# (3) release_owner force-release SWALLOWED a raising restore silently.
# Tip claims (v0.768.0): checkpointed rollback unwinds LIFO; orphan sweep;
# raising restore -> lease QUARANTINED + aggregate LeaseRestoreError raised,
# observable via is_clean/quarantine_report/clear_quarantine.
# Axis: REGRESSION vs recorded base bugs.
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
scenario = sys.argv[1]
if scenario in ('1', '2'):
    os.environ['LC_ALL'] = 'en_US.UTF-8'
else:
    os.environ['LC_ALL'] = 'C'
os.environ.pop('LC_CTYPE', None)
os.environ.pop('LC_COLLATE', None)

assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__, "scenario", scenario)

from psh.core.state import ShellState
from psh.core.process_lease import (get_coordinator, ComponentKind, LeaseError,
                                    LeaseRestoreError)

coord = get_coordinator()


def boom(*a, **k):
    raise RuntimeError("INJECTED: locale apply failed")


if scenario == '1':
    st = ShellState()
    print("pending_libc:", st.locale.pending_libc)
    st.locale.ensure_applied = boom
    raised = None
    try:
        st.activate()
    except BaseException as e:
        raised = e
    print("activate raised:", type(raised).__name__ if raised else None)
    live = [c for c in coord._components if not c.released]
    print("live components after failed activate:", len(live))
    for c in live:
        print("   leftover: kind=%s owner_is_st=%s" % (c.kind.name, c.owner_ref() is st))
    coord.release_owner(st)
    print("after release_owner: live components:",
          len([c for c in coord._components if not c.released]))
    # third shell: C locale, must activate cleanly
    os.environ['LC_ALL'] = 'C'
    st2 = ShellState()
    st2.locale.ensure_applied = lambda *a, **k: None
    try:
        st2.activate()
        print("second shell activate: SUCCEEDED")
    except LeaseError as e:
        print("second shell activate: SPURIOUS LeaseError:", str(e)[:120])

elif scenario == '2':
    os.environ['LC_ALL'] = 'C'
    A = ShellState()
    A.locale.ensure_applied = lambda *a, **k: None
    la = A.activate()
    la.release()
    print("A quiescent owner:", coord.current_owner() is A,
          "depth:", coord.activation_depth)
    os.environ['LC_ALL'] = 'en_US.UTF-8'
    B = ShellState()
    print("B pending_libc:", B.locale.pending_libc)
    B.locale.ensure_applied = boom
    try:
        B.activate()
        print("B.activate unexpectedly SUCCEEDED")
    except BaseException as e:
        print("B.activate raised:", type(e).__name__)
    live = [c for c in coord._components if not c.released]
    print("live components after B failure:", len(live))
    os.environ['LC_ALL'] = 'C'
    C = ShellState()
    C.locale.ensure_applied = lambda *a, **k: None
    try:
        C.activate()
        print("C.activate: SUCCEEDED (no poisoning)")
    except LeaseError as e:
        print("C.activate: SPURIOUS LeaseError:", str(e)[:120])

elif scenario == '3':
    D = ShellState()
    D.locale.ensure_applied = lambda *a, **k: None
    la = D.activate()
    la.release()
    print("D quiescent owner:", coord.current_owner() is D)

    def raising_restore():
        raise OSError("INJECTED: restore failed")

    coord.acquire_component(D, ComponentKind.STD_FDS,
                            restore=raising_restore, description="q1-test")
    print("is_clean before release:", coord.is_clean())
    raised = None
    try:
        coord.release_owner(D)
    except BaseException as e:
        raised = e
    print("release_owner raised:", type(raised).__name__ if raised else "NOTHING (swallowed)")
    print("isinstance LeaseRestoreError:", isinstance(raised, LeaseRestoreError))
    print("isinstance LeaseError:", isinstance(raised, LeaseError))
    print("is_clean after:", coord.is_clean())
    rep = coord.quarantine_report()
    print("quarantine_report:", rep)
    cleared = coord.clear_quarantine()
    print("clear_quarantine returned:", cleared)
    print("is_clean after clear:", coord.is_clean())
