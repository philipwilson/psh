"""INSTR08 — the TIMEOUT-route faces (legs A/B) under psh+CLOSE, s1 UNCHANGED.

Answers the matrix cell the recommendation turns on: if the surfaces are
closed but s1 is left alone, is the DATA-INTEGRITY defect gone (no byte
lost, no cross-source contamination) even though the s1 VALUE split remains?
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import BASH, PSH, REPO, discriminate, feed  # noqa: E402

discriminate()
CLOSESITE = os.path.join(REPO, 'tmp/w4b4/closesite')
_orig_env = harness.env


def env_close(extra=None):
    e = _orig_env(extra)
    e['PYTHONPATH'] = CLOSESITE + os.pathsep + e['PYTHONPATH']
    return e


def feed_close(argv, script, phases, marker):
    harness.env = env_close
    try:
        return feed(argv, script, phases, marker)
    finally:
        harness.env = _orig_env


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    M = os.path.join(d, 'marker')
    F = os.path.join(d, 'f.txt')
    open(F, 'wb').write(b'FILELINE\nF2\n')
    STRAND = f': > {M}; read -t 2 -N 2 v; '

    for name, script, phases in [
        ("LEG A (temp-frame)",
         STRAND + f"read x < {F}; printf 'v=%s|x=%s\\n' \"$v\" \"$x\" | od -c | head -2",
         [(0.05, b'\xc3')]),
        ("LEG B (dup)",
         STRAND + "exec 3<&0; read -t 2 -u 3 y; read -t 2 -N 1 w; "
         "printf 'v=%s|y=%s|w=%s\\n' \"$v\" \"$y\" \"$w\" | od -c | head -2",
         [(0.05, b'\xc3'), (3.0, b'\xa9Z\n')]),
    ]:
        psh, _ = feed(PSH, script, phases, M)
        pshc, _ = feed_close(PSH, script, phases, M)
        bash, _ = feed(BASH, script, phases, M)
        print(f"### {name}")
        print(f"    psh      : {psh!r}")
        print(f"    psh+CLOSE: {pshc!r}")
        print(f"    bash     : {bash!r}")
        print()
