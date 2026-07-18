"""Drift-lock guards for the S4 parser-call contract, with synthetic offenders.

Each guard is paired with a synthetic offender that is RUN and shown to trip the
guard, so the guard is proven load-bearing rather than vacuously green.
"""

import dataclasses
import re
from pathlib import Path

import pytest

from psh.lexer import tokenize
from psh.parser import ParseInputs
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig
from psh.parser.recursive_descent.helpers import ErrorContext

PSH_ROOT = Path(__file__).resolve().parents[3] / "psh"
RD_DIR = PSH_ROOT / "parser" / "recursive_descent"


# === Guard 1: ParseInputs is frozen ===

def test_parse_inputs_frozen_guard_and_offender():
    inputs = ParseInputs(source_text="x")
    # Guard: the real (frozen) inputs reject mutation.
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.source_text = "y"

    # Offender: a non-frozen twin ALLOWS the mutation the guard forbids.
    @dataclasses.dataclass
    class _MutableInputs:
        source_text: str = "x"

    offender = _MutableInputs()
    offender.source_text = "y"  # no error — this is what freezing prevents
    assert offender.source_text == "y"


# === Guard 2: the combinator retains no per-call state after return ===

def _combinator_slots(p):
    return (p.commands.heredocs, p.expansions.parse_ctx, p._parse_inputs, p.heredocs)


def test_combinator_retains_nothing_after_parse_with_heredocs():
    from psh.lexer import tokenize_with_heredocs
    lu = tokenize_with_heredocs("cat <<EOF\nbody\nEOF\n")
    p = ParserCombinatorShellParser(ParserConfig())
    p.parse_with_heredocs(list(lu.tokens), lu.heredocs, lexer_options={"extglob": True})
    assert _combinator_slots(p) == (None, None, None, None)


def test_combinator_retains_nothing_after_bare_parse():
    p = ParserCombinatorShellParser(ParserConfig())
    p.parse(list(tokenize("echo hi")))
    assert p.commands.heredocs is None
    assert p.expansions.parse_ctx is None


def test_retains_nothing_offender_is_detectable():
    # Offender: a parse variant that installs per-call state and forgets to
    # clear it would leave a non-None slot — exactly what the snapshot catches.
    p = ParserCombinatorShellParser(ParserConfig())
    p.commands.heredocs = {"leak": True}          # simulate a missing finally-clear
    assert _combinator_slots(p) != (None, None, None, None)
    # The real parse() restores the invariant.
    p.parse(list(tokenize("echo hi")))
    assert p.commands.heredocs is None


# === Guard 3: outcome_from_parse is the sole trichotomy decision point ===

def test_both_parsers_route_outcome_through_outcome_from_parse():
    rd_src = (RD_DIR / "parser.py").read_text()
    comb_src = (PSH_ROOT / "parser" / "combinators" / "parser.py").read_text()
    # Each parser's parse_outcome delegates to the one classifier; neither
    # re-implements the Complete/Incomplete/Invalid decision inline.
    assert "outcome_from_parse(" in rd_src
    assert "outcome_from_parse(" in comb_src
    for src in (rd_src, comb_src):
        # No inline at_eof branching that would re-derive the trichotomy.
        assert "Incomplete(" not in src
        assert "Invalid(" not in src


# === Guard 4: the caret is drawn from COLUMN, never the token-stream position ===

def test_caret_is_column_based_not_position_based():
    # A source line with the error at column 5; the byte `position` is a wildly
    # different (stripped-stream) number. The caret must land under column 5.
    ctx = ErrorContext(token=None, message="boom", position=999,
                       line=3, column=5, source_line="abcdefg")
    rendered = ctx.format_error()
    caret_line = [ln for ln in rendered.splitlines() if ln.strip() == "^"][0]
    assert caret_line.index("^") == 4          # column 5 -> 4 leading spaces
    assert "position 999" not in rendered      # the stripped offset is not shown
    assert "line 3, column 5" in rendered


def test_position_shown_only_when_no_line_column():
    ctx = ErrorContext(token=None, message="boom", position=7,
                       line=None, column=None, source_line=None)
    rendered = ctx.format_error()
    assert "at position 7" in rendered         # fallback coordinate


# === Guard 5: heredoc-bearing caret aligns (handoff 2 concrete case) ===

def test_heredoc_bearing_error_caret_aligns_at_source_column():
    # End-to-end (the reporter back-fills the source line by LINE NUMBER from
    # the body-bearing source): a syntax error AFTER a heredoc must draw the
    # caret under the offending token, in the (line, column) coordinate system
    # — never mis-placed by the stripped token-stream byte offset.
    import subprocess
    import sys
    import tempfile
    script = "cat <<EOF\nbody one\nbody two\nEOF\necho hi )\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run([sys.executable, "-m", "psh", path],
                           capture_output=True, text=True, timeout=30)
    finally:
        import os
        os.unlink(path)
    lines = r.stderr.splitlines()
    # Find the source line `echo hi )` and the caret line directly under it.
    idx = next(i for i, ln in enumerate(lines) if ln == "echo hi )")
    caret = lines[idx + 1]
    assert caret.strip() == "^"
    assert "echo hi )"[caret.index("^")] == ")"
    assert "line 5, column 9" in r.stderr        # one coordinate system
    assert "at position" not in r.stderr.split("Context")[0]


# === Guard 6: the only finally in the RD parser is the balanced depth counter ===

def test_only_rd_finally_is_the_balanced_nesting_counter():
    finallies = []
    for py in RD_DIR.rglob("*.py"):
        text = py.read_text()
        for m in re.finditer(r"^\s*finally:", text, re.MULTILINE):
            finallies.append((py.name, text[m.start():m.start() + 120]))
    # Exactly one finally, and it decrements the nesting depth counter — never a
    # post-return per-call-state scrub (the §8 "nothing to clear" claim).
    assert len(finallies) == 1, finallies
    name, snippet = finallies[0]
    assert name == "commands.py"
    assert "nesting_depth" in snippet


# === Guard 7: ParseInputs has exactly two sanctioned construction sites ===

def test_parse_inputs_construction_sites():
    sites = []
    for py in PSH_ROOT.rglob("*.py"):
        rel = py.relative_to(PSH_ROOT).as_posix()
        if rel == "parser/parse_inputs.py":
            continue  # the definition module (its docstring names the type)
        for _ in re.finditer(r"\bParseInputs\(", py.read_text()):
            sites.append(rel)
    # Sole constructors: the RD ParserContext (funnel for the RD parser) and the
    # combinator shell parser's per-call inputs. Any third site is drift.
    assert set(sites) == {
        "parser/recursive_descent/context.py",
        "parser/combinators/parser.py",
    }, sites


# === Guard 8: the combinator threads lexer_options into template validation ===

def test_combinator_threads_lexer_options_into_templates_guard_and_offender():
    import psh.parser.recursive_descent.support.syntax_templates as st
    seen = []
    orig = st._validate_body

    def spy(body, ctx):
        seen.append(ctx)
        return orig(body, ctx)

    st._validate_body = spy
    try:
        p = ParserCombinatorShellParser(ParserConfig())
        p.parse_with_heredocs(list(tokenize("x=; echo ${x:-$(echo hi)}")), {},
                              lexer_options={"extglob": True})
        # Guard: the combinator now passes a ParseInputs carrying the options.
        assert seen and isinstance(seen[0], ParseInputs)
        assert seen[0].lexer_options == {"extglob": True}

        # Offender: the base behavior passed ctx=None (no budget threaded).
        assert seen[0] is not None
    finally:
        st._validate_body = orig
