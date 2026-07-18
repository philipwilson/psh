"""NUL / invalid-byte channel-equivalence matrix (campaign F3, medium 5).

The policy is decided ONCE in ``psh/scripting/program_source.py``; this
matrix pins it per channel against the bash 5.2 oracle. Ground truth and
red-on-base evidence: tmp/boundary-ledgers/F3-probes/ (base batteries A1-A14
at SHA 11e6661d), cross-checked against the bash 5.2 sources
(builtins/evalfile.c, general.c check_binary_file, shell.c).

The facts a future reader will not believe without the transcripts:

* STREAM channels (script-file argument, stdin script) DELETE every NUL:
  ``e\\0cho hi`` runs ``echo hi``; ``magic\\0\\0\\0tail`` is ``magictail``.
* STRING-READ channels (source/., rc) run bash's exact ``_evalfile`` loop:
  an isolated NUL is deleted, but the second NUL of an ADJACENT PAIR
  survives unexamined and truncates the whole rest of the FILE at parse
  time (``echo A\\0B`` prints ``AB``; ``echo A\\0\\0B\\necho C`` runs only
  ``echo A``).
* ``source`` refuses a file only after MORE THAN 256 deleted NULs
  (``cannot execute binary file``, 126). Content never matters: bash 5.2
  happily sources a file starting with the ELF magic. The rc channel has
  NO limit at all.
* The content sniff (ELF magic; ``#!`` first line makes a NUL anywhere in
  the sample binary; otherwise NUL before the first newline; sample = first
  80 bytes) applies ONLY to the script-invocation channel and its analysis
  twin (``--validate`` agrees with ``bash -n``).
* ``-c`` is an N/A channel for NUL: execve forbids NUL bytes in argv, so
  there is no program text a NUL could reach through it. In-process command
  text (eval/run_command) comes from shell values, which are NUL-free.
  Invalid UTF-8 (0xFF) is N/A as a policy question everywhere: every
  channel decodes surrogateescape, and the A3 rows pin the round-trip.
"""
import sys
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, run_shell_case, try_resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
_ORACLE = try_resolve_bash()

pytestmark = pytest.mark.skipif(_ORACLE is None, reason="no bash oracle")

NUL_AFTER = b"echo one\ne\x00cho two\n"
NUL_BEFORE = b"e\x00cho one\necho two\n"
FF_AFTER = b"echo one\necho t\xffwo\n"
DBL_NUL = b"echo A\x00\x00B\necho C\n"
FAT_SMALL = b"\xca\xfe\xba\xbe" + b"\x00" * 40 + b"fat-noise"
FAT_BIG = FAT_SMALL + b"\x00" * 200000  # >256 deleted NULs
ELF_NL = b"\x7fELF\necho hi\n"
SHEBANG_NUL = b"#!/bin/sh\necho a\x00b\n"
SHEBANG_NUL_PAST80 = b"#!/bin/sh\n" + b"# " + b"x" * 75 + b"\necho o\x00k\n"
WINDOW_EDGE = b"echo " + b"A" * 100 + b"\x00hi\necho ok\n"


def _run(argv, *, stdin, cwd, shell_tag):
    # Per-shell HISTFILE, always: an interactive-family bash writes its
    # session back to $HISTFILE on exit — without this, an -i row would
    # append to the developer's real ~/.bash_history (RESUME standing
    # lesson; psh runs first in run_both for the same reason).
    extra = {"HISTFILE": f"{cwd}/hist-{shell_tag}"}
    if argv[0] == sys.executable:
        extra["PYTHONPATH"] = str(REPO_ROOT)
    result = run_shell_case(argv, stdin_data=stdin,
                            env=hermetic_shell_env(extra), cwd=cwd, timeout=30)
    assert isinstance(result, Completed), result
    return result


def run_both(args, *, stdin=None, files=None, tmp_path):
    for rel, content in (files or {}).items():
        (tmp_path / rel).write_bytes(content)
    psh = _run([sys.executable, "-m", "psh", *args], stdin=stdin,
               cwd=str(tmp_path), shell_tag="psh")
    bash = _run([_ORACLE.path, *args], stdin=stdin, cwd=str(tmp_path),
                shell_tag="bash")
    return psh, bash


# One row: (id, args, stdin, files, psh_stderr_contains).
# args may reference files by relative name (cwd = tmp_path).
MATRIX = [
    # --- A1: NUL after the first newline is never a refusal, any channel ---
    ("nul_after_script", ["--norc", "f.sh"], None, {"f.sh": NUL_AFTER}, None),
    ("nul_after_stdin", ["--norc"], NUL_AFTER, None, None),
    ("nul_after_source", ["--norc", "-c", ". ./f.sh; echo rc=$?"], None,
     {"f.sh": NUL_AFTER}, None),
    ("nul_after_rc", ["--rcfile", "rc", "-i", "-s"], b"echo body\n",
     {"rc": NUL_AFTER}, None),
    # --- A2: NUL before the first newline: sniff on the script channel
    #     ONLY (126); stdin/source/rc discard and run ---
    ("nul_before_script_126", ["--norc", "f.sh"], None,
     {"f.sh": NUL_BEFORE}, "cannot execute binary file"),
    ("nul_before_stdin_runs", ["--norc"], NUL_BEFORE, None, None),
    ("nul_before_source_runs", ["--norc", "-c", ". ./f.sh; echo rc=$?"], None,
     {"f.sh": NUL_BEFORE}, None),
    ("nul_before_rc_runs", ["--rcfile", "rc", "-i", "-s"], b"echo body\n",
     {"rc": NUL_BEFORE}, None),
    # --- A3: invalid UTF-8 round-trips on every channel (surrogateescape) ---
    ("ff_script", ["--norc", "f.sh"], None, {"f.sh": FF_AFTER}, None),
    ("ff_stdin", ["--norc"], FF_AFTER, None, None),
    ("ff_source", ["--norc", "-c", ". ./f.sh; echo rc=$?"], None,
     {"f.sh": FF_AFTER}, None),
    ("ff_rc", ["--rcfile", "rc", "-i", "-s"], b"echo body\n",
     {"rc": FF_AFTER}, None),
    # --- evalfile pair-survivor semantics (string-read channels) vs
    #     delete-all (stream channels) ---
    ("single_nul_source_joins",
     ["--norc", "-c", ". ./f; echo rc=$?"], None,
     {"f": b"echo A\x00B\n"}, None),
    ("double_nul_source_truncates_file",
     ["--norc", "-c", ". ./f; echo rc=$?"], None, {"f": DBL_NUL}, None),
    ("double_nul_stdin_deletes_all", ["--norc"], DBL_NUL, None, None),
    ("double_nul_rc_truncates", ["--rcfile", "rc", "-i", "-s"],
     b"echo body\n", {"rc": DBL_NUL}, None),
    ("nul_run_source_word_split",
     ["--norc", "-c", ". ./f; echo rc=$?"], None,
     {"f": b"echo start\nmagic\x00\x00\x00tail\n"}, None),
    ("nul_run_stdin_joins_word", ["--norc"],
     b"echo start\nmagic\x00\x00\x00tail\n", None, None),
    ("leading_nul_pair_source_empty",
     ["--norc", "-c", ". ./f; echo rc=$?"], None,
     {"f": b"\x00\x00echo hi\n"}, None),
    # --- source binary rule: >256 deleted NULs, never content ---
    ("source_small_fat_runs_127",
     ["--norc", "-c", ". ./f.bin; echo rc=$?"], None,
     {"f.bin": FAT_SMALL}, None),
    ("source_big_fat_refused_126",
     ["--norc", "-c", ". ./f.bin; echo rc=$?"], None,
     {"f.bin": FAT_BIG}, "cannot execute binary file"),
    ("rc_big_fat_no_limit", ["--rcfile", "rc", "-i", "-s"], b"echo body\n",
     {"rc": FAT_BIG}, None),
    # --- script-channel sniff details (check_binary_file, 80-byte window) ---
    ("script_elf_magic_with_newline_126", ["--norc", "f"], None,
     {"f": ELF_NL}, "cannot execute binary file"),
    ("source_elf_magic_no_sniff",
     ["--norc", "-c", ". ./f; echo rc=$?"], None, {"f": ELF_NL}, None),
    ("script_shebang_nul_in_sample_126", ["--norc", "f"], None,
     {"f": SHEBANG_NUL}, "cannot execute binary file"),
    ("script_shebang_nul_past_window_runs", ["--norc", "f"], None,
     {"f": SHEBANG_NUL_PAST80}, None),
    ("script_nul_outside_80_window_runs", ["--norc", "f"], None,
     {"f": WINDOW_EDGE}, None),
]


@pytest.mark.parametrize("row_id,args,stdin,files,psh_stderr_contains",
                         MATRIX, ids=[row[0] for row in MATRIX])
def test_nul_matrix_row(row_id, args, stdin, files, psh_stderr_contains,
                        tmp_path):
    psh, bash = run_both(args, stdin=stdin, files=files, tmp_path=tmp_path)
    assert psh.returncode == bash.returncode, (
        f"exit codes diverge: psh={psh.returncode} bash={bash.returncode}\n"
        f"psh stderr: {psh.stderr!r}\nbash stderr: {bash.stderr!r}")
    assert psh.stdout == bash.stdout, (
        f"stdout diverges:\npsh : {psh.stdout!r}\nbash: {bash.stdout!r}")
    if psh_stderr_contains is not None:
        assert psh_stderr_contains in psh.stderr, psh.stderr


class TestAnalysisChannelParity:
    """--validate agrees with bash -n on the script channel's byte policy.

    psh's --validate OUTPUT is its own (a summary line; bash -n is silent),
    so these rows pin exit-status parity and psh-side shape — the F3 rule
    is that analysis sees the SAME normalized text execution would run.
    """

    def test_validate_nul_after_newline_ok(self, tmp_path):
        (tmp_path / "f.sh").write_bytes(NUL_AFTER)
        psh = _run([sys.executable, "-m", "psh", "--validate", "f.sh"],
                   stdin=None, cwd=str(tmp_path), shell_tag="psh")
        bash = _run([_ORACLE.path, "-n", "f.sh"], stdin=None,
                    cwd=str(tmp_path), shell_tag="bash")
        assert psh.returncode == bash.returncode == 0
        assert "No issues found" in psh.stdout  # psh's own summary format

    def test_validate_binary_sniff_matches_bash_n(self, tmp_path):
        (tmp_path / "f.sh").write_bytes(NUL_BEFORE)
        psh = _run([sys.executable, "-m", "psh", "--validate", "f.sh"],
                   stdin=None, cwd=str(tmp_path), shell_tag="psh")
        bash = _run([_ORACLE.path, "-n", "f.sh"], stdin=None,
                    cwd=str(tmp_path), shell_tag="bash")
        assert psh.returncode == bash.returncode == 126
        assert "cannot execute binary file" in psh.stderr

    def test_validate_stdin_strips_nuls(self, tmp_path):
        # Analysis of stdin applies the same stream NUL policy execution
        # would: the NUL-carrying word does not corrupt the parse.
        psh = _run([sys.executable, "-m", "psh", "--validate"],
                   stdin=b"echo o\x00k\n", cwd=str(tmp_path), shell_tag="psh")
        assert psh.returncode == 0
        assert "No issues found" in psh.stdout
