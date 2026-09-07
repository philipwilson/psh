"""Executable round-trip contract for psh's serializations (C033, C231).

The contract every code-PRINTING path owes: text produced from a parsed
program must re-parse to a program that BEHAVES the same. Structural or
string equality is not that contract — ``VariableExpansion.braced`` is
excluded from ``__eq__``, so an AST-equality round trip passes while the
re-parsed program reads a DIFFERENT variable::

    v=1 v1=A v2=B; f() { echo ${v}{1,2}; }
    eval "$(declare -f f)"; f     # must print `11 12`, not `A B`

That was the live defect (C033): brace expansion runs BEFORE parameter
expansion, so a bare ``$v{1,2}`` re-forms the names ``v1``/``v2`` while a
delimited ``${v}{1,2}`` stays ``${v}1``/``${v}2``. Dropping the source's
braces in ``declare -f`` / ``--format`` silently retargets the read.

This module is the psh-side CORPUS guard. Every row of
``tests/harness/roundtrip_corpus.py`` is executed three ways in each of
psh's three input modes:

* directly (the reference),
* after ``eval "$(declare -f fN)"`` — the serialization behind
  ``declare -f``/``typeset -f``/``type``/``export -f``,
* after being run through ``psh --format``,

and the two derived runs must reproduce the reference's stdout and exit
status row for row. The bash-side reference for the same corpus (bash's own
``declare -f`` output re-evaluated in bash) lives in
``tests/conformance/bash/test_executable_roundtrip_conformance.py``.
"""

import os
import tempfile

import pytest
from roundtrip_corpus import (
    CORPUS,
    FAMILY_FLOORS,
    ROW_IDS,
    direct_script,
    roundtrip_script,
    split_rows,
)
from shell_oracle import is_comparable, run_psh

MODES = ["-c", "file", "stdin"]


def _run(script: str, mode: str, cwd: str, args=()):
    """Run psh over ``script`` in one of the three input modes."""
    if mode == "-c":
        r = run_psh([*args, "-c", script, "psh", "posarg"], timeout=60, cwd=cwd)
    elif mode == "stdin":
        r = run_psh([*args, "-s", "posarg"], stdin_data=script,
                    stdin_mode="pipe", timeout=60, cwd=cwd)
    else:
        path = os.path.join(cwd, "corpus.sh")
        with open(path, "w") as fh:
            fh.write(script)
        r = run_psh([*args, path, "posarg"], timeout=60, cwd=cwd)
    assert is_comparable(r), r
    return r


@pytest.fixture(scope="module")
def passes():
    """{mode: (direct_rows, declare_f_rows, format_rows, stderr triple)}."""
    out = {}
    for mode in MODES:
        with tempfile.TemporaryDirectory() as d:
            direct = _run(direct_script(), mode, d)
        with tempfile.TemporaryDirectory() as d:
            rt = _run(roundtrip_script(), mode, d)
        with tempfile.TemporaryDirectory() as d:
            fmt = _run(direct_script(), mode, d, args=("--format",))
            assert fmt.returncode == 0, fmt.stderr
            formatted = _run(fmt.stdout, mode, d)
        out[mode] = (split_rows(direct.stdout), split_rows(rt.stdout),
                     split_rows(formatted.stdout),
                     (direct.stderr, rt.stderr, formatted.stderr))
    return out


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("row_id", ROW_IDS)
def test_declare_f_reeval_preserves_behavior(row_id, mode, passes):
    """``eval "$(declare -f f)"`` must not change what ``f`` does (C033)."""
    direct, rt, _, _ = passes[mode]
    assert rt[row_id] == direct[row_id], (
        f"[{row_id}/{mode}] declare -f round trip changed behavior:\n"
        f"  direct: {direct[row_id]!r}\n  re-eval: {rt[row_id]!r}")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("row_id", ROW_IDS)
def test_format_preserves_behavior(row_id, mode, passes):
    """``psh --format`` output must behave like its input (C033, C231)."""
    direct, _, fmt, _ = passes[mode]
    assert fmt[row_id] == direct[row_id], (
        f"[{row_id}/{mode}] --format changed behavior:\n"
        f"  direct: {direct[row_id]!r}\n  formatted: {fmt[row_id]!r}")


@pytest.mark.parametrize("mode", MODES)
def test_no_diagnostics_on_any_pass(mode, passes):
    """None of the three passes may write to stderr.

    A dropped ``psh: error: [Errno 1] Operation not permitted`` host flake
    identifies itself here instead of looking like a round-trip regression.
    """
    assert passes[mode][3] == ("", "", "")


@pytest.mark.parametrize("mode", MODES)
def test_every_corpus_row_ran(mode, passes):
    """The marker split saw every row in every pass (no silent truncation)."""
    direct, rt, fmt, _ = passes[mode]
    assert set(direct) == set(rt) == set(fmt) == set(ROW_IDS)
    assert len(ROW_IDS) == len(CORPUS) >= 90
    # Row-safe, not just block-safe: losing rows OUT of a family fails too.
    for prefix, floor in FAMILY_FLOORS.items():
        present = [r for r in ROW_IDS if r.startswith(prefix)]
        assert len(present) >= floor, (
            f"family {prefix!r} shrank to {len(present)} rows (floor {floor})")


# ---------------------------------------------------------------------------
# The serialization TEXT, at the site the harm was reported on. The corpus
# above pins behavior; these pin the bytes the user is shown, so a renderer
# that "behaves" by re-fusing cannot quietly reintroduce the loss.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,expected", [
    ("echo ${v}{1,2}", "echo ${v}{1,2}"),
    ("echo ${v}{a,b}", "echo ${v}{a,b}"),
    ("echo ${v}{1..3}", "echo ${v}{1..3}"),
    ("echo $v{1,2}", "echo $v{1,2}"),        # bare stays bare
    ("echo ${x}b", "echo ${x}b"),
    ("echo $xb", "echo $xb"),                # bare stays bare
    ("echo ${x}.txt", "echo ${x}.txt"),
    ("echo $x.txt", "echo $x.txt"),
    # Quoted adjacency: the renderer merges same-quote regions, so the quote
    # the source used as a delimiter is gone by the time the text is written
    # and the name must carry its own braces (base emitted `echo "$vx"`).
    ('echo "$v""x"', 'echo "${v}x"'),
    ('echo "a$v""x"', 'echo "a${v}x"'),
    ('echo $v"dq"', 'echo ${v}"dq"'),
    # …and only where a fusion is actually possible:
    ('echo "$v"" x"', 'echo "$v x"'),
    ('echo "$v"".txt"', 'echo "$v.txt"'),
    (r'echo "$v"{1,2}', r'echo "${v}"{1,2}'),   # the quote already stopped it
    (r'echo $v""{1,2}', r'echo ${v}""{1,2}'),   # so did the empty part
    (r'echo $v{1,2}', r'echo $v{1,2}'),         # bare-adjacent: still fuses
    # An EMPTY part prints nothing, so it separates nothing in the emitted
    # text — the spelling has to look PAST it, not at the syntactically next
    # part (base and round 2 emitted `echo "$vx"` for the first row).
    (r'echo "$v""""x"', r'echo "${v}x"'),
    (r'echo "$v""""""x"', r'echo "${v}x"'),
    (r'echo "a$v""""x"', r'echo "a${v}x"'),
    (r'echo "$v"$"""x"', r'echo "${v}x"'),
    (r'echo "$v"""" x"', r'echo "$v x"'),        # nothing to fuse with
    (r'echo "$v"""', r'echo "$v"'),              # nothing follows at all
])
def test_declare_f_text_keeps_the_source_spelling(body, expected):
    """``declare -f`` renders the braces the source wrote — and only those."""
    with tempfile.TemporaryDirectory() as d:
        r = run_psh(["-c", f"f() {{ {body}; }}\ndeclare -f f"], timeout=30, cwd=d)
    assert is_comparable(r), r
    assert expected in r.stdout, r.stdout


# The OTHER renderer. ``display_text`` drops quotes unconditionally, so an
# empty part never separated anything there either; these five shapes printed
# ``$vx`` — a different variable — in ``.args`` and ``--debug-ast`` while the
# formatter happened to survive them (their quote-char groups differ, so no
# run is merged). One authority, one answer: both renderers brace.
@pytest.mark.parametrize("source,expected", [
    ('echo "$v"' + "''" + '"x"', "${v}x"),
    ('echo "$v"$' + "''" + '"x"', "${v}x"),
    (r'echo "$v"""x', "${v}x"),
    (r'echo $v""x', "${v}x"),
    (r"echo $v''x", "${v}x"),
    (r'echo "$v""""x"', "${v}x"),
    # controls: no fusion possible, so no braces
    (r'echo "$v"""" x"', "$v x"),
    (r'echo "$v"".txt"', "$v.txt"),
])
def test_display_text_looks_past_empty_parts(source, expected):
    """The ``.args`` / ``--debug-ast`` flattening uses the same authority."""
    from psh.lexer import tokenize
    from psh.parser import parse
    command = parse(tokenize(source)).statements[0].pipelines[0].commands[0]
    assert command.args[1] == expected, command.args


@pytest.mark.parametrize("source,expected", [
    (r'echo $v""x', "${v}x"),
    (r'echo "$v""""x"', "${v}x"),
])
def test_debug_ast_shows_the_same_spelling(source, expected):
    """``--debug-ast`` is a real consumer of that flattening, not just .args."""
    with tempfile.TemporaryDirectory() as d:
        r = run_psh(["--debug-ast", "-c", source], timeout=30, cwd=d)
    assert is_comparable(r), r
    printed = r.stdout + r.stderr
    assert expected in printed, printed
    assert "$vx" not in printed.replace(expected, ""), printed
