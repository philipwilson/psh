"""Sourced-program service semantics matrix (campaign F3).

Pins ``execute_sourced_file`` — the ONE executor behind ``source``/``.`` AND
rc loading — against the bash 5.2 oracle: source depth, ``return`` at depth,
RETURN traps, the positional swap with bash's ``set``-persistence rule, the
rc dialect rows (continuation medium 2), and the F1-handoff rule that
sourced files never bang-expand. Ground truth and red-on-base evidence:
tmp/boundary-ledgers/F3-probes/ (base batteries B/C/D at SHA 11e6661d).

The facts a future reader will not believe without the transcripts:

* ``return 7`` in an rc ends the rc CLEANLY: no diagnostic, the rest of the
  line and file are dropped, startup continues, and the return status is
  DISCARDED — ``$?`` at the first command keeps the last pre-return
  command's status (``false; return 7`` leaves ``$?`` = 1, plain
  ``return 7`` leaves 0). A ``source`` adopts N as its status instead.
* The RETURN trap fires per completed ``source`` but NEVER at the end of
  the rc — not even for an explicit ``return`` in the rc.
* ``set -- z`` inside an args-passed ``source`` PERSISTS (the caller's
  positionals are NOT restored) and the effect is consumed by exactly one
  args-passed boundary; ``shift`` restores normally, and a ``set`` inside a
  function called from the sourced file does not mark the source's frame.
* Sourced files never history-expand, even under an interactive family
  whose main stream does (``-i -s`` / ``-i script.sh``).
"""
import sys
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, run_shell_case, try_resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
_ORACLE = try_resolve_bash()

pytestmark = pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")


def _run(argv, *, stdin, cwd, shell_tag):
    # Per-shell HISTFILE, psh first (run_both): an interactive bash writes
    # its session back to $HISTFILE on exit (RESUME standing lesson).
    extra = {"HISTFILE": f"{cwd}/hist-{shell_tag}"}
    if argv[0] == sys.executable:
        extra["PYTHONPATH"] = str(REPO_ROOT)
    result = run_shell_case(argv, stdin_data=stdin,
                            env=hermetic_shell_env(extra), cwd=cwd, timeout=30)
    assert isinstance(result, Completed), result
    return result


def run_both(args, *, stdin=None, files=None, tmp_path):
    for rel, content in (files or {}).items():
        (tmp_path / rel).write_text(content)
    psh = _run([sys.executable, "-m", "psh", *args], stdin=stdin,
               cwd=str(tmp_path), shell_tag="psh")
    bash = _run([_ORACLE.path, *args], stdin=stdin, cwd=str(tmp_path),
                shell_tag="bash")
    return psh, bash


# One row: (id, args, stdin, files, psh_stderr_contains).
# Comparison is always returncode + stdout equality against bash; files are
# written into tmp_path (the cwd), so scripts reference them as ./name.
MATRIX = [
    # --- rc return semantics (continuation medium 2; probes B1-B13) ---
    ("rc_return_stops_rc_silently", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n", {"rc": "echo before\nreturn 7\necho after\n"}, None),
    ("rc_return_discards_status", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n", {"rc": "return 7\n"}, None),
    ("rc_return_keeps_pre_return_status", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n", {"rc": "false\nreturn 7\n"}, None),
    ("rc_return_kills_rest_of_line", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n",
     {"rc": "echo before\nreturn 7; echo sameline\necho after\n"}, None),
    ("rc_return_bad_numeric_still_stops", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n", {"rc": "echo before\nreturn abc\necho after\n"},
     "numeric argument required"),
    ("rc_no_return_trap_at_end", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n", {"rc": "trap 'echo RET' RETURN\necho mid\n"}, None),
    ("rc_no_return_trap_on_explicit_return", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n",
     {"rc": "trap 'echo RET' RETURN\necho mid\nreturn 7\necho after\n"}, None),
    ("rc_natural_end_keeps_last_status", ["--rcfile", "rc", "-i", "-s"],
     "echo body $?\n", {"rc": "sh -c 'exit 9'\n"}, None),
    ("rc_exit_still_exits_shell", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n", {"rc": "echo before\nexit 5\necho after\n"}, None),
    ("rc_function_return_is_local", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n", {"rc": "f(){ return 3; echo nf; }\nf\necho rc-cont $?\n"},
     None),
    ("rc_sources_inner_return_contained", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n", {"rc": "echo r1\n. ./inner\necho r2 $?\n",
                     "inner": "echo i1\nreturn 5\necho i2\n"}, None),
    ("rc_unbound_line_discarded", ["--rcfile", "rc", "-i", "-s"],
     "echo body\n", {"rc": "set -u\necho a $nope\necho b\n"},
     "unbound variable"),
    # --- sourced files never bang-expand (F1 handoff; probes C1-C3) ---
    ("sourced_file_no_bang_expansion", ["--norc", "-i", "-s"],
     "echo MARKER\n. ./f\n", {"f": "echo !!\n"}, None),
    ("main_stream_bang_still_expands", ["--norc", "-i", "-s"],
     "echo MARKER\necho !!\n", None, None),
    ("i_script_own_lines_expand_sourced_stay_literal",
     ["--norc", "-i", "s.sh"], None,
     {"s.sh": "echo MARKER\n. ./f\n", "f": "echo !!\n"}, None),
    # --- source depth / return-at-depth (probes D1-D2, D8-D9) ---
    ("nested_x3_return_at_depth_3",
     ["--norc", "-c", ". ./f1; echo top $?"], None,
     {"f1": "echo f1-in\n. ./f2\necho f1-after $?\n",
      "f2": "echo f2-in\n. ./f3\necho f2-after $?\n",
      "f3": "echo f3-in\nreturn 5\necho f3-never\n"}, None),
    ("bare_return_keeps_last_status",
     ["--norc", "-c", ". ./f1; echo top $?"], None,
     {"f1": "echo a\n. ./f2\necho after $?\n",
      "f2": "false\nreturn\necho never\n"}, None),
    ("return_n_becomes_source_status",
     ["--norc", "-c", ". ./f; echo rc=$?"], None,
     {"f": "echo in\nreturn 3\necho never\n"}, None),
    ("source_status_is_last_command",
     ["--norc", "-c", ". ./f; echo rc=$?"], None,
     {"f": "echo in\nfalse\n"}, None),
    # --- RETURN trap through the service (probe D3) ---
    ("return_trap_fires_per_source_completion",
     ["--norc", "-c", "trap 'echo RET:$?' RETURN; . ./f1; echo done"], None,
     {"f1": "echo f1\n. ./f2\n", "f2": "echo f2\n"}, None),
    # --- positionals: swap, restore, and the set-persistence rule
    #     (probes D4-D5g) ---
    ("args_swap_and_restore",
     ["--norc", "-c", "set -- p1 p2; . ./f a b; echo after:$1,$2,$#"], None,
     {"f": "echo during:$1,$2,$#\n"}, None),
    ("args_restore_to_empty",
     ["--norc", "-c", ". ./f a b; echo after:$#,${1-unset}"], None,
     {"f": "echo during:$1,$2,$#\n"}, None),
    ("set_inside_args_source_persists",
     ["--norc", "-c", "set -- p1 p2; . ./f a b; echo after:$1,$2,$#"], None,
     {"f": "set -- z\necho during:$1,$#\n"}, None),
    ("set_clear_inside_args_source_persists_empty",
     ["--norc", "-c", "set -- p1 p2; . ./f a b; echo top:$#,${1-unset}"],
     None, {"f": "set --\necho during:$#\n"}, None),
    ("shift_inside_args_source_restores",
     ["--norc", "-c", "set -- p1 p2; . ./f a b c; echo after:$1,$#"], None,
     {"f": "shift\necho during:$1,$#\n"}, None),
    ("no_args_source_set_persists",
     ["--norc", "-c", "set -- p1 p2; . ./f; echo after:$1,$#"], None,
     {"f": "set -- z\necho during:$1,$#\n"}, None),
    ("set_in_nested_no_args_source_persists_to_top",
     ["--norc", "-c", "set -- p1; . ./f1 a b; echo top:$1,$#"], None,
     {"f1": ". ./f2\necho f1:$1,$#\n", "f2": "set -- z\n"}, None),
    ("set_consumed_by_one_boundary",
     ["--norc", "-c", "set -- p1 p2; . ./f a b; . ./g x; echo top:$1,$#"],
     None, {"f": "set -- z\n", "g": "echo g:$1,$#\n"}, None),
    ("set_in_function_does_not_mark_source",
     ["--norc", "-c", "set -- p1 p2; . ./f a b; echo top:$1,$#"], None,
     {"f": "fn(){ set -- q; }\nfn\necho during:$1,$#\n"}, None),
    ("nested_both_args_inner_set_persists_one_level",
     ["--norc", "-c", "set -- p1; . ./f1 a b; echo top:$1,$#"], None,
     {"f1": ". ./f2 c d\necho f1:$1,$#\n", "f2": "set -- z\n"}, None),
    ("restore_on_exception_exit",
     ["--norc", "-c",
      "set -- p1 p2; readonly r=1; . ./f a b; echo after:$1,$#"], None,
     {"f": "echo during:$1\nr=2\necho f-never\n"}, "readonly variable"),
    # --- mode variation: the service is input-mode independent (D11) ---
    ("return_status_via_script_channel", ["--norc", "s.sh"], None,
     {"s.sh": ". ./f\necho rc=$?\n", "f": "echo in\nreturn 3\necho never\n"},
     None),
    ("return_status_via_stdin_channel", ["--norc"],
     ". ./f\necho rc=$?\n",
     {"f": "echo in\nreturn 3\necho never\n"}, None),
]


@pytest.mark.parametrize("row_id,args,stdin,files,psh_stderr_contains",
                         MATRIX, ids=[row[0] for row in MATRIX])
def test_source_service_row(row_id, args, stdin, files, psh_stderr_contains,
                            tmp_path):
    psh, bash = run_both(args, stdin=stdin, files=files, tmp_path=tmp_path)
    assert psh.returncode == bash.returncode, (
        f"exit codes diverge: psh={psh.returncode} bash={bash.returncode}\n"
        f"psh stderr: {psh.stderr!r}\nbash stderr: {bash.stderr!r}")
    assert psh.stdout == bash.stdout, (
        f"stdout diverges:\npsh : {psh.stdout!r}\nbash: {bash.stdout!r}")
    if psh_stderr_contains is not None:
        assert psh_stderr_contains in psh.stderr, psh.stderr


class TestDocumentedDivergences:
    """psh-only pins where bash's behavior is not worth reproducing."""

    def test_infinite_source_chain_clean_limit(self, tmp_path):
        # bash 5.2 SEGFAULTS (rc 139/-11) on `. self` recursion (probe
        # D10); psh degrades to a clean resource-limit diagnostic and the
        # whole current input line dies with status 1 — deliberate
        # divergence, kept by the service.
        (tmp_path / "self").write_text(". ./self\n")
        psh = _run([sys.executable, "-m", "psh", "--norc", "-c",
                    ". ./self; echo rc=$?"], stdin=None, cwd=str(tmp_path),
                   shell_tag="psh")
        assert psh.returncode == 1
        assert psh.stdout == ""
        assert "maximum recursion depth exceeded" in psh.stderr

    def test_rc_return_no_diagnostic_on_stderr(self, tmp_path):
        # The old rc path printed "can only `return' from a function or
        # sourced script" and KEPT RUNNING the rc; both halves are pinned
        # bash-shaped by the matrix rows — this adds the psh-side stderr
        # absence explicitly.
        (tmp_path / "rc").write_text("echo before\nreturn 7\necho after\n")
        psh = _run([sys.executable, "-m", "psh", "--rcfile", "rc", "-i", "-s"],
                   stdin="echo body $?\n", cwd=str(tmp_path), shell_tag="psh")
        assert psh.returncode == 0
        assert psh.stdout == "before\nbody 0\n"
        assert "can only" not in psh.stderr
