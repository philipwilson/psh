"""The ``braceexpand`` shell option gates brace expansion (bash set -B/+B).

Before v0.672 the option was registered (default ON, ``$-`` letter B) but a
complete NO-OP: nothing consulted it, and ``set -B``/``set +B`` were rejected
as invalid options. These tests pin the wired behavior at three levels:

- tokenize-level: the post-lex brace expander honours the seeded option value
  AND same-stream ``set`` toggles (psh brace-expands at tokenize time, so a
  same-line ``set +B; echo {a,b}`` needs the stream scanner to match bash);
- shell-level: toggling via ``set +o braceexpand`` / ``set +B`` affects later
  commands, ``$-`` and the ``set -o``/``set +o`` listings track;
- CLI-level: ``psh -B``/``+B`` invocation flags (bash-compatible).

Ground truth: bash 5.2.26 (see tests/behavioral/golden_cases.yaml braceexp_*
for the bash-compared battery).
"""

import os
import subprocess
import sys

from psh.lexer import tokenize


def _values(command, shell_options=None):
    return [t.value for t in tokenize(command, shell_options=shell_options)
            if t.value]


def _clean_env():
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "XAUTHORITY")}
    return env


# ---------------------------------------------------------------------------
# Tokenize-level: the seeded option value
# ---------------------------------------------------------------------------

def test_tokenize_disabled_keeps_braces_literal():
    assert _values("echo {a,b}", {"braceexpand": False}) == ["echo", "{a,b}"]


def test_tokenize_disabled_keeps_range_literal():
    assert _values("echo {1..3}", {"braceexpand": False}) == ["echo", "{1..3}"]


def test_tokenize_enabled_expands():
    assert _values("echo {a,b}", {"braceexpand": True}) == ["echo", "a", "b"]


def test_tokenize_without_options_expands():
    """Analysis callers that tokenize with no shell options keep expanding."""
    assert _values("echo {a,b}") == ["echo", "a", "b"]


# ---------------------------------------------------------------------------
# Tokenize-level: same-stream `set` toggles (bash does brace expansion at
# word-expansion time, so a same-line toggle applies to the words after it)
# ---------------------------------------------------------------------------

def test_same_stream_set_plus_B_disables_rest_of_stream():
    assert _values("set +B; echo {a,b}") == ["set", "+B", ";", "echo", "{a,b}"]


def test_same_stream_set_plus_o_braceexpand():
    assert _values("set +o braceexpand; echo {a,b}") == [
        "set", "+o", "braceexpand", ";", "echo", "{a,b}"]


def test_same_stream_set_minus_B_reenables():
    assert _values("set -B; echo {a,b}", {"braceexpand": False}) == [
        "set", "-B", ";", "echo", "a", "b"]


def test_same_stream_cluster_with_B():
    assert _values("set +xB; echo {a,b}") == ["set", "+xB", ";", "echo", "{a,b}"]


def test_same_stream_trailing_o_consumes_other_name():
    """`set -euo pipefail`: the trailing o's name is pipefail, not braceexpand."""
    assert _values("set -euo pipefail; echo {a,b}") == [
        "set", "-euo", "pipefail", ";", "echo", "a", "b"]


def test_same_stream_subshell_toggle_is_scoped():
    """A subshell's `set +B` does not escape it (bash)."""
    assert _values("(set +B); echo {a,b}") == [
        "(", "set", "+B", ")", ";", "echo", "a", "b"]


def test_same_stream_toggle_persists_inside_subshell():
    assert _values("set +B; (echo {a,b})") == [
        "set", "+B", ";", "(", "echo", "{a,b}", ")"]


def test_same_stream_pipeline_set_is_discarded():
    """A pipeline-segment `set +B` runs in a subshell in bash: no effect."""
    assert _values("set +B | cat; echo {a,b}") == [
        "set", "+B", "|", "cat", ";", "echo", "a", "b"]


def test_same_stream_set_own_arguments_use_old_state():
    """bash expands a command's words BEFORE running it: `set +B {a,b}`
    still expands {a,b} into two positional parameters."""
    assert _values("set +B {a,b}") == ["set", "+B", "a", "b"]


def test_same_stream_double_dash_stops_interpretation():
    """`set -- +B` sets a positional parameter; it does not toggle."""
    assert _values("set -- +B; echo {a,b}") == [
        "set", "--", "+B", ";", "echo", "a", "b"]


def test_same_stream_set_as_argument_not_interpreted():
    """`set` outside command position (an argument) is not a toggle."""
    assert _values("echo set +B; echo {a,b}") == [
        "echo", "set", "+B", ";", "echo", "a", "b"]


# ---------------------------------------------------------------------------
# Shell-level: option toggling across commands, $- and listings
# ---------------------------------------------------------------------------

def test_set_plus_o_braceexpand_disables_later_commands(captured_shell):
    assert captured_shell.run_command("set +o braceexpand") == 0
    captured_shell.run_command("echo {a,b} {1..3}")
    assert captured_shell.get_stdout() == "{a,b} {1..3}\n"


def test_set_plus_B_accepted_and_disables(captured_shell):
    assert captured_shell.run_command("set +B") == 0
    assert captured_shell.get_stderr() == ""
    captured_shell.run_command("echo {a,b}")
    assert captured_shell.get_stdout() == "{a,b}\n"


def test_set_minus_B_accepted_and_reenables(captured_shell):
    captured_shell.run_command("set +B")
    assert captured_shell.run_command("set -B") == 0
    assert captured_shell.get_stderr() == ""
    captured_shell.run_command("echo {a,b}")
    assert captured_shell.get_stdout() == "a b\n"


def test_dollar_dash_tracks_B(captured_shell):
    captured_shell.run_command('case $- in *B*) echo hasB;; *) echo noB;; esac')
    assert captured_shell.get_stdout() == "hasB\n"
    captured_shell.clear_output()
    captured_shell.run_command("set +B")
    captured_shell.run_command('case $- in *B*) echo hasB;; *) echo noB;; esac')
    assert captured_shell.get_stdout() == "noB\n"


def test_set_o_listing_tracks(captured_shell):
    captured_shell.run_command("set +B")
    captured_shell.run_command("set -o")
    assert "braceexpand    \toff" in captured_shell.get_stdout()


def test_set_plus_o_reusable_form_tracks(captured_shell):
    captured_shell.run_command("set +B")
    captured_shell.run_command("set +o")
    assert "set +o braceexpand" in captured_shell.get_stdout()


def test_alias_value_honors_disabled_option(captured_shell):
    """Alias text joins the input stream and sees the same expansion
    settings (bash): a brace in an alias VALUE stays literal under +B."""
    captured_shell.run_command("alias a='echo {1,2}'")
    captured_shell.run_command("set +B")
    captured_shell.run_command("a")
    assert captured_shell.get_stdout() == "{1,2}\n"


def test_posix_mode_does_not_disable_braceexpand(captured_shell):
    """bash: `set -o posix` keeps brace expansion enabled."""
    captured_shell.run_command("set -o posix")
    captured_shell.run_command("echo {a,b}")
    assert captured_shell.get_stdout() == "a b\n"


def test_option_persists_into_subshell():
    # Subshells fork and write at fd level, so this runs psh in a
    # subprocess rather than through captured_shell.
    result = _run_psh([], "set +B\n(echo {a,b})")
    assert result.returncode == 0
    assert result.stdout == "{a,b}\n"


def test_option_persists_into_command_substitution(captured_shell):
    captured_shell.run_command("set +B")
    captured_shell.run_command("echo $(echo {a,b})")
    assert captured_shell.get_stdout() == "{a,b}\n"


# ---------------------------------------------------------------------------
# CLI-level: -B / +B invocation flags
# ---------------------------------------------------------------------------

def _run_psh(argv, script):
    return subprocess.run(
        [sys.executable, "-m", "psh", *argv, "-c", script],
        capture_output=True, text=True, env=_clean_env(), timeout=15)


def test_cli_plus_B_disables_brace_expansion():
    result = _run_psh(["+B"], "echo {a,b}")
    assert result.returncode == 0
    assert result.stdout == "{a,b}\n"
    assert result.stderr == ""


def test_cli_minus_B_enables_brace_expansion():
    result = _run_psh(["-B"], "echo {a,b}")
    assert result.returncode == 0
    assert result.stdout == "a b\n"
    assert result.stderr == ""
