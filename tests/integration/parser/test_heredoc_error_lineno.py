"""Absolute line numbers for parse errors on heredoc-bearing commands.

Remediation B1 pins. Rerouting the heredoc branch through the one
``parse_with_inputs`` entry threads ``line_offset``/``source_text`` into the
parser for the FIRST time (the deleted ``utils.parse_with_heredocs`` hard-coded
line_offset=0 / source_text=None). So a parse error in a nested substitution of
a heredoc-bearing command now reports the ABSOLUTE source line — matching bash —
instead of the fragment-relative line 1. This manifests on BOTH parsers
(remediation R3-4): the nested-substitution error is parsed by the recursive
descent parser via the shared nested-parse path even under ``--parser
combinator``, so the threaded offset reaches it on either active parser (the
subprocess pins run both).

RED AT BASE (genuine db6dfb13 probes, throwaway base worktree, all three modes;
both parsers behave identically here):
  * pad + heredoc (erroring command on line 3): base ``line 1`` → tip ``line 3``
    = bash 5.2.26 ``line 3``.
  * function defined after a pad (heredoc body command on line 4): base
    ``line 2`` → tip ``line 4`` = bash ``line 4``.
  * no-pad control (command on line 1): base ``line 1`` = tip ``line 1`` (no
    offset to apply, no delta).
So these pins encode the NEW (correct, bash-matching) numbers and were RED at
base. Corroborated by verification round-1 T1's independent replay and by the
in-process ``test_old_no_offset_path_reported_line_1`` witness (the old
line_offset=0 budget still yields the fragment-relative line 1).
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

# Function DEFINED after a two-line pad: the function is command 3 (start line 3),
# its heredoc-bearing body command errors on absolute line 4. This is the shape
# that carries the delta — at base it reported line 2, at tip line 4 (= bash). (A
# function defined at line 1 does NOT show the delta: its whole body is one
# command buffer, so the error line is already absolute at base.)
_FUNC_HEREDOC_SCRIPT = ": p1\n: p2\nf() {\n  echo $(if) <<EOF\nbody\nEOF\n}\n"


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


def _run(mode, script, tmp_path, parser="rd"):
    """Run *script* through psh in file / -c / stdin mode; return stderr.

    ``parser`` selects the active parser. The improvement manifests on BOTH
    parsers (remediation R3-4): the nested-substitution error whose line this
    pins is parsed by the recursive-descent parser via the shared nested-parse
    path even under ``--parser combinator``, so the threaded line_offset reaches
    it either way.
    """
    base = [sys.executable, "-m", "psh"]
    if parser == "combinator":
        base += ["--parser", "combinator"]
    if mode == "file":
        p = tmp_path / "probe.sh"
        p.write_text(script)
        r = subprocess.run(base + [str(p)], capture_output=True, text=True)
    elif mode == "-c":
        r = subprocess.run(base + ["-c", script], capture_output=True, text=True)
    else:  # stdin
        r = subprocess.run(base, input=script, capture_output=True, text=True)
    return r.stderr


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("mode", ["file", "-c", "stdin"])
def test_pad_heredoc_absolute_line_all_modes(mode, parser, tmp_path):
    # The rendered diagnostic pins the absolute line in BOTH coordinates: the
    # `psh: <source>:3:` prefix and the `(line 3, ...)` caret coordinate. Both
    # parsers report line 3 (verifier-confirmed: base 1 → tip 3 on each).
    stderr = _run(mode, _PAD_HEREDOC_SCRIPT, tmp_path, parser)
    assert ":3:" in stderr
    assert "line 3" in stderr


@pytest.mark.parametrize("parser", ["rd", "combinator"])
@pytest.mark.parametrize("mode", ["file", "-c", "stdin"])
def test_function_body_heredoc_absolute_line_all_modes(mode, parser, tmp_path):
    # Function defined at line 3, heredoc body command errors on line 4.
    # Red at base: base reported line 2 (genuine base-worktree probe), tip line 4
    # — on BOTH parsers.
    stderr = _run(mode, _FUNC_HEREDOC_SCRIPT, tmp_path, parser)
    assert ":4:" in stderr
    assert "line 4" in stderr


def test_no_pad_control_is_line_1(tmp_path):
    # Control: with no pad the command IS on line 1, so both base and tip report
    # line 1 — the fix moves the number only when there is an offset to apply.
    stderr = _run("file", _HEREDOC_FRAGMENT, tmp_path)
    assert ":1:" in stderr
    assert "line 1" in stderr
