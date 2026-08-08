"""INSTR06 — THE COUPLING, measured: does s1-toward-bash remove legs A/B?

The brief's design insight is that the s1 disposition and the contract width
are ONE decision. This instrument measures it instead of arguing it: each
cell runs THREE ways —

    psh            (as shipped)
    psh+s1         (the s1-toward-bash emulation, injected into the CHILD
                    via sitecustomize on PYTHONPATH — no production edit)
    bash           (ambient UTF-8 oracle; the timeout input is WELL-FORMED)

A cell where psh+s1 == bash means the s1 ruling ALONE closes it. A cell
where psh+s1 still diverges means the surface needs a hook regardless of s1
— which is the load-bearing distinction for the decision matrix.

VALIDITY CONTROL: the emulation must actually be active in the child, so
cell 0 is the s1 divergence itself. If psh+s1 does not converge THERE, the
injection failed and every other row is meaningless.

Run:  python tmp/w4b4/instr06_s1_effect.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, PSH, REPO, discriminate, feed  # noqa: E402
import harness  # noqa: E402

discriminate()
S1SITE = os.path.join(REPO, 'tmp/w4b4/s1site')
print(f"s1 emulation injected via: {S1SITE}/sitecustomize.py")
print()

_orig_env = harness.env


def env_s1(extra=None):
    e = _orig_env(extra)
    e['PYTHONPATH'] = S1SITE + os.pathsep + e['PYTHONPATH']
    return e


def feed_s1(argv, script, phases, marker, hang=20):
    harness.env = env_s1
    try:
        return feed(argv, script, phases, marker, hang=hang)
    finally:
        harness.env = _orig_env


def run3(name, script, phases, marker, note=""):
    psh, _ = feed(PSH, script, phases, marker)
    pshs1, _ = feed_s1(PSH, script, phases, marker)
    bash, _ = feed(BASH, script, phases, marker)
    v_base = 'MATCH' if psh == bash else 'DIVERGE'
    v_s1 = 'MATCH' if pshs1 == bash else 'DIVERGE'
    closed = (v_base == 'DIVERGE' and v_s1 == 'MATCH')
    print(f"### {name}")
    print(f"    psh    : {psh!r}   [{v_base}]")
    print(f"    psh+s1 : {pshs1!r}   [{v_s1}]")
    print(f"    bash   : {bash!r}")
    print(f"    -> s1 ALONE {'CLOSES' if closed else 'DOES NOT CLOSE'} this cell")
    if note:
        print(f"    note: {note}")
    print()
    return closed


def run3_plain(name, script, stdin_bytes, note=""):
    """Deterministic (no-timing) variant for the MALFORMED route."""
    def one(argv, e):
        return subprocess.run(argv + ['-c', script], input=stdin_bytes,
                              cwd=REPO, env=e, capture_output=True,
                              timeout=30).stdout
    psh = one(PSH, _orig_env())
    pshs1 = one(PSH, env_s1())
    bashc = one(BASH, _orig_env({'LC_ALL': 'C', 'LANG': 'C'}))
    v_base = 'MATCH' if psh == bashc else 'DIVERGE'
    v_s1 = 'MATCH' if pshs1 == bashc else 'DIVERGE'
    closed = (v_base == 'DIVERGE' and v_s1 == 'MATCH')
    print(f"### {name}   (oracle = bash C, malformed model)")
    print(f"    psh    : {psh!r}   [{v_base}]")
    print(f"    psh+s1 : {pshs1!r}   [{v_s1}]")
    print(f"    bash-C : {bashc!r}")
    print(f"    -> s1 ALONE {'CLOSES' if closed else 'DOES NOT CLOSE'} this cell")
    if note:
        print(f"    note: {note}")
    print()
    return closed


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    M = os.path.join(d, 'marker')
    F = os.path.join(d, 'f.txt')
    with open(F, 'wb') as fh:
        fh.write(b'FILELINE\nF2\n')
    G = os.path.join(d, 'g.txt')
    with open(G, 'wb') as fh:
        fh.write(b'\xc3AGGG\nG2\n')

    STRAND = f': > {M}; read -t 2 -N 2 v; '

    print("=" * 72)
    print("CELL 0 — VALIDITY CONTROL: is the emulation live in the child?")
    print("=" * 72)
    ok = run3("R-TIMEOUT x S-SAMEFD (the s1 divergence itself)",
              STRAND + "read -t 2 -N 1 w; "
              "printf 'v=<%s> w=<%s>\\n' \"$v\" \"$w\" | od -c | head -2",
              [(0.05, b'\xc3')], M,
              "psh+s1 MUST converge here or the injection failed.")
    if not ok:
        print("!! INJECTION NOT PROVEN — remaining rows are meaningless. STOP.")
        sys.exit(1)
    print("INJECTION PROVEN LIVE.\n")

    print("=" * 72)
    print("THE TIMEOUT ROUTE across the unhooked surfaces")
    print("=" * 72)
    run3("LEG A — R-TIMEOUT x S-TEMPFRAME forward",
         STRAND + f"read x < {F}; "
         "printf 'v=%s|x=%s\\n' \"$v\" \"$x\" | od -c | head -2",
         [(0.05, b'\xc3')], M)

    run3("LEG B — R-TIMEOUT x S-DUP",
         STRAND + "exec 3<&0; read -t 2 -u 3 y; read -t 2 -N 1 w; "
         "printf 'v=%s|y=%s|w=%s\\n' \"$v\" \"$y\" \"$w\" | od -c | head -2",
         [(0.05, b'\xc3'), (3.0, b'\xa9Z\n')], M)

    print("=" * 72)
    print("THE MALFORMED ROUTE across the SAME surfaces — the residual that")
    print("s1 cannot reach (no timeout is involved at all)")
    print("=" * 72)
    run3_plain("R-MALFORMED x S-TEMPFRAME forward (I1 (c'))",
               f"read -N 1 a; read b < {F}; read -N 1 c; "
               "printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
               b"\xc3A\nS2\n")

    run3_plain("R-MALFORMED x S-TEMPFRAME REVERSE (new face)",
               f"read -N 1 a < {G}; read b; "
               "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
               b"STDIN1\nSTDIN2\n")

    run3_plain("R-MALFORMED x S-DUP (I1 (b))",
               "exec 3<&0; read -N 1 -u 0 a; read -N 1 -u 3 b; "
               "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
               b"\xc3A\n")
