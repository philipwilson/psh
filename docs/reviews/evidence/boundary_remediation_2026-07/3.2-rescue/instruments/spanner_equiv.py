#!/usr/bin/env python3
"""Does the all-start PRE-FILTER change any span_at answer? (must be: no)

The filter claims `P*` matches text[p:] exactly  <=>  P matches text[p:k] for
some k. If that identity is wrong anywhere — zero-width matches, empty
patterns, brackets, nested groups, case folding — substitution silently
changes. Checked against the UNFILTERED computation directly, at every
position of every subject.
"""
import os
import sys

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"# discriminator OK: {psh.__file__}")


def span_at_unfiltered(root, text, pos, profile):
    """The pre-filter-free definition (what the engine did before)."""
    m = pe._Matcher(text, profile.for_pathname, profile.ic)
    ends = m._ends(root, 0, pos)
    return (max(ends) - pos) if ends else None


PATTERNS = [
    '', '*', '*b', 'a*b', '*a*b', 'ab', 'a', '?', '?b', '[ab]', '[ab]*',
    '*[!a]', 'a*b*c', '*a*a*b', '[a-c]x', r'\*', r'a\*', '*x', 'a*x',
    '+(a)', '*(a)', '?(a)', '@(a|b)', '!(a)', '*(ab)x', '@(a|)', '+([ab])',
    '!(a|b)c', '*(a|aa)c', '?(a)?(b)', '@(a|b)*', '+(a)b', '*(a)*(b)',
    '[[:space:]]', '+([[:space:]])', '*([[:space:]])', '@(x|)',
    'A', '*A*', '[A-Z]',
]
SUBJECTS = [
    '', 'a', 'b', 'x', 'ab', 'ba', 'aa', 'abc', 'aab', 'abab', 'aaa',
    'aabb', 'xyz', 'a b', '  ', ' a ', 'AB', 'aB', 'Ab', 'ax', 'xa',
    'aaab', 'abba', 'c', 'ac', 'bc', 'a' * 7, 'ab' * 4, 'x ' * 3,
]

cells = 0
bad = []
for pat in PATTERNS:
    root = pe.compile_pattern(pat)
    if pe._seq_bash_quirk(root):
        continue                       # filter is on the non-quirk path only
    cp = pe.CompiledPattern(root)
    for profile in (pe.STRING, pe.STRING_IC):
        for subj in SUBJECTS:
            spanner = cp.spanner(subj, profile)
            for pos in range(len(subj) + 1):
                cells += 1
                got = spanner(pos)
                want = span_at_unfiltered(root, subj, pos, profile)
                if got != want:
                    bad.append((pat, subj, pos, profile.ic, want, got))
                # span_at() must agree with spanner() too
                if cp.span_at(subj, pos, profile) != want:
                    bad.append((pat, subj, pos, profile.ic, want, 'span_at'))

print(f"cells: {cells}")
print(f"DISAGREEMENTS: {len(bad)}")
for b in bad[:20]:
    print(f"  pat={b[0]!r} subj={b[1]!r} pos={b[2]} ic={b[3]}: "
          f"unfiltered={b[4]!r} filtered={b[5]!r}")
sys.exit(1 if bad else 0)
