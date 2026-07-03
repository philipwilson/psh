"""Lexer command-position fed by grammar context (reappraisal #16 follow-up g).

bash's parser feeds position back to its tokenizer; psh's command-position
machinery previously did not know it was (a) right after a function-definition
header `f()` where a compound-body keyword/operator is expected, or (b) right
after `for NAME` where `do` (without a preceding `in`/`;`) opens the body.

- g1: `f() [[ ... ]]` — after `)` the lexer emitted `[[` as a plain WORD, so the
  function body parser hit "Expected '{' for function body". A `)` now returns
  the lexer to command position (matching the normalizer), so `[[` is recognized
  as the test operator. The same gap broke `[[` at the start of a case body
  (`x) [[ ... ]]`).
- g2: `for x do ...` / `for x; do ...` — `do` closing a no-`in` loop header is
  now normalized to the DO keyword, and `pending_in` is cleared so a later `in`
  in the body is not mis-read as the loop keyword (the normalizer stays
  idempotent across its two passes: lexer pipeline + parser create_context).

All fixes live in the shared lexer, so BOTH parsers are covered. Verified
against bash 5.2.
"""

import subprocess
import sys

import pytest


def _run(cmd, parser=None):
    args = [sys.executable, '-m', 'psh']
    if parser:
        args += ['--parser', parser]
    args += ['-c', cmd]
    return subprocess.run(args, capture_output=True, text=True)


def _bash(cmd):
    return subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)


# g1: `[[ ]]` as a function body / case body (the odd-one-out among compound
# bodies — `(( ))`, `if`, `for`, `while`, `{ }`, `( )`, `case` already worked).
G1_CASES = [
    'f() [[ -n x ]]; f; echo rc=$?',
    'f() [[ -z x ]]; f; echo rc=$?',
    'f() [[ -n abc ]]; f && echo yes',
    'case x in x) [[ -n y ]] && echo hit;; esac',
    'case foo in f*) [[ -d / ]] && echo dir;; esac',
]

# g1 regressions: the other compound bodies must keep working after `f()`.
G1_REGRESSIONS = [
    'f() (( 1 )); f; echo rc=$?',
    'f() if true; then echo hi; fi; f',
    'f() for i in a b; do echo $i; done; f',
    'f() while false; do echo x; done; f; echo rc=$?',
    'f() { echo body; }; f',
    'f() case x in x) echo hit;; esac; f',
    'f() ( echo sub ); f',
]

# g2: POSIX no-`in` for/select loops (iterate the positional parameters).
G2_CASES = [
    'set -- 1 2; for x do echo $x; done',
    'set -- 1 2; for x; do echo $x; done',
    'set -- 1; for x do echo in; done',       # `in` in the body must stay a word
    'set -- 1; for x; do echo in; done',
    'set -- 1 2; for x do for y in a; do echo $x$y; done; done',
]

# g2 regressions: the `in` forms and body words must keep working.
G2_REGRESSIONS = [
    'for x in a b; do echo $x; done',
    'for x in a b; do echo in; done',
    'echo in',
    'echo hello in world',
    'for x in do re mi; do echo $x; done',    # `do`/`re`/`mi` are wordlist items
]


@pytest.mark.parametrize("cmd", G1_CASES + G1_REGRESSIONS + G2_CASES + G2_REGRESSIONS)
def test_command_position_matches_bash(cmd):
    bash = _bash(cmd)
    psh = _run(cmd)
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd


# The `for x in do re mi` regression exercises the combinator's known
# wordlist-parsing gap (documented educational-only in psh/parser/CLAUDE.md),
# unrelated to command position — so it is RD-only above.
@pytest.mark.parametrize("cmd", G2_CASES + G2_REGRESSIONS[:-1])
def test_g2_combinator_parser(cmd):
    """The g2 fix is in the shared lexer, so the combinator parser is covered."""
    bash = _bash(cmd)
    psh = _run(cmd, parser="combinator")
    assert psh.stdout == bash.stdout, cmd
    assert psh.returncode == bash.returncode, cmd
