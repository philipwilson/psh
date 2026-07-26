"""Absolute line numbers for parse errors on heredoc-bearing commands.

Remediation B1 pins. Rerouting the heredoc branch through the one
``parse_with_inputs`` entry threads ``line_offset``/``source_text`` into the RD
parser for the FIRST time (the deleted ``utils.parse_with_heredocs`` hard-coded
line_offset=0 / source_text=None). So a parse error in a nested substitution of
a heredoc-bearing command now reports the ABSOLUTE source line — matching bash —
instead of the fragment-relative line 1.

RED AT BASE: at db6dfb13 the probe below reported ``line 1``; at tip it reports
``line 3`` (= bash 5.2.26). The base number was independently replayed by
verification round-1 (T1) and is re-derived here in process by
``test_old_no_offset_path_reported_line_1`` (calling the entry with the old
line_offset=0 budget still yields line 1), so these pins encode the NEW correct
numbers and would fail against the old behavior.
"""

import subprocess
import sys

import pytest

from psh.lexer import tokenize_with_heredocs
from psh.parser import ParseError, ParseInputs, parse_with_inputs

# The heredoc-bearing command exactly as the source processor hands it to the
# parser: a nested `$(if)` (incomplete → end-of-file error) plus a `<<EOF` body.
_HEREDOC_FRAGMENT = "echo $(if) <<EOF\nbody\nEOF\n"

# Two-line pad in front, so the erroring command sits on absolute line 3.
_PAD_HEREDOC_SCRIPT = ": p1\n: p2\n" + _HEREDOC_FRAGMENT

# Function body: the heredoc-bearing command with the nested error on line 3.
_FUNC_HEREDOC_SCRIPT = "f() {\n  : pad\n  echo $(if) <<EOF\nbody\nEOF\n}\n"


def _err_line(line_offset, source_text):
    """error_context.line for the fragment parsed under *line_offset*."""
    lu = tokenize_with_heredocs(_HEREDOC_FRAGMENT)
    inputs = ParseInputs(source_text=source_text, line_offset=line_offset,
                         heredocs=lu.heredocs)
    with pytest.raises(ParseError) as excinfo:
        parse_with_inputs(list(lu.tokens), inputs, "recursive_descent")
    return excinfo.value.error_context.line


def test_threaded_offset_reports_absolute_line_3():
    # The command at file line 3 → line_offset 2 → the nested error reports line 3.
    assert _err_line(2, _PAD_HEREDOC_SCRIPT) == 3


def test_old_no_offset_path_reported_line_1():
    # Red-at-base witness: the OLD heredoc path threaded no line_offset/source
    # (line_offset=0), so the same nested error reported the fragment-relative
    # line 1. This is exactly the number the pins above replace.
    assert _err_line(0, None) == 1


def _run(mode, script, tmp_path):
    """Run *script* through psh in file / -c / stdin mode; return stderr."""
    if mode == "file":
        p = tmp_path / "probe.sh"
        p.write_text(script)
        r = subprocess.run([sys.executable, "-m", "psh", str(p)],
                           capture_output=True, text=True)
    elif mode == "-c":
        r = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                           capture_output=True, text=True)
    else:  # stdin
        r = subprocess.run([sys.executable, "-m", "psh"], input=script,
                           capture_output=True, text=True)
    return r.stderr


@pytest.mark.parametrize("mode", ["file", "-c", "stdin"])
def test_pad_heredoc_absolute_line_all_modes(mode, tmp_path):
    # The rendered diagnostic pins the absolute line in BOTH coordinates: the
    # `psh: <source>:3:` prefix and the `(line 3, ...)` caret coordinate.
    stderr = _run(mode, _PAD_HEREDOC_SCRIPT, tmp_path)
    assert ":3:" in stderr
    assert "line 3" in stderr


@pytest.mark.parametrize("mode", ["file", "-c", "stdin"])
def test_function_body_heredoc_absolute_line_all_modes(mode, tmp_path):
    stderr = _run(mode, _FUNC_HEREDOC_SCRIPT, tmp_path)
    assert ":3:" in stderr
    assert "line 3" in stderr


def test_no_pad_control_is_line_1(tmp_path):
    # Control: with no pad the command IS on line 1, so both base and tip report
    # line 1 — the fix moves the number only when there is an offset to apply.
    stderr = _run("file", _HEREDOC_FRAGMENT, tmp_path)
    assert ":1:" in stderr
    assert "line 1" in stderr
