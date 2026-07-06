"""Backslash quoting on the command word suppresses aliases, not functions.

Bash semantics (F2): a leading backslash (`\\ls`, `\\echo`) quotes the command
word. Quoting suppresses ALIAS expansion, but after quote removal the plain
name still participates in normal function -> builtin -> external lookup. psh
previously bypassed BOTH alias and function lookup on the backslash path, so
`\\f` failed to find a defined function `f`.

These exercise real command lookup/forking, so they run psh in a subprocess.
"""

import subprocess
import sys


def _run(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_backslash_calls_defined_function():
    out, _, rc = _run("f() { echo FUNC; }; \\f")
    assert out == "FUNC\n"
    assert rc == 0


def test_backslash_function_shadowing_builtin():
    out, _, _ = _run("echo() { printf 'FUNCTION\\n'; }; \\echo hi")
    assert out == "FUNCTION\n"


def test_backslash_export_function_not_builtin():
    # \export must call the export() function, which does NOT export X.
    out, _, _ = _run(
        "export() { echo FUNCTION; }; \\export X=y; "
        "printf 'X=<%s>\\n' \"${X-unset}\"")
    assert out == "FUNCTION\nX=<unset>\n"


def test_backslash_exit_function_does_not_exit():
    # \exit must call the exit() function (shell keeps running -> 'after').
    out, _, _ = _run("exit() { echo EXITFUNC; }; \\exit; echo after")
    assert out == "EXITFUNC\nafter\n"


def test_backslash_echo_is_builtin_when_no_function():
    out, _, _ = _run("\\echo hi")
    assert out == "hi\n"


def test_backslash_export_is_builtin_when_no_function():
    out, _, _ = _run("unset X; \\export X=y; printf 'X=<%s>\\n' \"${X-unset}\"")
    assert out == "X=<y>\n"


def test_backslash_still_suppresses_alias():
    # \e must NOT expand the alias; with no command `e`, lookup fails -> 127.
    out, err, _ = _run("alias e='echo A'; \\e; echo \"rc=$?\"")
    assert out == "rc=127\n"
    assert "command not found" in err


def test_command_builtin_still_bypasses_function():
    out, _, _ = _run("echo() { printf 'FUNC\\n'; }; command echo hi")
    assert out == "hi\n"


def test_backslash_export_word_splits_argument():
    # A backslash-quoted command word is NOT a declaration builtin, so its
    # `foo=$x` argument is word-split like an ordinary command argument.
    # `\export foo=$x` with x="a b" therefore passes two words to export.
    out, _, _ = _run(
        "x='a b'; \\export foo=$x; declare -p foo 2>/dev/null")
    # foo is set to 'a'; 'b' is a separate (invalid-name) export argument.
    assert out == 'declare -x foo="a"\n'
