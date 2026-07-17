"""Invocation matrix: source kind x interactive flags x transitions (F1).

Every bash-compared row runs psh and the bash 5.2 oracle through the shared
``run_shell_case`` runner and asserts identical exit status and stdout
(stderr carries bash's tty/job-control noise for interactive-family rows, so
rows assert psh-side stderr substrings explicitly where the diagnostic
matters). Ground truth and red-on-base evidence:
tmp/boundary-ledgers/F1-probes/ (base-battery/base-followup/base-policy*,
SHA 992787a9).

Highlights a future reader will not believe without the transcript:
* ``+c 'echo hi'`` ENABLES command mode and prints hi (bash probe C12);
* ``+s`` acts exactly like ``-s`` (probe E2/C10) while ``+i`` CANCELS ``-i``
  (probes C8/C9) — bash's sign semantics differ per letter;
* a bare trailing ``-o``/``+o`` prints the option listing (exit 0) and the
  shell then proceeds (probe E3/E3b);
* ``-h`` is bash ``hashall``, not help (campaign decision; probe C1);
* ``bash -ic`` sources the rc, sets ``i``/``H`` in ``$-``, aborts an
  unbound-variable LINE with status 1 (not 127), and never bang-expands the
  ``-c`` string (probes B1-B8);
* ``-H``/``+H`` work at invocation AND ``set -H``/``set +H`` at runtime
  (probe E5; closes reappraisal-21 CORE-4).
"""
import sys
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, run_shell_case, try_resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
_ORACLE = try_resolve_bash()

pytestmark = pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")


def _run(argv, *, stdin, cwd, histfile):
    extra = {"HISTFILE": histfile}
    if argv[0] == sys.executable:
        extra["PYTHONPATH"] = str(REPO_ROOT)
    result = run_shell_case(argv, stdin_data=stdin,
                            env=hermetic_shell_env(extra), cwd=cwd, timeout=30)
    assert isinstance(result, Completed), result
    return result


def run_both(args, *, stdin=None, files=None, tmp_path, hist_content=None):
    """Run psh and bash with identical args in *tmp_path*; return both."""
    for rel, content in (files or {}).items():
        (tmp_path / rel).write_text(content)
    histfile = tmp_path / "histfile"
    if hist_content is not None:
        histfile.write_text(hist_content)
    psh = _run([sys.executable, "-m", "psh", *args], stdin=stdin,
               cwd=str(tmp_path), histfile=str(histfile))
    bash = _run([_ORACLE.path, *args], stdin=stdin, cwd=str(tmp_path),
                histfile=str(histfile))
    return psh, bash


# One row: (id, args, stdin, files, psh_stderr_contains)
# Comparison is always returncode + stdout equality against bash.
MATRIX = [
    # --- registry-derived short-option surface (medium 1) ---
    ("h_is_hashall", ["--norc", "-h", "-c", "echo $-"], None, None, None),
    ("plus_h_drops_hashall", ["--norc", "+h", "-c", "echo $-"], None, None, None),
    ("a_allexport", ["--norc", "-a", "-c", "v=1; printenv v"], None, None, None),
    ("b_notify_flag", ["--norc", "-b", "-c", "echo $-"], None, None, None),
    ("E_T_flags", ["--norc", "-E", "-T", "-c", "echo $-"], None, None, None),
    ("m_dropped_without_tty", ["--norc", "-m", "-c", "echo $-"], None, None, None),
    ("cluster_amx", ["--norc", "-amx", "-c", "echo $-"], None, None, None),
    ("H_invocation_flag", ["--norc", "-H", "-c", "echo $-"], None, None, None),
    ("plus_H_under_ic", ["--norc", "+H", "-ic", "echo $-"], None, None, None),
    # Runtime set -H / set +H (reappraisal-21 CORE-4: both spellings were
    # rejected while the registry reserved the H letter).
    ("runtime_set_H", ["--norc", "-c", "set -H; echo $-"], None, None, None),
    ("runtime_set_plus_H", ["--norc", "-ic", "set +H; echo $-"], None, None, None),
    # --- invocation-only sign semantics (bash-probed; i aware, s/c blind) ---
    ("plus_i_alone_not_interactive", ["--norc", "+i", "-c", "echo $-"],
     None, None, None),
    ("plus_i_cancels_dash_i", ["--norc", "-i", "+i", "-c", "echo $-"],
     None, None, None),
    ("plus_i_piped_stdin", ["--norc", "+i"], "echo $-\n", None, None),
    ("plus_s_acts_like_dash_s", ["--norc", "+s", "A", "B"],
     "echo 1=${1-none} 2=${2-none}\n", None, None),
    ("plus_s_no_cancel", ["--norc", "-s", "+s", "s.sh"], "echo from-stdin\n",
     {"s.sh": "echo from-script\n"}, None),
    ("plus_c_enables_command_mode", ["--norc", "+c", "echo hi"], None, None, None),
    ("plus_c_no_cancel", ["--norc", "-c", "+c", "s.sh"], None,
     {"s.sh": "echo from-script\n"}, "command not found"),
    # --- source kind x flags: $- truth ---
    ("dash_c_flags", ["--norc", "-c", "echo $-"], None, None, None),
    ("sc_keeps_stdin_flag", ["--norc", "-sc", "echo $-"], None, None, None),
    ("ic_flags", ["--norc", "-ic", "echo $-"], None, None, None),
    ("i_script_flags", ["--norc", "-i", "s.sh"], None,
     {"s.sh": "echo $-\n"}, None),
    ("i_s_piped_flags", ["--norc", "-i", "-s"], "echo $-\n", None, None),
    ("plain_stdin_flags", ["--norc"], "echo hello:$-\n", None, None),
    ("m_i_s_piped_no_tty", ["--norc", "-m", "-i", "-s"], "echo $-\n",
     None, None),
    ("s_positionals", ["--norc", "-s", "A", "B"], "echo $#:$1:$2\n",
     None, None),
    # --- H17: interactive-family startup independent of source ---
    ("ic_runs_rc", ["--rcfile", "rc", "-ic", "echo body"], None,
     {"rc": "echo rcran\n"}, None),
    ("i_script_runs_rc", ["--rcfile", "rc", "-i", "s.sh"], None,
     {"rc": "echo rcran\n", "s.sh": "echo scriptbody\n"}, None),
    ("rc_alias_usable_from_ic", ["--rcfile", "rc", "-ic", "zz"], None,
     {"rc": "alias zz='echo ALIASED'\n"}, None),
    ("no_i_no_rc_for_c", ["--rcfile", "rc", "-c", "echo body"], None,
     {"rc": "echo rcran\n"}, None),
    ("ic_positionals", ["--norc", "-ic", "echo 0=$0 1=${1-none}", "a", "b"],
     None, None, None),
    ("i_script_positionals", ["--norc", "-i", "s.sh", "x"], None,
     {"s.sh": "echo 0=$0 1=$1\n"}, None),
    # --- interactive-family error policy (probes B6/P5/Q1/D5/P2) ---
    ("ic_unbound_aborts_status_1",
     ["--norc", "-ic", "set -u; echo $undef; echo after"], None, None,
     "unbound variable"),
    ("ic_multiline_discards_line_and_continues",
     ["--norc", "-ic", "set -u\necho $undef\necho after"], None, None, None),
    ("i_script_unbound_continues", ["--norc", "-i", "s.sh"], None,
     {"s.sh": "set -u\necho $undef\necho after\n"}, None),
    ("i_s_piped_unbound_continues", ["--norc", "-i", "-s"],
     "set -u\necho $undef\necho after\n", None, None),
    ("i_s_piped_errexit_aborts", ["--norc", "-i", "-s"],
     "set -e\nfalse\necho after\n", None, None),
    ("ic_errexit_aborts", ["--norc", "-ic", "set -e; false; echo after"],
     None, None, None),
    ("plain_c_unbound_control", ["--norc", "-c", "echo $undef; echo after", ],
     None, None, None),
    ("u_flag_plain_c_fatal", ["--norc", "-u", "-c", "echo $undef; echo after"],
     None, None, "unbound variable"),
    # --- history expansion boundaries (probes B8 + -i stream expansion) ---
    ("ic_string_never_bang_expands", ["--norc", "-ic", "echo A; echo !!"],
     None, None, None),
    ("i_s_piped_bang_expands", ["--norc", "-i", "-s"],
     "echo A\necho !!\n", None, None),
    ("plain_stdin_no_bang_expansion", ["--norc", "-s"],
     "echo A\necho !!\n", None, None),
    # --- history loading (probes H1-H3) ---
    ("i_s_loads_and_records_history", ["--norc", "-i", "-s"], "history\n",
     None, None),
    ("ic_does_not_load_history", ["--norc", "-ic", "history"], None,
     None, None),
    ("plain_stdin_no_history", ["--norc", "-s"], "history\n", None, None),
    # --- other transitions through the same path ---
    ("last_wins_x_then_plus_x", ["--norc", "-x", "+x", "-c", "echo hi"],
     None, None, None),
    ("o_pipefail_last_wins",
     ["--norc", "-o", "pipefail", "+o", "pipefail",
      "-c", "false | true; echo rc=$?"], None, None, None),
    ("plus_B_braceexpand_off", ["--norc", "+B", "-c", "echo {a,b}"],
     None, None, None),
    ("noexec_n", ["--norc", "-n", "-c", "echo hi"], None, None, None),
]

_HISTORY_ROWS = {"i_s_loads_and_records_history", "ic_does_not_load_history",
                 "plain_stdin_no_history"}


@pytest.mark.parametrize("row_id,args,stdin,files,psh_stderr_contains",
                         MATRIX, ids=[row[0] for row in MATRIX])
def test_matrix_row(row_id, args, stdin, files, psh_stderr_contains, tmp_path):
    hist = ("echo canary-one\necho canary-two\n"
            if row_id in _HISTORY_ROWS else None)
    psh, bash = run_both(args, stdin=stdin, files=files, tmp_path=tmp_path,
                         hist_content=hist)
    assert psh.returncode == bash.returncode, (
        f"exit codes diverge: psh={psh.returncode} bash={bash.returncode}\n"
        f"psh stderr: {psh.stderr!r}\nbash stderr: {bash.stderr!r}")
    assert psh.stdout == bash.stdout, (
        f"stdout diverges:\npsh : {psh.stdout!r}\nbash: {bash.stdout!r}")
    if psh_stderr_contains is not None:
        assert psh_stderr_contains in psh.stderr, psh.stderr


class TestBareOptionListings:
    """Bare trailing -o/+o print the listing (rc 0) and the shell proceeds.

    bash's table CONTENT differs from psh's (psh's set -o surface is a
    documented superset/subset), so these rows pin exit parity plus psh's
    own listing shape and the continue-afterwards behavior (probe E3b: bash
    prints the table, then reads stdin normally).
    """

    def test_bare_dash_o_lists_and_continues(self, tmp_path):
        psh, bash = run_both(["--norc", "-o"], stdin="echo after-table\n",
                             tmp_path=tmp_path)
        assert psh.returncode == bash.returncode == 0
        assert "errexit" in psh.stdout
        assert psh.stdout.endswith("after-table\n")
        assert bash.stdout.endswith("after-table\n")

    def test_bare_plus_o_lists_reusable_form(self, tmp_path):
        psh, bash = run_both(["--norc", "+o"], stdin="echo after-table\n",
                             tmp_path=tmp_path)
        assert psh.returncode == bash.returncode == 0
        assert "set +o errexit" in psh.stdout
        assert "set +o errexit" in bash.stdout
        assert psh.stdout.endswith("after-table\n")

    def test_o_with_next_arg_still_consumes_name(self, tmp_path):
        # `-o -c ...`: -c is consumed as the (invalid) option NAME (bash).
        psh, bash = run_both(["--norc", "-o", "-c", "echo hi"],
                             tmp_path=tmp_path)
        assert psh.returncode == bash.returncode == 2
        assert psh.stdout == bash.stdout == ""
        assert "invalid option name" in psh.stderr


class TestPshOnlyRows:
    """Rows bash cannot mirror (psh-specific surface)."""

    def test_dollar0_is_psh_for_stdin_mode(self, tmp_path):
        psh = _run([sys.executable, "-m", "psh", "--norc", "-s", "A"],
                   stdin="echo $0\n", cwd=str(tmp_path),
                   histfile=str(tmp_path / "hf"))
        assert psh.returncode == 0
        assert psh.stdout == "psh\n"

    def test_dash_V_prints_version(self, tmp_path):
        psh = _run([sys.executable, "-m", "psh", "-V"], stdin=None,
                   cwd=str(tmp_path), histfile=str(tmp_path / "hf"))
        assert psh.returncode == 0
        assert psh.stdout.startswith("Python Shell (psh) version ")

    def test_help_is_long_option_only(self, tmp_path):
        psh = _run([sys.executable, "-m", "psh", "--help"], stdin=None,
                   cwd=str(tmp_path), histfile=str(tmp_path / "hf"))
        assert psh.returncode == 0
        assert psh.stdout.startswith("Usage: psh")

    def test_parser_choice_visible_to_body(self, tmp_path):
        psh = _run([sys.executable, "-m", "psh", "--norc",
                    "--parser", "combinator", "-c", "parser-select"],
                   stdin=None, cwd=str(tmp_path),
                   histfile=str(tmp_path / "hf"))
        assert psh.returncode == 0
        assert any(ln.lstrip().startswith("*") and "combinator" in ln
                   for ln in psh.stdout.splitlines())
