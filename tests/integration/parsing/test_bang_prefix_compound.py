"""`!` (pipeline negation) before a compound command (reappraisal #14 Tier 2).

`!` keeps the following token at command position, so a reserved word or the
`[[` test operator right after it is recognized: `! while ...; do ...; done`,
`! if ...; fi`, `! [[ -z x ]]`. Previously the lexer/normalizer reset command
position after `!`, so the next keyword lexed as a plain WORD and the parser
reported "Expected command" (or `[[: command not found`). The fix is in the
shared lexer command-position machinery, so BOTH parsers are covered. Verified
against bash 5.2.
"""

import pytest
from shell_oracle import is_comparable, run_bash, run_psh


def _run(cmd, parser=None):
    args = []
    if parser:
        args += ['--parser', parser]
    args += ['-c', cmd]
    r = run_psh(args)
    assert is_comparable(r), r
    return r


def _bash(cmd):
    r = run_bash(['-c', cmd])
    assert is_comparable(r), r
    return r


# (command, ...) — each negates a compound; output+rc must match bash.
CASES = [
    '! while false; do echo x; done; echo $?',
    '! until true; do echo x; done; echo $?',
    '! if true; then false; fi; echo $?',
    '! case x in x) true;; esac; echo $?',
    '! for i in 1 2; do false; done; echo $?',
    '! [[ -z x ]]; echo $?',
    '! [[ -n x ]]; echo $?',
    'if ! grep -q z <<<abc; then echo notfound; fi',
    'true && ! false; echo $?',
]


@pytest.mark.parametrize("cmd", CASES)
def test_bang_compound_matches_bash(cmd):
    bash = _bash(cmd)
    psh = _run(cmd)
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd


@pytest.mark.parametrize("cmd", CASES)
def test_bang_compound_combinator_parser(cmd):
    """The fix lives in the shared lexer, so the combinator parser is covered too."""
    bash = _bash(cmd)
    psh = _run(cmd, parser="combinator")
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd


# Regressions: forms that already worked must keep working.
@pytest.mark.parametrize("cmd", [
    '! { false; }; echo $?',
    '! ( false ); echo $?',
    '! echo a | grep z; echo $?',
    'while false; do echo x; done; echo $?',
    'echo ! while',          # `!`/`while` as ordinary args, not negation/keyword
])
def test_regressions_match_bash(cmd):
    bash = _bash(cmd)
    psh = _run(cmd)
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd


# Repeated `!`: bash accepts `! ! cmd`, each occurrence toggling the sense of
# the exit status. Previously psh consumed only one `!` and hit "Expected
# command" on the second. Verified against bash 5.2.
@pytest.mark.parametrize("cmd", [
    '! ! true; echo $?',
    '! ! false; echo $?',
    '! ! ! true; echo $?',
    '! ! ! false; echo $?',
    '! ! echo a | grep a; echo $?',
    '! ! [[ -n x ]]; echo $?',
])
def test_repeated_bang_matches_bash(cmd):
    bash = _bash(cmd)
    psh = _run(cmd)
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd
