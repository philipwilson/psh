"""Conformance pins for the "ambiguous redirect" fix (reappraisal #7, bug L3).

bash rule: for a filename-target redirect (`<`, `>`, `>>`, `<>`, `>|`,
`&>`, `&>>`) whose target word is UNQUOTED and, after expansion +
word-splitting + globbing, yields zero words OR more than one word, bash
reports `<word>: ambiguous redirect` (exit 1) and opens NOTHING. A QUOTED
target suppresses splitting/globbing (`> "$v"` with v="a b" writes the
literal file `a b`); a glob matching exactly one file is fine; a glob
matching none is the literal pattern (nullglob off).

The MESSAGE prefix differs (`bash: line N:` vs `psh:`) — that's the
shell-name prefix, not behavior — so these assert the `<word>: ambiguous
redirect` body and the exit codes, not byte-identical stderr.

Driven through subprocesses so psh and bash are directly comparable and so
the external-command (forked child) path is exercised as a real process.
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

pytestmark = pytest.mark.serial  # spawns subprocesses

BASH = resolve_bash().path


def _psh(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True, timeout=30,
    )


def _bash(cmd):
    return subprocess.run(
        [BASH, "-c", cmd], capture_output=True, text=True, timeout=30,
    )


# (command, expected pre-expansion target word that names the error)
# Each of these expands/splits/globs to != 1 word and must be ambiguous.
_AMBIGUOUS_CASES = [
    # unset variable -> zero words
    ("echo hi > $undef", "$undef"),
    # empty variable -> zero words
    ("u=; echo hi > $u", "$u"),
    # multi-word value, unquoted -> two words
    ('v="a b"; echo hi > $v', "$v"),
    # append form
    ("echo hi >> $undef", "$undef"),
    # stderr redirect form
    ("echo hi 2> $undef", "$undef"),
    # read-write form
    ("echo hi <> $undef", "$undef"),
    # command substitution yielding two words
    ("echo hi > $(echo a b)", "$(echo a b)"),
    # external command (forked-child redirect path), zero words
    ("cat /etc/hostname > $undef", "$undef"),
    # external command, multi-word value
    ('v="a b"; cat /etc/hostname > $v', "$v"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd,word", _AMBIGUOUS_CASES)
def test_ambiguous_redirect_exit_and_message(cmd, word):
    p = _psh(cmd)
    b = _bash(cmd)
    # Exit code matches bash (1).
    assert p.returncode == b.returncode == 1, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    # bash names the same word in the same `<word>: ambiguous redirect` shape.
    expected = f"{word}: ambiguous redirect"
    assert expected in p.stderr, (
        f"psh stderr lacks `{expected}` for {cmd!r}: {p.stderr!r}")
    assert expected in b.stderr, (
        f"bash stderr lacks `{expected}` for {cmd!r}: {b.stderr!r}")
    # No doubled / nonsense strerror message (the pre-fix bug).
    assert "No such file or directory: No such file or directory" not in p.stderr
    assert "[Errno" not in p.stderr, p.stderr


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_glob_multi_match_is_ambiguous(tmp_path):
    """A glob target matching >= 2 files is ambiguous (exit 1, nothing opened)."""
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "b.txt").write_text("")
    cmd = "echo hi > *.txt"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    b = subprocess.run([BASH, "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == b.returncode == 1
    assert "*.txt: ambiguous redirect" in p.stderr, p.stderr


# --------------------------------------------------------------------------
# Non-ambiguous cases: must NOT error (regression guard for normal redirects)
# --------------------------------------------------------------------------

def test_quoted_multiword_target_writes_literal_file(tmp_path):
    """`> "$v"` with v="a b" writes the literal file `a b` (not ambiguous)."""
    cmd = 'v="a b"; echo hi > "$v"; cat "a b"'
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "hi\n"
    assert (tmp_path / "a b").read_text() == "hi\n"


def test_single_word_target_is_fine(tmp_path):
    cmd = 'v=onefile; echo hi > $v; cat onefile'
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "hi\n"


def test_glob_no_match_uses_literal_pattern(tmp_path):
    """A glob matching nothing (nullglob off) is the literal pattern -> 1 word."""
    cmd = "echo hi > out.nomatch; cat out.nomatch"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "hi\n"
    assert (tmp_path / "out.nomatch").exists()


def test_single_glob_match_is_fine(tmp_path):
    (tmp_path / "single.log").write_text("")
    cmd = "echo hi > single*.log; cat single.log"
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "hi\n"


def test_plain_redirects_unaffected(tmp_path):
    """Normal `>`, `>>`, `2>` to a literal name still work, builtin + external."""
    cmd = ("echo a > f1; echo b >> f1; printf 'x' > f2 2>err; "
           "printf 'hello\\n' | cat > f3; cat f1")
    p = subprocess.run([sys.executable, "-m", "psh", "-c", cmd],
                       cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    assert p.stdout == "a\nb\n"
    assert (tmp_path / "f3").read_text() == "hello\n"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
