"""Characterization pins for the unified `//` substitution scan (T8 item 1).

`_substitute_all_empty_aware` (regex), `_substitute_all_matcher` (extglob
non-negation) and `_substitute_all_negation` (extglob negation) were three
hand-rolled left-to-right scans differing only in their zero-width stepping
bound. They now share one `_substitute_scan(value, replacement, match_at,
negation=)` loop. These cases lock psh's exact output byte-for-byte so the
merge stays behaviour-preserving; the empty-match battery
(tmp/r19-ledgers/T8-probes/item1_empty_match.sh) verified 18/20 match bash and
2 are the pre-existing per-quantifier `?()` quirk documented in
parameter_expansion.py (bash suppresses the empty match for `?()` on an empty
subject; psh does not — left as-is, NOT this scan's concern).
"""

import pytest

# (command, expected stdout) — psh's exact behaviour.
CASES = [
    ('x=abc; echo "${x//x*/-}"', "abc\n"),
    ('x=; echo "[${x//x*/-}]"', "[]\n"),
    ('x=abc; echo "${x/#/pre}"', "preabc\n"),
    ('x=abc; echo "${x/%/post}"', "abcpost\n"),
    ('x=; echo "[${x/#/pre}]"', "[pre]\n"),
    ('x=; echo "[${x/%/post}]"', "[post]\n"),
    (r'x=abc; echo "${x//\*/-}"', "abc\n"),
    (r'x=; echo "[${x//\*/-}]"', "[]\n"),
    ('shopt -s extglob; x=abc; echo "${x//?()/-}"', "-a-b-c\n"),
    # pre-existing `?()`-on-empty quirk (bash: "[]"): psh emits the empty match
    ('shopt -s extglob; x=; echo "[${x//?()/-}]"', "[-]\n"),
    ('shopt -s extglob; x=abc; echo "${x//*(q)/-}"', "-a-b-c\n"),
    ('shopt -s extglob; x=; echo "[${x//*(q)/-}]"', "[-]\n"),
    ('shopt -s extglob; x=aqqb; echo "${x//*(q)/-}"', "-a--b\n"),
    ('shopt -s extglob; x=abc; echo "${x//!(x)/-}"', "-\n"),
    # the negation zero-width knob: empty subject -> no end-of-subject match
    ('shopt -s extglob; x=; echo "[${x//!(x)/-}]"', "[]\n"),
    ('shopt -s extglob; x=abc; echo "${x//!(b)/-}"', "-\n"),
    ('shopt -s extglob; x=a; echo "${x//!(z)/-}"', "-\n"),
    # pre-existing `?()`-on-empty quirk, first-match form
    ('shopt -s extglob; x=; echo "[${x/?()/-}]"', "[-]\n"),
    ('shopt -s extglob; x=; echo "[${x/!(x)/-}]"', "[]\n"),
    ('x=; echo "[${x/#/P}]"', "[P]\n"),
]


@pytest.mark.parametrize("cmd,expected", CASES)
def test_substitution_scan(captured_shell, cmd, expected):
    captured_shell.clear_output()
    rc = captured_shell.run_command(cmd)
    assert rc == 0
    assert captured_shell.get_stdout() == expected
