# Q1 probe 13 (HIGH-1): the oracle's `yes` false-green is impossible at tip —
# typed outcomes; is_comparable is the sole comparability authority and must
# refuse the truncated/killed pair the base scored IDENTICAL.
# Axis: REGRESSION vs recorded base bug (rc -9 + 8MB truncation => IDENTICAL).
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, 'tests', 'harness'))
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

import shell_oracle
from shell_oracle import run_psh, run_bash, is_comparable

print("shell_oracle from:", shell_oracle.__file__)
p = run_psh(['-c', 'yes'])
b = run_bash(['-c', 'yes'])
for name, r in [('psh', p), ('bash', b)]:
    print("%s outcome: type=%s" % (name, type(r).__name__))
    for attr in ('outcome', 'kind', 'status', 'returncode', 'truncated',
                 'timed_out', 'signal'):
        if hasattr(r, attr):
            print("   .%s = %r" % (attr, getattr(r, attr)))
print("is_comparable(psh):", is_comparable(p))
print("is_comparable(bash):", is_comparable(b))
print("FALSE-GREEN POSSIBLE:", bool(is_comparable(p) and is_comparable(b)))

# control: a genuinely comparable pair still compares
cp = run_psh(['-c', 'echo ok'])
cb = run_bash(['-c', 'echo ok'])
print("control comparable:", is_comparable(cp) and is_comparable(cb),
      "| equal:", (cp.stdout, cp.returncode) == (cb.stdout, cb.returncode))
