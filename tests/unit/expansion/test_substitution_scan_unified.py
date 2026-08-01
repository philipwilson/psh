"""Characterization pins for the substitution scan's empty-match behaviour.

Originally the T8 item-1 lock for the unified substitution scan (18/20 rows
bash-verified; 2 rows pinned psh's then-divergent `?()`-on-empty output).
Slot 3.1 replaced the scan with bash's measured pat_subst / match_upattern
consumer layer (see the parameter_expansion.py module docstring): the
`?()`-on-empty quirk CLOSED — bash's match_pattern_char gate makes a scan
position with an empty remainder eligible only for `*`-headed pattern text —
so every row here is now the live-bash-verified value (bash 5.2.26,
re-verified 2026-08-02; the two former divergence pins flipped to `[]`).
The bash-composition battery holds the corpus-level lock; these rows keep
the in-process captured_shell reading.
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
    # `?()`-head is gated off an empty subject (match_pattern_char: only
    # `*`-headed pattern text is eligible at an empty position) — bash-verified
    ('shopt -s extglob; x=; echo "[${x//?()/-}]"', "[]\n"),
    ('shopt -s extglob; x=abc; echo "${x//*(q)/-}"', "-a-b-c\n"),
    ('shopt -s extglob; x=; echo "[${x//*(q)/-}]"', "[-]\n"),
    ('shopt -s extglob; x=aqqb; echo "${x//*(q)/-}"', "-a--b\n"),
    ('shopt -s extglob; x=abc; echo "${x//!(x)/-}"', "-\n"),
    # `!(`-head gated off an empty subject (same match_pattern_char rule)
    ('shopt -s extglob; x=; echo "[${x//!(x)/-}]"', "[]\n"),
    ('shopt -s extglob; x=abc; echo "${x//!(b)/-}"', "-\n"),
    ('shopt -s extglob; x=a; echo "${x//!(z)/-}"', "-\n"),
    # `?()`-head gated off an empty subject, first-match form — bash-verified
    ('shopt -s extglob; x=; echo "[${x/?()/-}]"', "[]\n"),
    ('shopt -s extglob; x=; echo "[${x/!(x)/-}]"', "[]\n"),
    ('x=; echo "[${x/#/P}]"', "[P]\n"),
]


@pytest.mark.parametrize("cmd,expected", CASES)
def test_substitution_scan(captured_shell, cmd, expected):
    captured_shell.clear_output()
    rc = captured_shell.run_command(cmd)
    assert rc == 0
    assert captured_shell.get_stdout() == expected
