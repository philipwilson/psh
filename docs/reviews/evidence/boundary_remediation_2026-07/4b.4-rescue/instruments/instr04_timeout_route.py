"""INSTR04 — A1 census, R-TIMEOUT row, on the marker-anchored harness (A0).

The R-TIMEOUT route feeds WELL-FORMED input: `\xc3` is the valid lead byte
of `é` that simply had not arrived when the deadline expired. So the oracle
here is AMBIENT UTF-8 bash (not the C-locale oracle DECISION 1 assigned to
the malformed model) — this is the A3 oracle-locale axis, and it is the
reason these cells are NOT covered by the I1 deliberate-loss registry's
"ultra-rare malformed count boundary" framing.

Every cell is anchored to the CHILD's marker (defect ID-1), so bash and psh
are compared at the same LOGICAL position despite very different startup
latencies.

Run:  python tmp/w4b4/instr04_timeout_route.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, PSH, REPO, discriminate, feed  # noqa: E402

discriminate()
print()


def cell(name, script, phases, marker, note="", expect=None):
    psh, sp = feed(PSH, script, phases, marker)
    amb, sa = feed(BASH, script, phases, marker)
    verdict = 'MATCH' if psh == amb else 'DIVERGE'
    print(f"[{verdict:7}] {name}")
    print(f"           psh      [{sp}]: {psh!r}")
    print(f"           bash-utf8[{sa}]: {amb!r}")
    if note:
        print(f"           note: {note}")
    print()
    return verdict


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    M = os.path.join(d, 'marker')
    F = os.path.join(d, 'f.txt')
    with open(F, 'wb') as fh:
        fh.write(b'FILELINE\nF2\n')
    FIFO = os.path.join(d, 'fifo')
    os.mkfifo(FIFO)

    STRAND = f': > {M}; read -t 2 -N 2 v; '

    print("=" * 72)
    print("R-TIMEOUT x each surface (oracle = AMBIENT UTF-8 bash: the input")
    print("is WELL-FORMED, merely incomplete at the deadline)")
    print("=" * 72)

    cell("R-TIMEOUT x S-SAMEFD (this IS D-4B.2-s1)",
         STRAND + "read -t 2 -N 1 w; printf 'v=<%s> w=<%s>\\n' \"$v\" \"$w\" | od -c | head -2",
         [(0.05, b'\xc3')], M,
         "bash assigns the partial at timeout; psh holds it for the next read.")

    cell("R-TIMEOUT x S-TEMPFRAME forward (LEG A)",
         STRAND + f"read x < {F}; "
         "printf 'v=%s|x=%s\\n' \"$v\" \"$x\" | od -c | head -2",
         [(0.05, b'\xc3')], M,
         "the stranded stdin byte is PREPENDED to a read from a DIFFERENT FILE.")

    cell("R-TIMEOUT x S-DUP (LEG B)",
         STRAND + "exec 3<&0; read -t 2 -u 3 y; read -t 2 -N 1 w; "
         "printf 'v=%s|y=%s|w=%s\\n' \"$v\" \"$y\" \"$w\" | od -c | head -2",
         [(0.05, b'\xc3'), (3.0, b'\xa9Z\n')], M,
         "phase 2 lands inside the y-read window, anchored to the CHILD.")

    cell("R-TIMEOUT x S-EXECREBIND (must-hold: cursor dropped)",
         STRAND + f"exec 0<{F}; read b; printf 'v=%s|b=%s\\n' \"$v\" \"$b\" | od -c | head -2",
         [(0.05, b'\xc3')], M,
         "rebind must drop the stranded decoder state.")

    cell("R-TIMEOUT x S-FORK (child registry fresh)",
         STRAND + "( read -t 2 -N 1 c; printf 'child=%s\\n' \"$c\" ) ; "
         "printf 'v=%s\\n' \"$v\" | od -c | head -2",
         [(0.05, b'\xc3'), (2.2, b'\xa9Z\n')], M,
         "does the child see the byte the parent stranded?")

    print("=" * 72)
    print("R-TIMEOUT x S-TEMPFRAME **REVERSE** — strand while fd 0 IS the temp")
    print("source (a FIFO, so the deadline can expire mid-character), then read")
    print("real stdin. Mirror of the malformed reverse face in INSTR03.")
    print("=" * 72)

    # Writer opens the FIFO and feeds only a lead byte, so the temp-framed
    # read times out mid-character with fd 0 pointing at the FIFO.
    def fifo_cell(argv, label):
        import subprocess
        import threading
        from harness import env
        script = (f': > {M}; read -t 2 -N 2 a < {FIFO}; read b; '
                  "printf 'a=%s|b=%s\\n' \"$a\" \"$b\" | od -c | head -2")
        if os.path.exists(M):
            os.unlink(M)
        r, w = os.pipe()
        p = subprocess.Popen(argv + ['-c', script], stdin=r,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=REPO, env=env())
        os.close(r)
        os.write(w, b'STDIN1\n')          # real stdin content, available early

        def writer():
            # Blocks until the child opens the FIFO for reading.
            fd = os.open(FIFO, os.O_WRONLY)
            os.write(fd, b'\xc3')          # lead byte only -> deadline expires
            import time
            time.sleep(3.0)
            os.close(fd)
        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            out, _ = p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
            out = b'HUNG'
        t.join(6)
        try:
            os.close(w)
        except OSError:
            pass
        print(f"           {label}: {out!r}")
        return out

    pshr = fifo_cell(PSH, "psh      ")
    bashr = fifo_cell(BASH, "bash-utf8")
    print(f"[{'MATCH' if pshr == bashr else 'DIVERGE'}] "
          "R-TIMEOUT x S-TEMPFRAME REVERSE")
