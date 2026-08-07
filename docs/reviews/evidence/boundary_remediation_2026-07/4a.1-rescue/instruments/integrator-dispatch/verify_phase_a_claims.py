"""Integrator verification of dev-4a-1 Phase A beyond-brief claims (A-18, B-13a).

Runs each claim in its own subprocess (results written to files, since B-13a
may close the probe's own stdio). Invoke from repo root.
"""
import os
import subprocess
import sys

ROOT = "/Users/pwilson/src/psh"
OUT = os.path.join(ROOT, "tmp/w4a1-dispatch-probes")

A18 = r"""
import psh
assert psh.__file__.startswith("/Users/pwilson/src/psh/"), psh.__file__
from psh.core.process_lease import ComponentKind, get_coordinator
coord = get_coordinator()
class Owner:
    def __init__(self, n): self.name = n
    locale = None
b = Owner("B")
coord.activate(b).release()          # quiescent owner B
a2 = Owner("A2")
def glue():
    coord.acquire_component(a2, ComponentKind.LOCALE, restore=lambda: None,
                            description="orphan")
    raise RuntimeError("injected")
try:
    coord.activate(a2, on_grant=glue)
except RuntimeError:
    pass
# The A-18 claim: find_component(B, LOCALE) hands B the orphan owned by A2.
lease = coord.find_component(b, ComponentKind.LOCALE)
print("find_component(B, LOCALE) ->", "None" if lease is None else
      f"lease(owner_ref->{getattr(lease.owner_ref(), 'name', None)!r})")
# And B's own acquire folds into the orphan:
mine = coord.acquire_component(b, ComponentKind.LOCALE,
                               restore=lambda: print("B-RESTORE-RAN"),
                               description="B's own")
print("B acquire folded into orphan:", mine is lease)
print("release_owner(B) output next (B-RESTORE-RAN should be MISSING):")
coord.release_owner(b)
print("done")
"""

B13A = r"""
import os, resource, sys
import psh
assert psh.__file__.startswith("/Users/pwilson/src/psh/"), psh.__file__
log = open(os.environ["B13A_LOG"], "w")
def w(msg): log.write(msg + "\n"); log.flush()
# Lower RLIMIT_NOFILE so F_DUPFD_CLOEXEC to >=63 must fail (fds 0..~9 fine).
resource.setrlimit(resource.RLIMIT_NOFILE, (24, 24))
from psh.shell import Shell
sh = Shell()
rc = sh.run_command("exec >" + os.environ["B13A_TARGET"])
w(f"exec rc={rc}")
from psh.core.process_lease import ComponentKind, get_coordinator
lease = get_coordinator().find_component(sh.state, ComponentKind.STD_FDS)
w(f"STD_FDS lease present={lease is not None}")
sh.close()
closed = []
for fd in (0, 1, 2):
    try:
        os.fstat(fd)
    except OSError:
        closed.append(fd)
w(f"std_fds_closed_after_close={closed}")
log.close()
"""

r = subprocess.run([sys.executable, "-c", A18], cwd=ROOT,
                   capture_output=True, text=True, timeout=60)
print("== A-18 ==")
print(r.stdout, end="")
if r.returncode != 0:
    print("rc:", r.returncode, "stderr:", r.stderr[-500:])

env = dict(os.environ)
env["B13A_LOG"] = os.path.join(OUT, "b13a-result.txt")
env["B13A_TARGET"] = os.path.join(OUT, "scratch/b13a-out.txt")
os.makedirs(os.path.join(OUT, "scratch"), exist_ok=True)
r = subprocess.run([sys.executable, "-c", B13A], cwd=ROOT, env=env,
                   capture_output=True, text=True, timeout=60)
print("== B-13a (from log file; subprocess stdio may have died) ==")
print(open(env["B13A_LOG"]).read(), end="")
print("subprocess rc:", r.returncode)
