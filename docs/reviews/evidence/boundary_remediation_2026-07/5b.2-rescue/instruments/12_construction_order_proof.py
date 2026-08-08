#!/usr/bin/env python3
"""Instrument 12 (slot 5B.2) — construction-order proof for the (c2) member.

R1 (c2): "Concrete-class plumbing must be behavior-identical and
construction-order-proven (the manager/expander construction sequence — prove
the new attribute is live before first use, don't assume it)."

The question is whether `VariableExpander` can hold the expansion runtime as an
EAGER attribute (`self.expansion_runtime = shell.expansion_manager` in
`__init__`) or must reach it lazily. Reading the source suggests it cannot:
`shell.expansion_manager` is assigned at shell.py:265, i.e. only after
`ExpansionManager.__init__` RETURNS, while that same `__init__` constructs the
`VariableExpander` partway through. This instrument does not rely on that
reading — it observes the live construction.

Usage:  python 12_construction_order_proof.py <ROOT>
"""
import os
import pathlib
import subprocess
import sys


PROBE = r'''
import os, sys
import psh
assert os.path.dirname(psh.__file__) == os.path.join(ROOT, "psh"), \
    "DISCRIMINATOR FAILED: " + psh.__file__

from psh.expansion.variable import VariableExpander

observations = []
_orig = VariableExpander.__init__

def spy(self, shell):
    observations.append((
        hasattr(shell, "expansion_manager"),
        getattr(shell, "expansion_manager", None) is not None,
    ))
    return _orig(self, shell)

VariableExpander.__init__ = spy

from psh.shell import Shell
sh = Shell(norc=True)

print("VariableExpander constructions observed:", len(observations))
for i, (has, non_none) in enumerate(observations):
    print(f"  #{i}: hasattr(shell,'expansion_manager')={has}  non_none={non_none}")

eager_would_work = all(has for has, _ in observations)
print("EAGER `self.expansion_runtime = shell.expansion_manager` viable:",
      eager_would_work)

# And the direct demonstration: what an eager read would actually do.
VariableExpander.__init__ = _orig
class Probe:
    pass
try:
    from psh.shell import Shell as S2
    trial = object.__new__(S2)
    _ = trial.expansion_manager
    print("bare-shell eager read: OK")
except AttributeError as e:
    print("bare-shell eager read raises AttributeError:", e)

# The LAZY form, evaluated after construction, is the expression the 8 migrated
# sites use today — verify it resolves to the live manager.
ve = sh.expansion_manager.variable_expander
print("lazy shell.expansion_manager is the live manager:",
      ve.shell.expansion_manager is sh.expansion_manager)
print("PROBE_OK")
'''


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    print(f"ROOT={root}")
    print(f"HEAD={subprocess.run(['git','rev-parse','--short','HEAD'],cwd=root,capture_output=True,text=True).stdout.strip()}")
    print()
    src = f"ROOT = {str(root)!r}\n" + PROBE
    r = subprocess.run([sys.executable, "-c", src], cwd=str(root),
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(root),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    print(r.stdout.strip())
    if r.returncode != 0:
        print("--- STDERR ---")
        print(r.stderr.strip()[-1500:])
    print(f"returncode={r.returncode}")


if __name__ == "__main__":
    main()
