"""Statement-parser compound-nesting depth guard (reappraisal #17 Tier 2).

Deeply nested compounds (~90 brace groups/ifs/subshells) used to overflow
the Python stack in the recursive-descent parser — "maximum recursion depth
exceeded", a raw traceback under strict-errors — while bash parses hundreds
of levels fine. The parser now tracks compound nesting in
``ParserContext.nesting_depth`` and ``CommandParser._parse_compound_component``
raises a clean ParseError past ``MAX_NESTING_DEPTH`` (1000) — the
statement-parser analogue of ``ArithParser.MAX_DEPTH``.

Depth-1000 cases run in a subprocess (they need the interpreter headroom a
psh process sets up at startup and must not burn the test runner's stack);
the guard MECHANISM is unit-tested in-process with a lowered limit.
"""

import subprocess
import sys

import pytest

from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.parsers import commands as commands_mod


def _psh_c(*args):
    return subprocess.run([sys.executable, '-m', 'psh', *args],
                          capture_output=True, text=True, timeout=120)


def _braces(n):
    return "{ " * n + "echo OK; " + "}; " * (n - 1) + "}"


def _ifs(n):
    return "if true; then " * n + "echo OK; " + "fi; " * (n - 1) + "fi"


# ---------------------------------------------------------------------------
# Guard mechanism (in-process, lowered limit)
# ---------------------------------------------------------------------------

def _parse(text):
    from psh.lexer import tokenize
    from psh.parser import Parser
    return Parser(tokenize(text), source_text=text).parse()


def test_guard_counts_only_compound_nesting(monkeypatch):
    """A simple command inside N compounds is at depth N, not N+1, and
    sequential compounds at one level don't accumulate."""
    monkeypatch.setattr(commands_mod, 'MAX_NESTING_DEPTH', 5)
    _parse(_braces(5))                       # exactly at the limit: fine
    _parse("{ echo a; }; " * 10)             # 10 sequential: depth stays 1
    with pytest.raises(ParseError, match="commands nested too deeply"):
        _parse(_braces(6))


def test_guard_covers_mixed_compound_kinds(monkeypatch):
    monkeypatch.setattr(commands_mod, 'MAX_NESTING_DEPTH', 4)
    _parse("if true; then { ( while true; do break; done ) }; fi")  # depth 4
    with pytest.raises(ParseError, match="commands nested too deeply"):
        _parse("{ if true; then { ( while true; do break; done ) }; fi; }")


def test_flat_chains_do_not_accumulate_depth(monkeypatch):
    """&&/||/pipe chains parse iteratively — no nesting depth (rdparser
    round-2 nuance: flat chains of hundreds are fine by construction)."""
    monkeypatch.setattr(commands_mod, 'MAX_NESTING_DEPTH', 3)
    _parse(" && ".join(["true"] * 50))
    _parse(" | ".join(["cat"] * 50))


# ---------------------------------------------------------------------------
# Real threshold (subprocess)
# ---------------------------------------------------------------------------

def test_1000_deep_braces_parse_and_execute():
    r = _psh_c('-c', _braces(1000))
    assert r.stdout == 'OK\n'
    assert r.returncode == 0


def test_1001_deep_braces_clean_parse_error():
    r = _psh_c('-c', _braces(1001))
    assert r.returncode == 2  # syntax-error status, like any ParseError
    assert 'commands nested too deeply (maximum depth 1000)' in r.stderr
    assert 'Traceback' not in r.stderr
    assert 'RecursionError' not in r.stderr


def test_1001_deep_ifs_clean_parse_error():
    r = _psh_c('-c', _ifs(1001))
    assert r.returncode == 2
    assert 'commands nested too deeply' in r.stderr
    assert 'Traceback' not in r.stderr


def test_deep_nesting_format_mode():
    """--format on a deeply nested script must survive too (the raised
    interpreter limit covers the formatter's own recursion)."""
    r = _psh_c('--format', '-c', _braces(500))
    assert r.returncode == 0
    assert 'Traceback' not in r.stderr
    assert r.stdout.count('{') == 500


def test_over_deep_validate_mode_reports_cleanly():
    r = _psh_c('--validate', '-c', _braces(1001))
    assert r.returncode == 2
    assert 'commands nested too deeply' in r.stderr
    assert 'Traceback' not in r.stderr
