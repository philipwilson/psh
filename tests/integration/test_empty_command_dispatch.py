"""Empty command name vs zero-field expansion (executor F1).

A QUOTED empty word (`''`, `""`, `"$empty"`) produces ONE empty field: an
attempted invocation of a command whose name is the empty string. Bash
performs normal command lookup, fails, and returns 127 — and a prefix
assignment before such a command is TEMPORARY (not persisted), exactly like
any failed command invocation.

An UNQUOTED empty/unset expansion (`$empty`) produces ZERO fields: there is
no command, so a prefix assignment persists (pure-assignment semantics).

These drive real command lookup (the empty-named command falls through to the
external strategy, which forks), so they run psh in a subprocess.
"""

import subprocess
import sys


def _run(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_empty_single_quote_command_not_found():
    out, err, rc = _run("''; printf 'rc=%s\\n' \"$?\"")
    assert out == "rc=127\n"
    assert "command not found" in err
    assert rc == 0


def test_empty_double_quote_command_not_found():
    out, _, _ = _run("\"\"; printf 'rc=%s\\n' \"$?\"")
    assert out == "rc=127\n"


def test_empty_quoted_var_command_not_found():
    out, _, _ = _run("empty=; \"$empty\"; printf 'rc=%s\\n' \"$?\"")
    assert out == "rc=127\n"


def test_empty_unquoted_var_is_zero_fields():
    # $empty vanishes -> no command -> rc 0
    out, err, rc = _run("empty=; $empty; printf 'rc=%s\\n' \"$?\"")
    assert out == "rc=0\n"
    assert err == ""
    assert rc == 0


def test_prefix_before_empty_quoted_does_not_persist():
    out, _, _ = _run(
        "unset X; X=v ''; printf 'rc=%s X=<%s>\\n' \"$?\" \"${X-unset}\"")
    assert out == "rc=127 X=<unset>\n"


def test_prefix_before_empty_unquoted_persists():
    # Zero fields -> pure assignment -> X persists (bash).
    out, _, _ = _run(
        "unset X; empty=; X=v $empty; printf 'rc=%s X=<%s>\\n' \"$?\" \"${X-unset}\"")
    assert out == "rc=0 X=<v>\n"


def test_empty_command_with_argument():
    out, _, _ = _run("'' arg; printf 'rc=%s\\n' \"$?\"")
    assert out == "rc=127\n"


def test_empty_command_diagnostic_names_empty():
    # bash prints "` `: command not found"; psh's diagnostic likewise carries
    # an empty command-name field (only the shell-name prefix differs).
    _, err, _ = _run("''")
    assert ": command not found" in err
