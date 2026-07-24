import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.builtins.input_reader import InputCursor

print("=== Claim A: split C3 A9 at the read_all seam -> two surrogates, not 'e-acute' ===")
print("é is UTF-8 bytes:", 'é'.encode('utf-8').hex(), "(c3 a9)")
print()

r, w = os.pipe()
cur = InputCursor(fd=r)

# Deliver ONLY the lead byte C3 first.
os.write(w, b'\xc3')

# Drive the real char path with a short -t deadline. It reads C3 (the decoder
# buffers it, emits nothing), then blocks for the continuation byte and TIMES
# OUT. On timeout the decoder is NOT flushed -> it stays buffering C3.
res = cur.read_limited(delimiter=None, max_chars=5,
                       deadline=time.monotonic() + 0.2)
print("timed-out read_limited: outcome =", res.outcome, "data =", repr(res.data))
print("cursor._decoder is not None (buffering C3):", cur._decoder is not None)
state = cur._decoder.getstate() if cur._decoder else None
print("decoder buffered bytes:", state[0].hex() if state else None)
print()

# Now the continuation byte A9 (plus the rest of the record) arrives, and a
# read_all consumer (mapfile with no line count) drains the same OFD cursor.
os.write(w, b'\xa9rest\n')
os.close(w)

out = cur.read_all()
print("read_all() returned:", repr(out))
print("  code points:", [hex(ord(c)) for c in out])
print()

expected = 'érest\n'
print("bash-equivalent / correct decode would be:", repr(expected))
print("MATCHES correct decode:", out == expected)
print("byte round-trip survives:",
      out.encode('utf-8', 'surrogateescape') == b'\xc3\xa9rest\n')
print("char content is two lone surrogates (\\udcc3 \\udca9) instead of é:",
      out.startswith('\udcc3\udca9'))
