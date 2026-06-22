"""Formatter (`psh --format`) round-trip and shape tests.

Covers the control-structure and redirect formatting defects fixed in
v0.505.0: control-structure headers kept their condition on a separate line
with an un-joined ``then``/``do``; nested compound keywords (``else``/``fi``/
``done``) collapsed to column 0; and heredoc bodies, quoted heredoc
delimiters, quoted file targets, and here-string quotes were dropped —
producing lossy, non-re-parseable output.

The load-bearing invariant is **behavior preservation**: formatting a script
must not change what it does. These run psh in a subprocess (the real
``--format`` path, which is heredoc-aware), so they are xdist-safe.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import FormatterVisitor

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _fmt(src):
    """In-process format (fine for inputs without heredocs)."""
    return FormatterVisitor().visit(parse(tokenize(src)))


def _psh(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "psh", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30, input=stdin,
    )


def _format_via_psh(src):
    r = _psh("--format", "-c", src)
    assert r.returncode == 0, f"--format failed: {r.stderr}"
    return r.stdout


def _run(src):
    r = _psh("-c", src)
    return (r.returncode, r.stdout, r.stderr)


# ---------------------------------------------------------------------------
# Header shape — condition/header and then/do share one line
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src,first_line", [
    ("if true; then echo y; fi", "if true; then"),
    ("if a; then x; elif b; then y; fi", "if a; then"),
    ("while true; do echo y; done", "while true; do"),
    ("until false; do echo y; done", "until false; do"),
    ("for i in 1 2 3; do echo $i; done", "for i in 1 2 3; do"),
    ("for ((i=0; i<3; i++)); do echo $i; done", "for ((i=0; i<3; i++)); do"),
])
def test_header_keeps_condition_and_keyword_on_one_line(src, first_line):
    assert _fmt(src).splitlines()[0] == first_line


def test_elif_header_is_joined():
    lines = _fmt("if a; then x; elif b; then y; else z; fi").splitlines()
    assert "elif b; then" in lines
    assert "else" in lines


# ---------------------------------------------------------------------------
# Nested indentation — compound keywords stay at their block's indent
# ---------------------------------------------------------------------------

def test_nested_compound_keywords_are_indented():
    """`else`/`fi`/`done` inside a function must not collapse to column 0."""
    out = _fmt(
        "f() { if true; then echo a; else echo b; fi; "
        "while x; do echo c; done; }"
    )
    for line in out.splitlines():
        stripped = line.strip()
        if stripped in ("else", "fi", "done") or stripped.startswith("while "):
            assert line.startswith("  "), f"under-indented: {line!r}\n{out}"


def test_doubly_nested_indentation_increases():
    out = _fmt("for a in 1; do for b in 2; do echo $a$b; done; done")
    lines = out.splitlines()
    # outer `for` at 0, inner `for` at 2, body at 4
    assert lines[0] == "for a in 1; do"
    assert lines[1] == "  for b in 2; do"
    assert lines[2] == "    echo $a$b"


# ---------------------------------------------------------------------------
# Idempotence — formatting a formatted script is a fixed point
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src", [
    "if true; then echo y; fi",
    "if a; then x; elif b; then y; else z; fi",
    "while read x; do echo $x; done",
    "until false; do echo x; done",
    "for i in 1 2 3; do echo $i; done",
    "for ((i=0; i<3; i++)); do echo $i; done",
    "case $x in a) echo A;; b|c) echo BC;; esac",
    "f() { if true; then echo a; else echo b; fi; }",
    "{ echo a; echo b; } > out",
])
def test_format_is_idempotent(src):
    once = _format_via_psh(src)
    twice = _format_via_psh(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Behavior preservation — formatting must not change what a script does
# ---------------------------------------------------------------------------

BEHAVIOR_CASES = [
    "if [ 3 -lt 5 ]; then echo less; else echo more; fi",
    "for i in 1 2 3; do printf '%s.' $i; done; echo",
    "n=0; while [ $n -lt 3 ]; do echo $n; n=$((n+1)); done",
    "case hello in h*) echo match;; *) echo no;; esac",
    "f() { local x=$1; echo \"got $x\"; }; f world",
    # Heredoc: body must survive
    "cat <<EOF\nhello $USER\nEOF",
    # Quoted heredoc delimiter: no expansion
    "cat <<'EOF'\nliteral $x stays\nEOF",
    # Heredoc feeding a read loop (redirect on a compound command)
    "while read line; do echo \"<$line>\"; done <<EOF\none\ntwo\nEOF",
    # Brace group + heredoc
    "{ read a; read b; echo \"$a-$b\"; } <<EOF\nA\nB\nEOF",
    # Here string with spaces
    "cat <<< 'a b c'",
    # Quoted redirect target with a space
    "echo hi > 'out file'; cat 'out file'; rm 'out file'",
    # --- reappraisal #14 H8: previously-lossy --format constructs ---
    # Subscripted variable expansion must keep its braces (${arr[@]} not $arr[@])
    "arr=(a b c); echo ${arr[@]}",
    "arr=(a b c); echo ${arr[0]} ${arr[2]}",
    # Process substitution as a redirect target needs a space after the operator
    "echo hi > >(cat)",
    "read line < <(echo deep); echo \"$line\"",
    # |& must not downgrade to |
    "ls /nonexistent |& grep -c nonexistent",
    # Escaped $ inside double quotes must stay literal
    'echo "a\\$b"',
    # ANSI-C $'...' must be re-escaped (embedded quote / tab)
    "printf '%s.' $'a\\tb'",
    "printf '%s.' $'q\\'x'",
    # Named file descriptor prefix must survive
    "echo hi {out}>/dev/null; echo done",
    # for-loop list items with metacharacters must round-trip (not parse-error)
    'for x in "a;b" "c|d"; do echo "[$x]"; done',
    # glob list items must stay UNQUOTED so they still glob
    "for x in *.md; do echo item; done",
    # Heredoc inside a multi-stage pipeline
    "cat <<EOF | grep h\nhello\nhi\nEOF",
]


@pytest.mark.parametrize("src", BEHAVIOR_CASES)
def test_formatting_preserves_behavior(src):
    original = _run(src)
    formatted_src = _format_via_psh(src)
    after = _run(formatted_src)
    assert after == original, (
        f"behavior changed.\n--- src ---\n{src}\n--- formatted ---\n"
        f"{formatted_src}\n--- orig {original} --- after {after} ---"
    )


@pytest.mark.parametrize("src", BEHAVIOR_CASES)
def test_formatted_output_reparses(src):
    """The formatted script must be valid (re-parseable) shell."""
    formatted_src = _format_via_psh(src)
    assert _psh("--validate", "-c", formatted_src).returncode == 0


# ---------------------------------------------------------------------------
# Reappraisal #14 H8: explicit output-shape assertions for the fixes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src,expected_substr", [
    ("arr=(a b c); echo ${arr[@]}", "${arr[@]}"),
    ("arr=(a b c); echo ${arr[0]}", "${arr[0]}"),
    ("echo hi > >(cat)", "> >(cat)"),
    ("read x < <(echo y)", "< <(echo y)"),
    ("ls |& grep x", "|&"),
    ('echo "a\\$b"', '"a\\$b"'),
    ("echo hi {fd}>/dev/null", "{fd}>"),
])
def test_format_emits_expected_token(src, expected_substr):
    assert expected_substr in _fmt(src)


def test_format_does_not_double_escaped_dollar():
    # The old bug doubled the backslash: "a\$b" -> "a\\$b" (live expansion).
    assert "\\\\$" not in _fmt('echo "a\\$b"')


def test_format_for_glob_item_unquoted():
    # A glob item must NOT be quoted (else globbing is suppressed).
    assert 'for x in *.md' in _fmt("for x in *.md; do :; done")


def test_format_for_metachar_item_quoted():
    # An item with an operator metacharacter MUST be quoted (else parse error).
    out = _fmt('for x in "a;b"; do :; done')
    assert '"a;b"' in out
