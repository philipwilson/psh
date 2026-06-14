"""Conformance pins for bugs L1 and L2 (reappraisal #7): two places where psh
should report a syntax error (exit 2) where bash does.

L1 — unterminated quote at end of input.
    `echo 'abc`, `echo "abc`, `echo $'abc` are syntax errors in bash (exit 2,
    "unexpected EOF while looking for matching quote"). psh used to flush the
    EOF-truncated buffer, re-tokenize it, and let the lexer's
    ``UnclosedQuoteError`` (a ``SyntaxError``, not a ``ParseError``) escape to
    the generic defect handler — printing `unexpected error: ...` and exiting 1.
    Now it is routed to the same exit-2 syntax-error path as the already-correct
    unterminated `$((`/`$(`/`${` constructs (which the parser reports as
    ParseError). The message wording differs from bash (psh has its own style);
    these pin the EXIT CODE and that the message is NOT an "unexpected error".

L2 — empty subshell `()` / brace group `{ }`.
    Bash requires at least one command inside `(...)` and `{ ...; }`. `()`,
    `( )`, `{ }`, `{  }`, newline-only and comment-only groups are all syntax
    errors (exit 2). psh used to accept them (exit 0). Command substitution
    `$()` and arithmetic `(())`/`(( ))` are SEPARATE and unchanged.

All driven through subprocesses so psh and bash are directly comparable.
"""

import shutil
import subprocess
import sys

import pytest

BASH = shutil.which("bash")


def _psh(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True, timeout=30,
    )


def _bash(cmd):
    return subprocess.run(
        [BASH, "-c", cmd], capture_output=True, text=True, timeout=30,
    )


# --------------------------------------------------------------------------
# L1: unterminated quote -> syntax error, exit 2 (not "unexpected error")
# --------------------------------------------------------------------------

_UNTERMINATED_QUOTE = [
    "echo 'abc",       # single quote
    'echo "abc',       # double quote
    "echo $'abc",      # ANSI-C quote
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", _UNTERMINATED_QUOTE)
def test_unterminated_quote_is_syntax_error(cmd):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 2, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    assert p.stdout == "" == b.stdout, p.stdout
    # On the syntax-error path, not the internal-defect path.
    assert "unexpected error" not in p.stderr, p.stderr
    assert "syntax error" in p.stderr.lower(), p.stderr


# Regression guard: the OTHER unterminated constructs were already correct and
# must STAY exit 2 on the syntax-error path.
_UNTERMINATED_OTHER = [
    "echo $((1+",      # arithmetic
    "echo $(foo",      # command substitution
    "echo ${x",        # parameter expansion
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", _UNTERMINATED_OTHER)
def test_other_unterminated_constructs_unchanged(cmd):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 2, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    assert "unexpected error" not in p.stderr, p.stderr
    assert "syntax error" in p.stderr.lower(), p.stderr


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_quote_closed_across_lines_still_works():
    """A quote opened on one line and closed on the next is NOT an error."""
    cmd = "echo 'abc\ndef'"
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 0
    assert p.stdout == "abc\ndef\n" == b.stdout


# --------------------------------------------------------------------------
# L2: empty subshell / brace group -> syntax error, exit 2
# --------------------------------------------------------------------------

_EMPTY_GROUPS = [
    "()",
    "( )",
    "{ }",
    "{  }",
    "( ( ) )",     # nested empty
    "(\n)",        # newline only
    "{\n}",        # newline only
    "( # c\n)",    # comment only (comment is no command)
    "{ # c\n}",    # comment only
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", _EMPTY_GROUPS)
def test_empty_group_is_syntax_error(cmd):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 2, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    assert "syntax error" in p.stderr.lower(), p.stderr


# Regression guards: non-empty groups still parse and run.
@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd,out", [
    ("(echo hi)", "hi\n"),
    ("{ echo hi; }", "hi\n"),
    ("( (echo hi) )", "hi\n"),
    ("{ echo a; echo b; }", "a\nb\n"),
])
def test_nonempty_groups_unchanged(cmd, out):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 0, (
        f"{cmd!r}: psh={p.returncode} bash={b.returncode} err={p.stderr!r}")
    assert p.stdout == out == b.stdout, p.stdout


# Regression guards: command substitution and arithmetic are SEPARATE forms
# and must keep their own (different) behavior.
@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_empty_command_substitution_unchanged():
    """Empty `$()` is valid (expands to nothing), exit 0 — NOT a subshell."""
    p = _psh("echo $()")
    b = _bash("echo $()")
    assert p.returncode == b.returncode == 0
    assert p.stdout == "\n" == b.stdout


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", ["(())", "(( ))"])
def test_empty_arithmetic_unchanged(cmd):
    """Empty arithmetic `(())` is exit 1 in bash (value 0 is false), NOT the
    exit-2 empty-subshell syntax error."""
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 1, (
        f"{cmd!r}: psh={p.returncode} bash={b.returncode}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
