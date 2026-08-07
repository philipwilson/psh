#!/usr/bin/env python3
"""i10 — FRESH probes for LEDGER carry #21 (attached to slot 4B.2).

LEDGER.md:76 — "`read -N` mixed valid+malformed hybrid | ATTACHED to slot 4B.2:
the decoder-seam fix touches this code — 4B.2 must re-rule (close or re-carry)
with fresh probes; silent behavior change forbidden."

Carry text (boundary_campaign_close_2026-07.md:248): a `read -N` spanning a MIX
of VALID and MALFORMED multibyte bytes lands on a count boundary that matches
NEITHER the UTF-8 nor the C-locale bash oracle — a HYBRID model.

This probe re-derives that three-way comparison at the 4B.2 base so the slot can
close-or-re-carry against a MEASURED post-state, and so any behaviour change my
fixes cause is visible rather than silent. Re-run this file after the fix and
diff the two outputs — that diff IS the "no silent behaviour change" evidence.

Shell-neutral: the byte stream is written by THIS process to the shell's stdin;
values are compared as raw bytes through the external `od`, never `printf %q`.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BASH = '/opt/homebrew/bin/bash'

BASE_ENV = {
    'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    'HOME': os.environ.get('HOME', '/tmp'),
    'TERM': 'dumb',
}

SCRIPT = (r'''read -N {n} x; rc=$?; printf 'rc=%s bytes=' "$rc"; '''
          r'''printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; printf '\n' ''')

# label, payload — each mixes VALID multibyte with MALFORMED bytes
PAYLOADS = [
    ('valid_then_malformed', b'\xc3\xa9\xc3A\n'),      # é, then lone lead C3, then A
    ('malformed_then_valid', b'\xc3A\xc3\xa9\n'),      # lone lead C3, A, then é
    ('ascii_valid_bare_ff', b'a\xc3\xa9\xffb\n'),      # a, é, bare FF, b
    ('euro_then_lone_lead', b'\xe2\x82\xac\xe2Z\n'),   # €, then lone lead E2, then Z
    ('two_valid', b'\xc3\xa9\xe2\x82\xac\n'),          # CONTROL: all valid
    ('two_malformed', b'\xc3\xc3A\n'),                 # CONTROL: all malformed
]
COUNTS = [1, 2, 3, 4]

ARMS = [
    ('psh', [sys.executable, '-m', 'psh', '-c'], {}),
    ('bash-UTF8', [BASH, '-c'], {'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8'}),
    ('bash-C', [BASH, '-c'], {'LC_ALL': 'C', 'LANG': 'C'}),
]


def run(argv, extra_env, script, stdin_bytes):
    env = dict(BASE_ENV)
    env.update(extra_env)
    r = subprocess.run(argv + [script], cwd=ROOT, env=env, input=stdin_bytes,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=20)
    lines = [ln for ln in r.stdout.decode('utf-8', 'surrogateescape').splitlines()
             if ln.startswith('rc=')]
    return lines[-1] if lines else r.stdout.decode('utf-8', 'surrogateescape').strip()


def main() -> int:
    bash_ver = subprocess.run([BASH, '--version'], capture_output=True,
                              text=True).stdout.splitlines()[0]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'psh/'], cwd=ROOT,
                           capture_output=True, text=True).stdout
    # Resolve and ASSERT the module actually under test. `python -m` prepends
    # the child's CWD to sys.path where it OUTRANKS PYTHONPATH, so a harness
    # that sets only the search path can silently measure its own tree — this
    # slot hit exactly that in its pty probe, in the direction that makes a base
    # look already-fixed. Setting cwd is the fix; asserting it is the proof.
    resolved = subprocess.run(
        [sys.executable, '-c',
         'import psh.builtins.read_builtin as rb; print(rb.__file__)'],
        cwd=ROOT, env=dict(BASE_ENV), capture_output=True, text=True).stdout.strip()
    want = os.path.join(ROOT, 'psh', 'builtins', 'read_builtin.py')
    if os.path.realpath(resolved) != os.path.realpath(want):
        raise SystemExit(
            f"DISCRIMINATOR FAILED: child imports {resolved!r}, expected "
            f"{want!r}; refusing to report numbers for the wrong tree.")

    print("== DISCRIMINATOR ==")
    print(f"module under test: {resolved}")
    print(f"bash oracle: {BASH} -> {bash_ver}")
    print(f"HEAD:        {head}")
    print(f"psh/ dirty:  {len(dirty.splitlines())} lines")
    print("stimulus:    written by THIS process to the shell's stdin "
          "(shell-neutral)")
    print("observable:  raw bytes of the variable via external od")
    print()

    print(f"{'PAYLOAD':<22} {'-N':<3} {'psh':<22} {'bash-UTF8':<22} "
          f"{'bash-C':<22} VERDICT")
    print("-" * 120)
    tally = {'matches-UTF8': 0, 'matches-C': 0, 'matches-both': 0,
             'matches-NEITHER': 0}
    for label, payload in PAYLOADS:
        for n in COUNTS:
            script = SCRIPT.format(n=n)
            got = {}
            for name, argv, env in ARMS:
                got[name] = run(argv, env, script, payload)
            eq_u = got['psh'] == got['bash-UTF8']
            eq_c = got['psh'] == got['bash-C']
            if eq_u and eq_c:
                verdict = 'matches-both'
            elif eq_u:
                verdict = 'matches-UTF8'
            elif eq_c:
                verdict = 'matches-C'
            else:
                verdict = 'matches-NEITHER'
            tally[verdict] += 1
            print(f"{label:<22} {n:<3} {got['psh']:<22} "
                  f"{got['bash-UTF8']:<22} {got['bash-C']:<22} {verdict}")
        print()

    total = sum(tally.values())
    print("== MEASURED SPLIT (carry #21 re-derivation) ==")
    for k in ('matches-both', 'matches-UTF8', 'matches-C', 'matches-NEITHER'):
        print(f"  {k:<16} {tally[k]:>3} / {total}")
    print()
    print("  carry #21 asserts a HYBRID model: cells matching NEITHER oracle.")
    print(f"  cells matching NEITHER at this tip: {tally['matches-NEITHER']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
