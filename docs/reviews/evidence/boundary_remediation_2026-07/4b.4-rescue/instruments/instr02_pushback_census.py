"""INSTR02 — P1: `_pushback` producer census (static + dynamic).

The brief's recon says `_pushback` has 0 references outside input_reader.py
and 7 inside, and asks: does any LIVE path append? A grep count cannot
answer that — a self-feeding writer looks like a writer to grep. So this
instrument does both halves:

  STATIC  — classify every occurrence as reader / writer / init, and trace
            the data dependency of each writer's SOURCE.
  DYNAMIC — install a tripwire that records ANY moment `_pushback` becomes
            non-empty, then drive the real consumers (the byte-record path
            is `StdinInput`'s, so the stimulus is a psh SCRIPT ON STDIN,
            not just `read`), and report.

Proof-shape: the static half is BY-ELIMINATION; the dynamic half is
CHARACTERIZATION over the exercised paths (it cannot prove a path that was
never driven, which is why the driven set is printed).

Run:  python tmp/w4b4/instr02_pushback_census.py
"""
import os
import subprocess
import sys

REPO = '/Users/pwilson/src/psh-r4b-4'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
print("DISCRIMINATOR:", psh.__file__)
print()

SRC = os.path.join(REPO, 'psh/builtins/input_reader.py')

print("=" * 70)
print("STATIC HALF — every `_pushback` occurrence, classified")
print("=" * 70)
with open(SRC) as fh:
    for n, line in enumerate(fh, 1):
        if '_pushback' in line:
            print(f"{n:4d}: {line.rstrip()}")
print()
print("Occurrences OUTSIDE input_reader.py (whole psh/ tree):")
subprocess.run(
    ["grep", "-rn", "_pushback", "--include=*.py", os.path.join(REPO, "psh")],
    check=False)
print("(empty above == none)")
print()

print("=" * 70)
print("DYNAMIC HALF — tripwire on every mutation of _pushback")
print("=" * 70)

from psh.builtins.input_reader import InputCursor  # noqa: E402

_TRIPS = []


class _Watched(bytearray):
    """A bytearray that records every call that could make it non-empty."""

    def __iadd__(self, other):
        if other:
            _TRIPS.append(("iadd", bytes(other)))
        return super().__iadd__(other)

    def extend(self, other):
        data = bytes(other)
        if data:
            _TRIPS.append(("extend", data))
        return super().extend(data)

    def append(self, item):
        _TRIPS.append(("append", item))
        return super().append(item)


_orig_init = InputCursor.__init__


def _patched_init(self, **kw):
    _orig_init(self, **kw)
    self._pushback = _Watched()


InputCursor.__init__ = _patched_init

# Also catch WHOLE-OBJECT REBINDING (`self._pushback = bytearray(...)`),
# which a subclass of bytearray cannot see. This is the line-306 writer,
# and it is the one the census actually turns on.
_REBINDS = []
_orig_setattr = InputCursor.__setattr__


def _patched_setattr(self, name, value):
    if name == '_pushback' and value and not isinstance(value, _Watched):
        _REBINDS.append(bytes(value))
    _orig_setattr(self, name, value)


InputCursor.__setattr__ = _patched_setattr

DRIVEN = []


def drive(label, stdin_bytes, must_contain):
    """Feed psh a SCRIPT ON STDIN; VALIDITY-CHECK that the stimulus ran.

    `must_contain` is the control (4B.2 lesson 1): if the expected marker is
    absent the stimulus did NOT exercise the path, and a census that counted
    it would be counting a no-op. stderr is captured and shown, never
    discarded — the earlier version of this instrument discarded it and read
    an empty stdout as "ran fine" (defect ID-2, ledgered).
    """
    DRIVEN.append(label)
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'PYTHONPATH': REPO, 'TERM': 'dumb', 'PSH_STRICT_ERRORS': '1'}
    r = subprocess.run([sys.executable, '-m', 'psh'], input=stdin_bytes,
                       cwd=REPO, env=env, capture_output=True, timeout=30)
    ok = must_contain in r.stdout
    print(f"   [{'VALID' if ok else 'INVALID-STIMULUS'}] {label}")
    print(f"     rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")
    # Same stimulus through the ORACLE, to show the script shape is not a
    # psh-ism: bash's stdin-script `read` consumes following lines too.
    rb = subprocess.run(BASH, input=stdin_bytes, capture_output=True,
                        timeout=30, env=env)
    print(f"     bash: rc={rb.returncode} stdout={rb.stdout!r}")
    return ok


BASH = ['/opt/homebrew/bin/bash']

# The byte-record path (read_record_bytes) belongs to StdinInput: a psh
# SCRIPT FED ON STDIN, where `read` inside the script consumes SUBSEQUENT
# physical lines as data. NOTE the script shape: `read` and its consumer
# must share ONE physical line, because `read` on its own line would consume
# the consumer line itself as data (that is what silently defeated the first
# version of this stimulus — ID-2).
print("-- driving the byte-record path (script on stdin) --")
all_valid = True
all_valid &= drive("script-on-stdin: read consumes the FOLLOWING line",
                   b"read x; echo got:$x\nDATALINE\n", b"got:DATALINE")
all_valid &= drive("script-on-stdin: two reads, two data lines",
                   b"read a; read b; echo \"[$a][$b]\"\nL1\nL2\n", b"[L1][L2]")
all_valid &= drive("script-on-stdin: malformed byte in the consumed data",
                   b"read x; printf 'x=%s|\\n' \"$x\"\n\xc3A\n", b"x=")
print(f"   ALL STIMULI VALID: {bool(all_valid)}")

print()
print("NOTE: the subprocess runs in a CHILD, so the in-process tripwire")
print("above cannot see it. The in-process arm follows.")
print()

print("-- in-process arm: drive InputCursor's byte path directly --")
r, w = os.pipe()
os.write(w, b"alpha\nbeta\n\xc3A\ngamma\n")
os.close(w)
cur = InputCursor(fd=r)
recs = []
while True:
    rec = cur.read_record_bytes(delimiter_byte=0x0A)
    if rec is None:
        break
    recs.append(rec)
os.close(r)
print("   records:", recs)
print("   _pushback after full drain:", repr(bytes(cur._pushback)))

print()
print("=" * 70)
print("RESULT")
print("=" * 70)
print("driven stimuli:", len(DRIVEN))
for d in DRIVEN:
    print("  -", d)
print("in-place mutations recorded (append/extend/+=):", _TRIPS)
print("non-empty REBINDS recorded (`self._pushback = bytearray(...)`):", _REBINDS)
