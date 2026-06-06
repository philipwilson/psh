"""Builtins must write to shell.stdout, not bare print() (sys.stdout).

Regression for the bug where several builtins used bare ``print()``, bypassing
``shell.stdout``. That leaks output to ``sys.stdout`` and breaks in-process
capture / redirection (e.g. builtin-to-builtin pipelines under test mode).

Each test calls the builtin's ``execute`` directly with ``shell.stdout`` set to a
StringIO (bypassing the executor's stdout reset) and asserts the output is
captured there and does NOT leak to ``sys.stdout``.
"""

import io
import sys

import pytest

from psh.builtins.registry import registry
from psh.shell import Shell


def _run_builtin(argv):
    """Run a builtin directly; return (captured_via_shell_stdout, leaked_to_sys)."""
    shell = Shell()
    buf = io.StringIO()
    shell.stdout = buf
    real_sys = sys.stdout
    sys.stdout = leak = io.StringIO()
    try:
        registry.get(argv[0]).execute(argv, shell)
    finally:
        sys.stdout = real_sys
    return buf.getvalue(), leak.getvalue()


@pytest.mark.parametrize("argv, expected", [
    (["parser-config"], "Parser Configuration"),
    (["parser-mode"], "Parser mode"),
    (["debug"], "Debug Options"),
    (["kill", "-l"], "SIG"),
])
def test_builtin_writes_to_shell_stdout(argv, expected):
    captured, leaked = _run_builtin(argv)
    assert expected in captured, f"{argv}: expected output on shell.stdout"
    assert leaked == "", f"{argv}: output leaked to sys.stdout: {leaked!r}"


def test_parse_tree_writes_to_shell_stdout():
    captured, leaked = _run_builtin(["parse-tree", "echo hi"])
    assert captured.strip(), "parse-tree produced no output on shell.stdout"
    assert leaked == ""


def test_cd_dash_prints_to_shell_stdout(tmp_path):
    # `cd -` echoes the directory it switched to; that echo must use shell.stdout.
    shell = Shell()
    buf = io.StringIO()
    shell.stdout = buf
    real_sys = sys.stdout
    sys.stdout = leak = io.StringIO()
    try:
        cd = registry.get("cd")
        cd.execute(["cd", str(tmp_path)], shell)
        buf.truncate(0); buf.seek(0)
        leak.truncate(0); leak.seek(0)
        cd.execute(["cd", "-"], shell)  # prints the previous dir
    finally:
        sys.stdout = real_sys
    assert buf.getvalue().strip(), "cd - produced no output on shell.stdout"
    assert leak.getvalue() == ""
