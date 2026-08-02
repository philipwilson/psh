#!/usr/bin/env python3
"""Slot 3.1 model of bash 5.2 gmatch (string profile), C-faithful. v5.

v5 (Phase C, R7): adds the glibc star-JUMP (sm_loop.c L150-155/L313/
L324-329) — the star general loop's inner walk (_segment, = GMATCH with
&end) stops at the next wildcard star and COMMITS that position; a
simple-element segment between stars is placed at its LEFTMOST match and
earlier stars never retry; groups are jump-opaque (EXTMATCH passes NULL
ends). v4 lacked the jump (plain positional search) — exact on corpus1/2
(no star-literal-star shapes) but wrong on corpus3's jump surface.
Validated: 0 mismatches on corpus1+2+3 = 437,811 cells.

Mirrors bash-5.2 lib/glob/sm_loop.c (fetched raw from savannah, cached at
tmp/slot31/sm_loop_5.2.c) restricted to the corpus alphabet: literals, '?',
'*', extglob groups. No brackets, no escapes, no pathname/period policy, no
case folding. The CORPUS (bash 5.2.26 measured) is the oracle; this model
must reproduce it 100%.

Key mechanisms (sm_loop.c line refs):
  - main-loop extglob dispatch RETURNS extmatch's result (L89-100).
  - '*' case collapse loop (L175-235):
      '?(' branch (L183-198): extmatch at CURRENT n; on failure SKIP group.
      '?' wildcard consumes one char (L200-209).
      '*(' branch (L211-231): extmatch at every newn STRICTLY < se; on
      failure SKIP group.
      loop-bottom break at p==pe keeps c = the wildcard (L233-234).
  - trailing-wildcard success (L240-257): pattern exhausted after wildcards
    (incl. post-SKIP) => MATCH.
  - end-of-string negation special (L259-268): n==se and next is '!(' =>
    unconditional MATCH: the --p makes EXTMATCH's PATSCAN fail, so EXTMATCH
    degenerates to STRCOMPARE(pattern-text, "") == NOMATCH, and the '!' arm
    returns 0 on EXTMATCH failure. ('?' arm unreachable: collapse consumed it.)
  - general loop tries rest at n2 STRICTLY < se (L284-331; first-char check
    is a pure optimization).
  - EXTMATCH (L823-950): '*' zero-instance try; '*'/'+' one alt-span then
    rest OR group-again (progress-guarded); '?'/'@' trailing optimization
    (srest starts at se when group is pattern-final); '!' per-split
    complement AND rest, splits si..se.
"""
import sys

_PREFIXES = "?*+@!"


def _find_paren(p, i):
    """p[i] == '('; return index of matching ')' or None."""
    depth = 1
    j = i + 1
    while j < len(p):
        if p[j] == '(':
            depth += 1
        elif p[j] == ')':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return None


def _split_alts(inner):
    parts, cur, depth = [], [], 0
    for c in inner:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if c == '|' and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append(''.join(cur))
    return parts


def gmatch(s, si, p, pi, encl=False):
    """encl: matching text that lies INSIDE some extglob group of the full
    physical pattern (an alternative slice). bash's end-of-string negation
    special is decided by a NUL-driven PATSCAN over the FULL pattern text
    (sm_loop.c L262-268 + glob_patscan): from '!' with depth pre-set to 1 it
    can only reach depth 0 via an ENCLOSING ')' — so the special yields MATCH
    iff the '!' group is NOT enclosed (top-level), else NOMATCH (EXTMATCH
    succeeds vacuously on the garbage parse and the '!' arm inverts it)."""
    n, se = si, len(s)
    while pi < len(p):
        c = p[pi]
        pi += 1
        # main-loop extglob dispatch (returns)
        if c in _PREFIXES and pi < len(p) and p[pi] == '(':
            close = _find_paren(p, pi)
            if close is None:
                return p[pi - 1:] == s[n:]  # STRCOMPARE fallback
            return extmatch(c, s, n, p, pi, close, encl)
        if c == '?':
            if n >= se:
                return False
            n += 1
            continue
        if c == '*':
            # Star-entry loop: re-entered on a glibc star-JUMP commit
            # (sm_loop.c L150-155 + L313 + L324-329): the general loop's
            # inner GMATCH gets &end and RETURNS at the next wildcard star,
            # committing (pattern, subject) — the segment between stars is
            # placed at its LEFTMOST match, and earlier stars never retry.
            while True:
                # collapse loop
                while True:
                    if pi >= len(p):
                        return True  # trailing wildcard(s)
                    c2 = p[pi]
                    if c2 not in '?*':
                        break
                    pi += 1
                    if c2 == '?' and pi < len(p) and p[pi] == '(':
                        close = _find_paren(p, pi)
                        if close is None:
                            pi = len(p)  # PATSCAN failure: skip to pe
                        else:
                            if extmatch('?', s, n, p, pi, close, encl):
                                return True
                            pi = close + 1  # skip group
                    elif c2 == '?':
                        if n >= se:
                            return False
                        n += 1
                    elif c2 == '*' and pi < len(p) and p[pi] == '(':
                        close = _find_paren(p, pi)
                        if close is None:
                            pi = len(p)
                        else:
                            for n2 in range(n, se):  # STRICTLY < se
                                if extmatch('*', s, n2, p, pi, close, encl):
                                    return True
                            pi = close + 1  # skip group
                    if pi >= len(p):
                        return True  # p==pe break with c a wildcard (L256)
                # c2 = first non-wildcard char, pi points AT c2
                # end-of-string negation special (L262): only at THIS entry
                # position (jump-committed) — MATCH iff not enclosed
                if (n == se and c2 == '!' and pi + 1 < len(p)
                        and p[pi + 1] == '('):
                    close = _find_paren(p, pi + 1)
                    if close is not None:
                        return not encl
                # general loop with the segment-jump semantics
                jump = None
                for n2 in range(n, se):
                    verdict, jn, jpi = _segment(s, n2, p, pi, encl)
                    if verdict == 1:  # full match
                        return True
                    if verdict == 2:  # jump: commit at the next star
                        jump = (jn, jpi)
                        break
                    # verdict 0: this n2 fails; try the next
                if jump is None:
                    return False
                n, pi = jump
                pi += 1  # consume the committed star; re-enter star entry
            # (unreachable)
        # literal
        if n < se and s[n] == c:
            n += 1
            continue
        return False
    return n == se


def _segment(s, m, p, j, encl):
    """The inner GMATCH of a star's general loop (called with &end in C):
    walk pattern chars from *j* matching s at *m*. Returns (verdict, n, pi):
    verdict 1 = full match to both ends; 2 = reached a wildcard star —
    JUMP, with (n, pi) the committed subject position and the star's index;
    0 = mismatch (caller tries the next start position). A GROUP dispatches
    EXTMATCH with the full continuation and is FINAL for this start
    (extmatch passes NULL ends in C — no jump through groups)."""
    se = len(s)
    while j < len(p):
        c = p[j]
        if c in _PREFIXES and j + 1 < len(p) and p[j + 1] == '(':
            close = _find_paren(p, j + 1)
            if close is not None:
                return ((1 if extmatch(c, s, m, p, j + 1, close, encl)
                         else 0), m, j)
            # unbalanced: prefix char is a literal (mirror the main loop)
            if m < se and s[m] == c:
                m += 1
                j += 1
                continue
            return (0, m, j)
        if c == '*':
            return (2, m, j)  # JUMP: commit here
        if c == '?':
            if m >= se:
                return (0, m, j)
            m += 1
            j += 1
            continue
        if m < se and s[m] == c:
            m += 1
            j += 1
            continue
        return (0, m, j)
    return ((1 if m == se else 0), m, j)


def extmatch(op, s, si, p, open_idx, close, encl=False):
    """Group op at p[open_idx]=='(' ... p[close]==')' matched at s[si:],
    then the rest p[close+1:]. Returns bool. Alt-descent sets encl=True
    (the alt text lies inside this group); the rest keeps the caller's."""
    se = len(s)
    alts = _split_alts(p[open_idx + 1:close])
    rest_pi = close + 1
    trailing = rest_pi >= len(p)

    def alt_span(a, start, end):
        return gmatch(s[start:end], 0, a, 0, True)

    def rest_ok(pos):
        return gmatch(s, pos, p, rest_pi, encl)

    if op in '*+':
        if op == '*' and rest_ok(si):
            return True  # zero instances
        for a in alts:
            for srest in range(si, se + 1):
                if alt_span(a, si, srest):
                    if rest_ok(srest):
                        return True
                    if srest != si and extmatch(op, s, srest, p, open_idx,
                                                close, encl):
                        return True
        return False
    if op in '?@':
        if op == '?' and rest_ok(si):
            return True
        for a in alts:
            start = se if trailing else si
            for srest in range(start, se + 1):
                if alt_span(a, si, srest) and rest_ok(srest):
                    return True
        return False
    if op == '!':
        for srest in range(si, se + 1):
            if not any(alt_span(a, si, srest) for a in alts):
                if rest_ok(srest):
                    return True
        return False
    raise AssertionError(op)


def predict(subject, pattern):
    return gmatch(subject, 0, pattern, 0)


def main(tsv_path):
    rows = []
    with open(tsv_path) as f:
        next(f)
        for line in f:
            cid, subj, pat, b, mine = line.rstrip("\n").split("\t")
            rows.append((cid, subj, pat, b, mine))
    mismatch = []
    for cid, subj, pat, b, _ in rows:
        got = "1" if predict(subj, pat) else "0"
        if got != b:
            mismatch.append((cid, subj, pat, b, got))
    print(f"model vs bash: {len(rows)} cells, mismatches={len(mismatch)}")
    for m in mismatch[:40]:
        print("  ", m)
    return len(mismatch)


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) == 0 else 1)
