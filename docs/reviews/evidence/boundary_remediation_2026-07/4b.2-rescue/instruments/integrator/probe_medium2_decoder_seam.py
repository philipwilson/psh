"""Brief-time evidence probe for slot 4B.2 (MEDIUM-2 + A5 rider), at base 21a23a4c.

Run from the slot worktree with PYTHONPATH set to it. Two legs:
  1. MEDIUM-2 decoder seam: a timed read consumes the first byte of UTF-8
     'é' (C3 A9) into the cursor's incremental decoder; the bulk drain
     (read_all) then finalizes that decoder with EMPTY input and decodes
     the tail with a FRESH decoder -> two surrogates instead of é.
  2. A5 rider: `read -t 1 -N 3` hangs (deadline never passed to
     read_limited); bash times out ~1s. Control: `read -t 1 -n 3` in psh
     times out correctly.
"""
import os
import sys
import time
import subprocess

import psh
print("DISCRIMINATOR:", psh.__file__)
from psh.builtins.input_reader import InputCursor  # noqa: E402

# --- Leg 1: decoder-seam split ------------------------------------------
r, w = os.pipe()
cur = InputCursor(fd=r)
os.write(w, b'\xc3')                      # first byte of é only
res = cur.read_record(delimiter='\n', include_delimiter=False,
                      deadline=time.monotonic() + 0.10)
print("leg1 timed read outcome:", res.outcome.name, "data:", repr(res.data))
os.write(w, b'\xa9\n')                    # rest of é + newline
os.close(w)
out = cur.read_all()
expected = 'é\n'
print("leg1 read_all:", repr(out), "| expected:", repr(expected),
      "| CORRUPTED:" , out != expected,
      "| surrogates:", [hex(ord(c)) for c in out if 0xDC80 <= ord(c) <= 0xDCFF])
os.close(r)

# byte round-trip check (the finding says round-trip "happens to survive")
rt = out.encode('utf-8', errors='surrogateescape')
print("leg1 byte round-trip:", rt == b'\xc3\xa9\n')

# --- Leg 2: read -t with -N hangs (rider) -------------------------------
def timed_shell(argv0, extra, script, feed_delay):
    rr, ww = os.pipe()
    p = subprocess.Popen([argv0, *extra, '-c', script], stdin=rr,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
    os.close(rr)
    t0 = time.monotonic()
    try:
        out, err = p.communicate(timeout=4)
        dt = time.monotonic() - t0
        return f"rc={p.returncode} dt={dt:.1f}s out={out.strip()!r}"
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate()
        return "HUNG (>4s, killed)"
    finally:
        os.close(ww)

script_N = 'read -t 1 -N 3 v; echo "rc=$? v=<$v>"'
script_n = 'read -t 1 -n 3 v; echo "rc=$? v=<$v>"'
print("leg2 psh  -N with -t:", timed_shell(sys.executable, ['-m', 'psh'], script_N, None))
print("leg2 bash -N with -t:", timed_shell('/opt/homebrew/bin/bash', [], script_N, None))
print("leg2 psh  -n with -t (control):", timed_shell(sys.executable, ['-m', 'psh'], script_n, None))
