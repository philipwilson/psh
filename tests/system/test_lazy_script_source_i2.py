"""Lazy SCRIPT_FILE reading, bash-compared (campaign I2, #20 H14).

A script-file argument is read ON DEMAND (block-buffered over an owned high-
CLOEXEC descriptor) rather than slurped to EOF before line one:

* a script that APPENDS to itself sees the appended lines (RED on the eager
  base — psh never saw them);
* a self-TRUNCATE / self-REWRITE of already-buffered bytes is invisible in BOTH
  shells (parity control — bash block-buffers too);
* /dev/stdin as a script arg behaves like bash (over-read as a file arg);
* memory is bounded independent of file size (the reader buffers one block, not
  the whole file).

The INVARIANT pinned is bash's: consumed bytes are never re-read; appends past
the read frontier are seen. The block SIZE (which mid-buffer edits are
invisible) is a documented deliberate loss.
"""
import os
import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _run(shell_argv, script_text, tmp_path, stdin=None, name="s.sh"):
    p = tmp_path / name
    p.write_text(script_text)
    return subprocess.run(shell_argv + [str(p)], cwd=tmp_path,
                          input=stdin, capture_output=True, text=True)


def _both(script_text, tmp_path, stdin=None):
    """(psh, bash) results on a FRESH copy of the script each (self-modifying
    scripts mutate the file, so bash and psh must not share it)."""
    psh = _run([sys.executable, "-m", "psh"], script_text, tmp_path / "psh",
               stdin=stdin)
    bash = _run([BASH], script_text, tmp_path / "bash", stdin=stdin)
    return psh, bash


def _mk(tmp_path):
    (tmp_path / "psh").mkdir()
    (tmp_path / "bash").mkdir()


def test_small_append_runs_appended_line(tmp_path):
    # RED on the eager base: psh printed one,three (never the appended two).
    _mk(tmp_path)
    psh, bash = _both('echo one\necho "echo two" >> "$0"\necho three\n', tmp_path)
    assert psh.stdout == bash.stdout == "one\nthree\ntwo\n"
    assert psh.returncode == bash.returncode == 0


def test_big_append_past_gap(tmp_path):
    # RED on the eager base. Append at line 2, seen after ~3000 buffered lines.
    _mk(tmp_path)
    script = ('echo START\necho "echo APPENDED" >> "$0"\n'
              + ": pad\n" * 3000 + 'echo END_ORIG\n')
    psh, bash = _both(script, tmp_path)
    assert psh.stdout == bash.stdout == "START\nEND_ORIG\nAPPENDED\n"


def test_truncate_self_is_invisible_parity(tmp_path):
    # Control: a self-truncate of already-buffered bytes is invisible in BOTH
    # shells (block-buffered) — B,C still run from the buffer.
    _mk(tmp_path)
    psh, bash = _both('echo A\n: > "$0"\necho B\necho C\n', tmp_path)
    assert psh.stdout == bash.stdout == "A\nB\nC\n"


def test_rewrite_ahead_is_invisible_parity(tmp_path):
    # Control: rewriting the whole file before later lines run does not change
    # what runs (the original bytes are already buffered) — both shells agree.
    _mk(tmp_path)
    psh, bash = _both(
        'echo L1\nprintf "echo L2\\necho REPLACED\\n" > "$0"\necho L3_original\n',
        tmp_path)
    assert psh.stdout == bash.stdout == "L1\nL3_original\n"


def test_dev_stdin_as_script_arg(tmp_path):
    # /dev/stdin as a file argument: bash over-reads it as a file (matching the
    # block-buffered reader), so an in-script read gets nothing after the
    # script drains — psh agrees.
    _mk(tmp_path)
    body = "echo scr1\nread x\necho \"got=[$x]\"\necho scr3\n"
    psh = subprocess.run([sys.executable, "-m", "psh", "/dev/stdin"],
                         cwd=tmp_path, input=body, capture_output=True, text=True)
    bash = subprocess.run([BASH, "/dev/stdin"], cwd=tmp_path, input=body,
                          capture_output=True, text=True)
    assert psh.stdout == bash.stdout
    assert psh.returncode == bash.returncode


def test_in_script_read_uses_stdin_not_script(tmp_path):
    # A FILE script's descriptor is separate from fd 0, so an in-script `read`
    # consumes STDIN, not the following script lines (bash-parity, D4).
    _mk(tmp_path)
    script = 'echo scriptline\nread x\necho "got=[$x]"\necho done\n'
    psh = _run([sys.executable, "-m", "psh"], script, tmp_path / "psh",
               stdin="from_stdin\nMORE\n")
    bash = _run([BASH], script, tmp_path / "bash", stdin="from_stdin\nMORE\n")
    assert psh.stdout == bash.stdout == "scriptline\ngot=[from_stdin]\ndone\n"


def _peak_rss_bytes(root, script_path):
    """Run psh(script) in a child and report ITS peak RSS (bytes)."""
    code = (
        "import resource,subprocess,os,sys;"
        f"subprocess.run([sys.executable,'-m','psh',{str(script_path)!r}],"
        f"capture_output=True,env=dict(os.environ,PYTHONPATH={root!r}));"
        "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, env=dict(os.environ, PYTHONPATH=root))
    return int(r.stdout.strip())


def test_memory_bounded_independent_of_file_size(tmp_path):
    # Both scripts exit on line 1, so the RSS DELTA is purely the reader's
    # buffering. An eager reader slurps the whole file (delta ~= several x the
    # file); the lazy reader touches one block (delta ~= 0). Assert the delta is
    # far under the file size — robust across platforms (relative, not a raw
    # RSS threshold).
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    tiny = tmp_path / "tiny.sh"
    tiny.write_text("exit 0\n")
    big = tmp_path / "big.sh"
    with open(big, "w") as f:
        f.write("exit 0\n")
        for i in range(400000):
            f.write(f": filler line {i} padded to roughly sixty-four bytes ok!\n")
    file_mb = os.path.getsize(big) / 1e6
    assert file_mb > 20  # a real large file
    tiny_rss = _peak_rss_bytes(root, tiny)
    big_rss = _peak_rss_bytes(root, big)
    delta_mb = (big_rss - tiny_rss) / 1e6
    assert delta_mb < file_mb / 4, (
        f"reader is not bounded: {file_mb:.0f} MB script added {delta_mb:.0f} "
        f"MB RSS (eager would add several x the file size)")
