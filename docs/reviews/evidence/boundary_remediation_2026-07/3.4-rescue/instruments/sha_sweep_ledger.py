#!/usr/bin/env python3
"""SLOT INSTRUMENT (not a shipped tool) — sweep a ledger's SHAs against git.

Lives with the slot instruments per R12: `tools/` is outside this slot's
scope and a new file there would move the lint surface mid-slot. Whether this
graduates to `tools/` campaign-wide is an integrator call at ceremony.

Every SHA in a durable record must be paste-from-instrument. This checks that
each one resolves to a real commit, so a typo cannot sit in the most
load-bearing row of the record (slot 3.4 B4).

EXCLUSION DESIGN — rewritten after a forcing probe (R13 asked whether the
exclusions could MASK a B4-class wrong SHA; they could, all three).

The first design excused whole LINES by context: "on a line that says
`originally read`", "on a line in this script's own output format". A planted
wrong SHA slipped through every one of them, because excusing a CONTEXT
excuses everything in it — including a second, unintended bad SHA on the same
line. Context is not evidence.

So there is now exactly ONE semantic exclusion and it is an explicit
ALLOWLIST: a known-wrong SHA must be named here, verbatim, with its reason.
Anything not on this list is reported no matter where it appears — prose,
quotation, or a pasted transcript of this script's own output. The remaining
exclusion is a pure tokenizer artifact (a run of hex digits inside a longer
decimal number is not a SHA at all).
"""
import pathlib
import re
import subprocess
import sys

BASE = '241a923c3f113fc55eb11b26e494b15a1e9fc17a'

# Known-wrong values, named verbatim with a reason. Nothing else is excused.
KNOWN_WRONG = {
    '9d840d117': 'B4: the mistyped round-2 tip, quoted in its own correction '
                 'and in the sweep transcript that reported it',
}


def sweep(path: pathlib.Path) -> int:
    known = set(subprocess.run(['git', 'log', '--format=%H', f'{BASE}~1..HEAD'],
                               capture_output=True, text=True).stdout.split())
    known.add(BASE)

    bad, noted, checked = [], 0, 0
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        for m in re.finditer(r'\b[0-9a-f]{7,40}\b', line):
            tok = m.group()
            before, after = line[:m.start()], line[m.end():]
            in_number = (before.rstrip().endswith(tuple('.0123456789'))
                         or after[:1].isdigit())
            if in_number and tok.isdigit():
                # A run of DECIMAL digits inside a longer number (a drift
                # figure like 0.10139416983523447). Narrowed to all-digit
                # tokens: a hex token carrying a-f in the same position is
                # still reported, so the exclusion cannot hide a planted SHA.
                continue
            checked += 1
            if any(k.startswith(tok) for k in known):
                continue
            if tok in KNOWN_WRONG:
                noted += 1
                continue
            bad.append((lineno, tok))

    print(f"  checked {checked} SHA-like tokens against git log")
    print(f"  {noted} allowlisted known-wrong occurrence(s)")
    for lineno, tok in bad:
        print(f"  BAD   {path}:{lineno}: {tok} does not resolve to a commit")
    print(f"  RESULT: {len(bad)} unresolvable")
    return 1 if bad else 0


if __name__ == '__main__':
    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else 'tmp/remediation-ledgers/3.4.md')
    sys.exit(sweep(target))
