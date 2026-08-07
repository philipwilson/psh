"""Brief-time evidence probe for slot 4A.1 (A5 multi-shell poisoning), at base.

Run as a SUBPROCESS from the repo root (cwd=/Users/pwilson/src/psh) so the
tree under test is the one imported. Discriminator printed first.

Scenarios (A5 wording):
  S1  shell A fails activation (glue fails AFTER acquiring a component)
      -> does unrelated shell C activate cleanly?           [first-owner case]
  S1b transfer-rollback variant: quiescent owner B, then A's transfer-grant
      fails after glue acquired a component -> is C (and B) poisoned?
  S2  real-shell: A takes STD_FDS lease (exec >file), dropped WITHOUT close,
      gc.collect() -> does fresh shell C execute cleanly?
  S3  release_owner sweep: after S1b poison, does release_owner(A) sweep the
      orphan (A5 says it early-returns)?
"""
import gc
import os
import sys

import psh
print("DISCRIMINATOR psh module:", psh.__file__)
from psh.core.process_lease import (ComponentKind, LeaseError,  # noqa: E402
                                    get_coordinator)

coord = get_coordinator()


class Owner:
    def __init__(self, name):
        self.name = name
    locale = None


def show(tag):
    comps = [(c.kind.name, c.released) for c in coord._components]
    owner = coord.current_owner()
    print(f"  [{tag}] owner={getattr(owner, 'name', owner)!r} "
          f"depth={coord.activation_depth} components={comps}")


print("== S1: first-owner failed activation, glue acquired component ==")
a = Owner("A")
def glue_fail():
    coord.acquire_component(a, ComponentKind.LOCALE, restore=lambda: None,
                            description="probe-orphan")
    raise RuntimeError("injected post-acquire glue failure")
try:
    coord.activate(a, on_grant=glue_fail)
    print("  UNEXPECTED: activation succeeded")
except RuntimeError as e:
    print(f"  A activation failed as injected: {e}")
show("after A failure")
c = Owner("C")
try:
    lease = coord.activate(c)
    print("  C activated CLEANLY")
    show("after C activate")
    lease.release()
    coord.release_owner(c)
except LeaseError as e:
    print(f"  C POISONED: {e}")
show("S1 end")

print("== S1b: transfer-rollback variant (quiescent B, A transfer fails) ==")
b = Owner("B")
bl = coord.activate(b)
bl.release()          # B quiescent, still owner, no components
show("B quiescent owner")
a2 = Owner("A2")
def glue_fail2():
    coord.acquire_component(a2, ComponentKind.LOCALE, restore=lambda: None,
                            description="probe-orphan-2")
    raise RuntimeError("injected transfer-grant failure")
try:
    coord.activate(a2, on_grant=glue_fail2)
    print("  UNEXPECTED: transfer succeeded")
except RuntimeError as e:
    print(f"  A2 transfer-grant failed as injected: {e}")
show("after A2 failure")
c2 = Owner("C2")
try:
    lease = coord.activate(c2)
    print("  C2 activated CLEANLY")
    lease.release()
    coord.release_owner(c2)
except LeaseError as e:
    print(f"  C2 POISONED: {e}")
print("== S3: does release_owner(A2) sweep the orphan? ==")
coord.release_owner(a2)
show("after release_owner(A2)")
n_orphan = sum(1 for cc in coord._components if not cc.released)
print(f"  orphan components remaining: {n_orphan}")
# clean up for S2: force-sweep via the legitimate owner if any
owner_now = coord.current_owner()
if owner_now is not None:
    coord.release_owner(owner_now)
coord._force_release_components()
show("cleaned for S2")

print("== S2: real shell, STD_FDS lease, dropped without close ==")
from psh.shell import Shell  # noqa: E402
os.makedirs("tmp/w4a1-dispatch-probes/scratch", exist_ok=True)
sh_a = Shell()
rc = sh_a.run_command("exec 3>tmp/w4a1-dispatch-probes/scratch/keep3.txt")
rc2 = sh_a.run_command("exec >tmp/w4a1-dispatch-probes/scratch/out.txt")
print(f"  A exec redirects rc={rc},{rc2}", file=sys.stderr)
show("A holds STD_FDS")
del sh_a
gc.collect()
show("A dropped+gc")
sh_c = Shell()
try:
    rc3 = sh_c.run_command("true")
    print(f"  C executed CLEANLY rc={rc3}", file=sys.stderr)
except LeaseError as e:
    print(f"  C POISONED: {e}", file=sys.stderr)
show("S2 end")
print("PROBE COMPLETE", file=sys.stderr)
