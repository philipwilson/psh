"""One shared lex→alias→parse pipeline for the scripting layer (reappraisal #19 H11).

`scripting/lex_parse.py` gives the completeness trial, the execution parser, and
the analysis parser (`--validate`/`--format`/...) one heredoc-aware
lex→alias→parse seam. The analysis copy had drifted — it ignored `--parser`,
dropped `lexer_options`, and skipped alias expansion. These pins lock the four
behavior deltas that fix brings, plus the strict-errors boundary in analysis
mode. See `tmp/r19-ledgers/T6.md` for the pre-registration and red-on-base
records.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from psh.scripting.visitor_modes import _parse_for_analysis, handle_visitor_mode_for_content
from psh.shell import Shell

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}

# A construct the recursive-descent parser accepts but the (educational)
# combinator parser rejects: `select` without an `in` clause.
SELECT_NO_IN = 'select x\ndo echo $x\ndone\n'


def _run(argv, script, tmp_path, name):
    path = tmp_path / name
    path.write_text(script)
    # cwd=REPO_ROOT so `-m psh` imports THIS tree (psh is editable-installed
    # against the main checkout; cwd wins on sys.path).
    return subprocess.run(
        [sys.executable, '-m', 'psh', *argv, str(path)],
        capture_output=True, text=True, timeout=10, env=ENV, cwd=str(REPO_ROOT))


# --- Delta A: analysis now honours --parser (was: always recursive descent) ---

def test_delta_a_validate_uses_selected_parser(tmp_path):
    # RD accepts select-without-in → rc 0; the combinator rejects it → rc 2.
    # Before the fix BOTH gave rc 0 (analysis silently used RD). This proves
    # --validate now dispatches to the selected parser.
    rd = _run(['--parser', 'rd', '--validate'], SELECT_NO_IN, tmp_path, 's1.sh')
    pc = _run(['--parser', 'pc', '--validate'], SELECT_NO_IN, tmp_path, 's2.sh')
    assert rd.returncode == 0, rd.stderr
    assert pc.returncode == 2, (pc.returncode, pc.stdout, pc.stderr)
    assert 'psh:' in pc.stderr


def test_delta_a_format_uses_selected_parser(tmp_path):
    rd = _run(['--parser', 'rd', '--format'], SELECT_NO_IN, tmp_path, 'f1.sh')
    pc = _run(['--parser', 'pc', '--format'], SELECT_NO_IN, tmp_path, 'f2.sh')
    assert rd.returncode == 0, rd.stderr
    assert pc.returncode == 2, (pc.returncode, pc.stdout, pc.stderr)


# --- Delta B: analysis threads lexer_options into nested-substitution re-lex ---

def test_delta_b_lexer_options_reach_nested_substitution():
    # A nested command substitution whose body uses an extglob pattern only
    # parses when the shell's option set (extglob) reaches the parser's
    # nested re-lex. Before the fix analysis dropped lexer_options → this
    # raised even with extglob on (red-on-base, recorded in the ledger).
    src = 'x=$(echo @(a|b))'

    on = Shell(norc=True)
    on.state.options['extglob'] = True
    ast = _parse_for_analysis(on, src)   # must not raise
    assert ast is not None

    # Both branches of the symmetric option: with extglob OFF the same input
    # is a genuine syntax error.
    from psh.parser import ParseError
    off = Shell(norc=True)
    with pytest.raises(ParseError):
        _parse_for_analysis(off, src)


# --- Delta C: analysis consults the alias table at the seam (like execution) ---

def test_delta_c_analysis_expands_aliases():
    import dataclasses

    from psh.ast_nodes import SimpleCommand

    shell = Shell(norc=True)
    shell.alias_manager.define_alias('ll', 'ls -l')
    ast = _parse_for_analysis(shell, 'll')

    def first_simple_command(node):
        if isinstance(node, SimpleCommand):
            return node
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                r = first_simple_command(getattr(node, f.name, None))
                if r:
                    return r
        if isinstance(node, (list, tuple)):
            for item in node:
                r = first_simple_command(item)
                if r:
                    return r
        return None

    cmd = first_simple_command(ast)
    assert cmd is not None
    # 'll' expanded to 'ls -l' — before the fix this stayed ['ll'].
    assert cmd.args == ['ls', '-l'], cmd.args


# --- Delta D: analysis syntax errors now carry the rich source-line caret ---

def test_delta_d_analysis_error_has_source_caret():
    r = subprocess.run(
        [sys.executable, '-m', 'psh', '--validate', '-c', 'if'],
        capture_output=True, text=True, timeout=10, env=ENV, cwd=str(REPO_ROOT))
    assert r.returncode == 2
    assert 'Traceback' not in r.stderr
    # The rich caret form the execution path prints (source line + ^ marker),
    # not the bare one-line reason analysis used to show. `if` at EOF marks the
    # source line `if` with a `^` caret.
    assert '^' in r.stderr
    assert 'if' in r.stderr


# --- Item 3: strict-errors boundary in analysis modes ---

def test_analysis_internal_defect_raises_under_strict(monkeypatch):
    # A visitor bug (an unexpected TypeError) under --lint is an INTERNAL
    # DEFECT: with strict-errors ON it must FAIL LOUDLY (re-raise), not be
    # swallowed as a bland exit-1. Before the fix the `except (ValueError,
    # TypeError)` clause masked it (red-on-base).
    def boom(self, ast):
        raise TypeError("injected visitor bug")
    monkeypatch.setattr('psh.visitor.LinterVisitor.visit', boom)

    shell = Shell(norc=True)
    shell.lint_only = True
    shell.state.options['strict-errors'] = True
    with pytest.raises(TypeError):
        handle_visitor_mode_for_content(shell, 'echo hi', '-c')


def test_analysis_internal_defect_reports_without_strict(monkeypatch, capsys):
    def boom(self, ast):
        raise TypeError("injected visitor bug")
    monkeypatch.setattr('psh.visitor.LinterVisitor.visit', boom)

    shell = Shell(norc=True)
    shell.lint_only = True
    shell.state.options['strict-errors'] = False
    rc = handle_visitor_mode_for_content(shell, 'echo hi', '-c')
    assert rc == 1
    err = capsys.readouterr().err
    assert 'unexpected error' in err
    # NOT the old bland swallow message.
    assert 'Error parsing command' not in err


def test_analysis_syntax_error_still_clean_under_strict(monkeypatch):
    # Contrast: a real syntax error is an EXPECTED shell error — it renders and
    # returns 2 even under strict-errors (it must NOT re-raise).
    shell = Shell(norc=True)
    shell.validate_only = True
    shell.state.options['strict-errors'] = True
    rc = handle_visitor_mode_for_content(shell, 'if', '-c')
    assert rc == 2


# --- Guard: the shared helper does exactly lex→alias→parse ---

def test_lex_and_parse_helper_roundtrip():
    from psh.ast_nodes import Program
    from psh.scripting.lex_parse import lex_and_expand, lex_and_parse, parse_tokens
    shell = Shell(norc=True)
    prog = lex_and_parse('echo hi', shell)
    assert isinstance(prog, Program)
    tokens, hmap = lex_and_expand('echo hi', shell)
    assert hmap is None
    prog2 = parse_tokens(tokens, hmap, shell)
    assert isinstance(prog2, Program)
