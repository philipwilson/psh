"""The ``braceexpand`` shell option gates brace expansion (bash set -B/+B).

Before v0.672 the option was registered (default ON, ``$-`` letter B) but a
complete NO-OP: nothing consulted it, and ``set -B``/``set +B`` were rejected
as invalid options. Since v0.678 brace expansion is a WORD-stage step (bash's
own position), so a ``set``/``shopt`` that actually RUNS updates the LIVE
option and the NEXT command's expansion honours it — no parse-time look-ahead
scanner. These tests pin the wired behavior at three levels:

- runtime toggle: a same-line ``set +B; echo {a,b}`` and its ``set +o`` /
  ``shopt -so/-uo braceexpand`` cousins take effect at RUNTIME, and — unlike
  the old token-stream scanner — the 6 approximation classes (toggle in a
  not-taken branch / uncalled function / shadowed builtin / pipeline segment,
  invalid clusters, quoted operands) are now correct FOR FREE;
- shell-level: toggling via ``set +o braceexpand`` / ``set +B`` affects later
  commands, ``$-`` and the ``set -o``/``set +o`` listings track;
- CLI-level: ``psh -B``/``+B`` invocation flags (bash-compatible).

Ground truth: bash 5.2.26 (see tests/behavioral/golden_cases.yaml braceexp_*
for the bash-compared battery; the same commands were probed vs bash 5.2.26 in
tmp/probe_brace.py).
"""

import os
import subprocess
import sys


def _clean_env():
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "XAUTHORITY")}
    return env


def _run_psh(argv, script):
    return subprocess.run(
        [sys.executable, "-m", "psh", *argv, "-c", script],
        capture_output=True, text=True, env=_clean_env(), timeout=15)


def _out(script):
    """stdout of running `script` through psh -c (subprocess: some cases fork
    subshells/pipelines whose option scope only shows at fd level)."""
    return _run_psh([], script).stdout


# ---------------------------------------------------------------------------
# Runtime: the live option value gates expansion of the NEXT command
# ---------------------------------------------------------------------------

def test_default_expands():
    assert _out("echo {a,b}") == "a b\n"


def test_set_plusB_keeps_braces_literal():
    assert _out("set +B; echo {a,b}") == "{a,b}\n"


def test_set_plusB_keeps_range_literal():
    assert _out("set +B; echo {1..3}") == "{1..3}\n"


def test_set_plus_o_braceexpand_literal():
    assert _out("set +o braceexpand; echo {a,b}") == "{a,b}\n"


def test_set_minus_B_reenables():
    assert _out("set +B; set -B; echo {a,b}") == "a b\n"


def test_cluster_with_B():
    assert _out("set +xB; echo {a,b}") == "{a,b}\n"


def test_trailing_o_name_is_pipefail_not_braceexpand():
    # `set -euo pipefail`: the trailing o's name is pipefail; braceexpand
    # stays ON, so {a,b} still expands.
    assert _out("set -euo pipefail; echo {a,b}") == "a b\n"


def test_set_own_arguments_expand_then_toggle():
    # bash expands a command's words BEFORE running it: `set +B a b` expands
    # nothing here but sets $1/$2, and B is off only for LATER commands.
    assert _out("set +B x{1,2}; echo \"$1 $2\"; echo {c,d}") == "x1 x2\n{c,d}\n"


def test_double_dash_stops_option_parsing():
    # `set -- +B` sets a positional parameter; braceexpand stays ON.
    assert _out("set -- +B; echo {a,b}") == "a b\n"


def test_set_as_argument_not_a_toggle():
    assert _out("echo set +B; echo {a,b}") == "set +B\na b\n"


# ---------------------------------------------------------------------------
# Runtime: subshell / pipeline / background scoping (a toggle in a bash
# subshell does not escape it) — now correct because the option is real state
# ---------------------------------------------------------------------------

def test_subshell_toggle_is_scoped():
    assert _out("(set +B); echo {a,b}") == "a b\n"


def test_toggle_persists_inside_subshell():
    assert _out("set +B; (echo {a,b})") == "{a,b}\n"


def test_pipeline_segment_set_is_discarded():
    assert _out("set +B | cat; echo {a,b}") == "a b\n"


def test_shopt_uo_reenables_across_commands():
    assert _out("set +B; shopt -so braceexpand; echo {a,b}") == "a b\n"


def test_shopt_uo_disables():
    assert _out("shopt -uo braceexpand; echo {a,b}") == "{a,b}\n"


def test_shopt_subshell_toggle_is_scoped():
    assert _out(
        "(shopt -uo braceexpand; echo {a,b}); echo {c,d}") == "{a,b}\nc d\n"


def test_shopt_s_without_o_is_not_a_toggle():
    # braceexpand is a set -o name, NOT a shopt-table name: `shopt -s
    # braceexpand` errors and does NOT change brace expansion.
    assert _out("shopt -s braceexpand 2>/dev/null; echo {a,b}") == "a b\n"


# ---------------------------------------------------------------------------
# The 6 formerly-wrong approximation classes — now correct at runtime because
# only a `set`/`shopt` that actually RUNS changes the option (task #30).
# ---------------------------------------------------------------------------

def test_class1_toggle_in_not_taken_branch_has_no_effect():
    assert _out("if false; then set +B; fi; echo {a,b}") == "a b\n"


def test_class1_toggle_in_uncalled_function_has_no_effect():
    assert _out("f() { set +B; }; echo {a,b}") == "a b\n"


def test_class2_loop_body_reads_option_per_iteration():
    assert _out(
        "for i in 1 2 3; do echo {a,b}; set +B; done") == "a b\n{a,b}\n{a,b}\n"


def test_class3_shadowed_set_does_not_toggle():
    assert _out("set() { :; }; set +B; echo {a,b}") == "a b\n"


def test_class4_pipeline_segment_set_does_not_leak():
    assert _out("true | set +B; echo {a,b}") == "a b\n"


def test_class5_invalid_cluster_does_not_toggle():
    assert _out("set -zB 2>/dev/null; echo {a,b}") == "a b\n"


def test_class6_quoted_operand_now_toggles():
    # The token scanner could not read a quoted operand; the real builtin does.
    assert _out('shopt -so "braceexpand"; set +o "braceexpand"; '
                'echo {a,b}') == "{a,b}\n"


def test_function_body_expands_at_call_time():
    # A function body brace-expands when it RUNS (reading the live option),
    # not when it was defined.
    assert _out("f() { echo {a,b}; }; set +B; f") == "{a,b}\n"


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
# CLI-level: -B / +B invocation flags (_run_psh defined at module top)
# ---------------------------------------------------------------------------

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
