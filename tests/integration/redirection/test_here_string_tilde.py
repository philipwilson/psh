"""Here-string (`<<<`) tilde expansion (reappraisal #14 Tier 2).

An UNQUOTED here-string tilde-expands like an assignment value: a `~`/`~user`
prefix at the start and after each `:` is expanded (`~:~` -> both), but a
mid-word `~` is not, and a quoted here-string (`<<<"~"`, `<<<'~'`) stays
literal. psh expanded variables/command-sub/arithmetic in here-strings but
skipped tilde entirely. Verified against bash 5.2.
"""

import pytest
from shell_oracle import is_comparable, run_bash, run_psh


def _out(cmd, runner):
    r = runner(['-c', cmd])
    assert is_comparable(r), r
    return (r.stdout, r.returncode)


@pytest.mark.parametrize("cmd", [
    'cat <<<~',
    'cat <<<~/foo',
    'cat <<<~root',
    'cat <<<~:~',                  # both tildes (value-context rule)
    'cat <<<a:~',                  # tilde after colon
    'cat <<<~:b',
    'cat <<<x~y',                  # mid-word tilde: NOT expanded
    'HOME=/zzz; cat <<<~',         # honors HOME
    'cat <<<"~"',                  # double-quoted: literal
    "cat <<<'~'",                  # single-quoted: literal
    'd=foo; cat <<<~/$d',          # tilde then variable
    'cat <<<~nonexistentuser99',   # unknown user: left as-is
    'x=hi; cat <<<$x',             # variable still works (regression)
    'cat <<<$(echo sub)',          # command sub still works (regression)
])
def test_here_string_tilde_matches_bash(cmd):
    psh = _out(cmd, run_psh)
    bash = _out(cmd, run_bash)
    assert psh == bash, cmd
