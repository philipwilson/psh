"""INSTR03 — A1 census: STRANDING ROUTE x CONTRACT SURFACE.

Routes that can leave userspace state on a cursor:
  R-TIMEOUT   `-t` expiry mid-multibyte  -> bytes buffered in `_decoder`
  R-ERROR     read error mid-multibyte   -> same buffer, different exit
  R-MALFORMED `read -N k` splitting a malformed sequence -> surplus in `_decoded`
  R-PUSHBACK  `_pushback` (INSTR02: provably always empty)

Surfaces:
  S-SAMEFD  S-TEMPFRAME  S-DUP  S-EXECREBIND  S-FORK

ORACLE-LOCALE AXIS (A3), and why it matters: I1's DECISION 1 pinned psh's
MALFORMED model against **C-locale** bash (byte-per-char), because psh's
hybrid model matches C there and ambient UTF-8 bash has mbrtowc quirks. But
the R-TIMEOUT cells feed WELL-FORMED input (\xc3 is a valid `é` lead that
merely had not arrived yet), so their oracle is **ambient UTF-8** bash.
Every cell below prints BOTH bash arms and names which one is its oracle;
mixing them is how this slot could talk itself into a false parity.

Deterministic cells only (no timing) live here; the two-phase timeout cells
use the marker-anchored harness (INSTR04).

Run:  python tmp/w4b4/instr03_census.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, PSH, REPO, discriminate, env  # noqa: E402

discriminate()
print()


def run(argv, script, stdin_bytes, extra_env=None):
    r = subprocess.run(argv + ['-c', script], input=stdin_bytes, cwd=REPO,
                       env=env(extra_env), capture_output=True, timeout=30)
    return r.stdout


def cell(name, oracle, script, stdin_bytes, note=""):
    """Run one census cell in psh, ambient bash and C-locale bash."""
    psh = run(PSH, script, stdin_bytes)
    amb = run(BASH, script, stdin_bytes)
    cloc = run(BASH, script, stdin_bytes, {'LC_ALL': 'C', 'LANG': 'C'})
    oracle_out = amb if oracle == 'utf8' else cloc
    verdict = 'MATCH' if psh == oracle_out else 'DIVERGE'
    print(f"[{verdict:7}] {name}   (oracle = bash {oracle})")
    print(f"           psh     : {psh!r}")
    print(f"           bash-utf8: {amb!r}")
    print(f"           bash-C   : {cloc!r}")
    if note:
        print(f"           note: {note}")
    print()
    return verdict


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    F = os.path.join(d, 'f.txt')
    with open(F, 'wb') as fh:
        fh.write(b'F1\nF2\n')
    # A file whose FIRST bytes split a malformed sequence, for the reverse cell.
    G = os.path.join(d, 'g.txt')
    with open(G, 'wb') as fh:
        fh.write(b'\xc3AGGG\nG2\n')

    print("=" * 72)
    print("R-MALFORMED  x  each surface  (deterministic; oracle = bash C per")
    print("DECISION 1, the hybrid malformed model)")
    print("=" * 72)

    cell("R-MALFORMED x S-SAMEFD (must-hold: surplus carries)", 'C',
         "read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"",
         b"\xc3A\n",
         "I1 same-fd persistence — the designed behavior.")

    cell("R-MALFORMED x S-TEMPFRAME forward (I1 (c'), pinned)", 'C',
         f"read -N 1 a; read b < {F}; read -N 1 c; "
         "printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
         b"\xc3A\nS2\n",
         "stdin surplus leaks INTO the temp-frame file read.")

    # NEW FACE: the same gap in the OTHER direction. Strand the surplus while
    # fd 0 IS the temp file, then read real stdin. If the leak is symmetric,
    # FILE bytes appear in a STDIN read.
    cell("R-MALFORMED x S-TEMPFRAME REVERSE (new face)", 'C',
         f"read -N 1 a < {G}; read b; "
         "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"STDIN1\nSTDIN2\n",
         "does the FILE's surplus leak OUT into the next STDIN read?")

    cell("R-MALFORMED x S-DUP (I1 (b), pinned)", 'C',
         "exec 3<&0; read -N 1 -u 0 a; read -N 1 -u 3 b; "
         "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\n",
         "lookahead byte stranded on fd0's cursor, invisible to fd3.")

    cell("R-MALFORMED x S-EXECREBIND (must-hold: cursor dropped)", 'C',
         f"read -N 1 a; exec 0<{F}; read b; "
         "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\nS2\n",
         "rebind() must drop the stale cursor — no surplus into the file read.")

    cell("R-MALFORMED x S-FORK (must-hold: child registry fresh)", 'C',
         "read -N 1 a; ( read -N 1 b; printf 'child=<%s>\\n' \"$b\" ); "
         "printf 'a=<%s>\\n' \"$a\"",
         b"\xc3ABC\n",
         "child must inherit no userspace buffer (only the kernel offset).")

    cell("R-MALFORMED x S-EXTERNAL (I1 (d), documented)", 'C',
         "read -N 1 a; cat", b"\xc3A\nZ\n",
         "stranded lookahead byte is invisible to an external child.")

    print("=" * 72)
    print("CONTROLS — the same surfaces with NO stranding (must be parity)")
    print("=" * 72)

    cell("CTL temp-frame, no surplus", 'utf8',
         f"read a; read b < {F}; read c; printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"",
         b"S1\nS2\nS3\n")

    cell("CTL dup alias, no surplus", 'utf8',
         "exec 3<&0; read -u 0 a; read -u 3 b; read -u 0 c; "
         "printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"",
         b"one\ntwo\nthree\n")

    cell("CTL temp-frame REVERSE, no surplus", 'utf8',
         f"read a < {F}; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"STDIN1\nSTDIN2\n")
