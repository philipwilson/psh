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

import os
import subprocess
import sys
from pathlib import Path

import pytest

from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.parsers import commands as commands_mod

# Repo root (tests/unit/parser/<this file> -> up 3). Used so standalone
# subprocesses import THIS worktree's psh, not an editable-install elsewhere.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


# ---------------------------------------------------------------------------
# Standalone parser boundary: RecursionError -> ParseError (finding 6)
#
# The parser is a public API usable WITHOUT constructing Shell. Shell raises
# the interpreter recursion limit to 40k at construction, which is what lets
# the MAX_NESTING_DEPTH guard (1000) fire before Python's stack runs out. With
# no Shell — an embedding, or direct parser use — the default recursion limit
# (1000) trips a raw RecursionError at ~200 nested compounds, long before the
# guard. Parser safety must not depend on shell initialization: the parse
# boundary converts that RecursionError into a clean ParseError.
#
# These run a subprocess that imports ONLY the parser (never constructs Shell)
# under the interpreter's default recursion limit, so the conversion is
# exercised independent of whatever the in-process test runner set the global
# limit to.
# ---------------------------------------------------------------------------

_STANDALONE_CODE = r"""
import sys
sys.setrecursionlimit(1000)  # interpreter default; no Shell headroom
from psh.lexer import tokenize
from psh.parser import parse
from psh.parser.recursive_descent.helpers import ParseError
script = sys.stdin.read()
try:
    parse(tokenize(script))
    print('NO_ERROR')
except ParseError as e:
    sys.stdout.write('PARSE_ERROR\n')
    sys.stdout.write(str(e).splitlines()[0] + '\n')
except RecursionError:
    print('RECURSION_ERROR')
"""


def _standalone_parse(script):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(PROJECT_ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    return subprocess.run([sys.executable, '-c', _STANDALONE_CODE],
                          input=script, capture_output=True, text=True,
                          timeout=60, cwd=str(PROJECT_ROOT), env=env)


def test_standalone_deep_nesting_is_parse_error_not_recursion_error():
    r = _standalone_parse('{ ' * 250 + 'echo hi; ' + '}; ' * 249 + '}')
    assert r.returncode == 0, r.stderr
    assert 'RecursionError' not in r.stdout
    assert 'RecursionError' not in r.stderr and 'Traceback' not in r.stderr
    assert r.stdout.startswith('PARSE_ERROR'), r.stdout
    assert 'too deeply nested' in r.stdout


def test_standalone_deep_ifs_is_parse_error():
    r = _standalone_parse('if true; then ' * 250 + 'echo hi; ' + 'fi; ' * 249 + 'fi')
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith('PARSE_ERROR'), r.stdout
    assert 'RecursionError' not in r.stderr


def test_standalone_normal_input_unaffected():
    r = _standalone_parse('echo hi; echo bye')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'NO_ERROR'


# ---------------------------------------------------------------------------
# Function bodies count toward the guard (reappraisal #19 H12)
#
# A function body is a compound command, so it must accumulate nesting depth
# exactly like a bare brace group. Before v0.714 `FunctionParser.
# parse_compound_command` hand-rolled its own brace/control dispatch and never
# touched `nesting_depth`, so a chain of nested function DEFINITIONS bypassed
# the guard entirely: 1,200 nested function bodies parsed unboundedly where
# 1,200 nested brace groups already tripped MAX_NESTING_DEPTH. Function bodies
# now route through the same `CommandParser._parse_compound_component`
# chokepoint, so the guard fires for them too.
#
# `_nested_funcs(n)` is `f1() { f2() { ... echo OK ; } ... ; }` — n nested
# brace bodies, so parse depth n (mirrors `_braces(n)`).
# ---------------------------------------------------------------------------

def _nested_funcs(n):
    return "".join(f"f{k}() {{ " for k in range(1, n + 1)) + "echo OK" + " ; }" * n


def _calling_nested_funcs(n):
    """n nested definitions where each level calls the one it defines, so the
    innermost `echo OK` actually runs when the outermost function is invoked."""
    opens = "".join(f"f{k}() {{ " for k in range(1, n + 1))
    closes = " ; }" + "".join(f" ; f{k + 1} ; }}" for k in range(n - 1, 0, -1))
    return opens + "echo OK" + closes + " ; f1"


def test_guard_counts_function_bodies(monkeypatch):
    """A chain of N nested function definitions is at depth N (H12). On the
    pre-fix tree these bypassed the guard entirely, so this raises RED there."""
    monkeypatch.setattr(commands_mod, 'MAX_NESTING_DEPTH', 5)
    _parse(_nested_funcs(5))                  # exactly at the limit: fine
    _parse("f() { echo a; }; " * 10)          # 10 sequential defs: depth stays 1
    with pytest.raises(ParseError, match="commands nested too deeply"):
        _parse(_nested_funcs(6))


def test_guard_counts_keyword_form_function_bodies(monkeypatch):
    """The `function name { ... }` form routes through the same chokepoint."""
    monkeypatch.setattr(commands_mod, 'MAX_NESTING_DEPTH', 4)
    body = "function f4 { echo OK ; }"
    for name in ("f3", "f2", "f1"):
        body = f"function {name} {{ {body} ; }}"
    _parse(body)                              # depth 4: fine
    with pytest.raises(ParseError, match="commands nested too deeply"):
        _parse(f"function f0 {{ {body} ; }}")  # depth 5: trips


def test_64_deep_func_bodies_parse_and_execute():
    """Deep-but-legal nesting (64 function bodies) must still parse AND run."""
    r = _psh_c('-c', _calling_nested_funcs(64))
    assert r.returncode == 0, r.stderr
    assert r.stdout == 'OK\n'
    assert 'Traceback' not in r.stderr


def test_1200_deep_func_bodies_clean_parse_error():
    """~1,200 nested function bodies now raise the standard MAX_NESTING_DEPTH
    ParseError — NOT a RecursionError, NOT an unbounded parse (H12)."""
    r = _psh_c('-c', _nested_funcs(1200))
    assert r.returncode == 2  # syntax-error status, like any ParseError
    assert 'commands nested too deeply (maximum depth 1000)' in r.stderr
    assert 'Traceback' not in r.stderr
    assert 'RecursionError' not in r.stderr


def test_1000_deep_func_bodies_parse():
    """The boundary: exactly MAX_NESTING_DEPTH nested function bodies parse."""
    r = _psh_c('-c', _nested_funcs(1000))
    assert r.returncode == 0, r.stderr
    assert 'commands nested too deeply' not in r.stderr


def test_1001_deep_func_bodies_clean_parse_error():
    r = _psh_c('-c', _nested_funcs(1001))
    assert r.returncode == 2
    assert 'commands nested too deeply' in r.stderr
    assert 'Traceback' not in r.stderr
