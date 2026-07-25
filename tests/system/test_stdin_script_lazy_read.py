"""A script delivered ON STDIN must be read lazily, sharing fd 0 with `read`.

Scripting appraisal 2026-07-07, finding #1 (HIGH). When psh's command source is
stdin — ``cmds | psh``, ``psh < file``, or ``psh -s`` — bash reads the script
LAZILY and leaves the unconsumed remainder of fd 0 readable, so a ``read`` /
``cat`` / ``mapfile`` inside the script consumes the SUBSEQUENT physical lines
as data. psh used to slurp all of fd 0 into an in-memory buffer up front,
draining it so every in-script stdin consumer saw immediate EOF (silent wrong
output).

These pin the fix DIFFERENTIALLY against live bash across all three stdin
invocation forms (pipe, seekable file, ``-s``), plus the byte model and the
controls that must stay correct (script-file and ``-c`` share the real pipe,
not a drained buffer). fd-level claims demand a real subprocess with raw-byte
pipes — an in-process text-layer probe is structurally blind to the fd sharing.

Every launch goes through the typed oracle runner
(``tests/harness/shell_oracle.py``), which spawns a real child and offers BOTH
kinds of fd 0 the subject needs: ``stdin_mode='pipe'`` (a real, NON-seekable
pipe) and ``stdin_mode='file'`` (a regular SEEKABLE file). The runner captures
with UTF-8 + ``surrogateescape``, so the raw-byte rows recover their exact bytes
with the inverse ``encode``.
"""

import sys
from pathlib import Path

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

REPO_ROOT = str(Path(__file__).resolve().parents[2])
PSH = [sys.executable, "-m", "psh"]
# LOUD resolution: a missing bash oracle is a harness failure, never a silent
# skip — every claim in this module is differential against live bash.
_ORACLE = resolve_bash()
BASH = _ORACLE.path
TIMEOUT = 20


def _run_case(argv, script: bytes, *, seekable: bool):
    """The typed runner result for *argv* with *script* on fd 0.

    ``seekable=True`` -> ``stdin_mode='file'`` (a regular SEEKABLE file);
    ``seekable=False`` -> ``stdin_mode='pipe'`` (a real non-seekable pipe).
    That distinction is the whole subject of this module.
    """
    mode = "file" if seekable else "pipe"
    argv = list(argv)
    if argv[:len(PSH)] == PSH:
        r = run_psh(argv[len(PSH):], stdin_data=script, stdin_mode=mode,
                    cwd=REPO_ROOT, timeout=TIMEOUT)
    else:
        assert argv[0] == BASH, argv
        r = run_bash(argv[1:], stdin_data=script, stdin_mode=mode,
                     cwd=REPO_ROOT, timeout=TIMEOUT)
    assert is_comparable(r), r
    return r


def _run(argv, script: bytes, *, seekable: bool):
    """Run argv with *script* on fd 0, as a pipe or a seekable file."""
    r = _run_case(argv, script, seekable=seekable)
    return r.returncode, r.stdout.encode("utf-8", "surrogateescape")


def _both(script: bytes, *, seekable=False, psh_args=(), bash_args=()):
    """Return (psh_rc, psh_out, bash_rc, bash_out) for the same stdin script."""
    prc, pout = _run(PSH + list(psh_args), script, seekable=seekable)
    brc, bout = _run([BASH] + list(bash_args), script, seekable=seekable)
    return prc, pout, brc, bout


# Each row: a script whose CORRECT (bash) behavior depends on an in-script
# stdin consumer eating the SUBSEQUENT script lines as data.
STDIN_SHARING_SCRIPTS = {
    "read_next_line": b"read a\nread b\necho a=[$a] b=[$b]\nX\nY\n",
    "cat_consumes_rest": b"echo START\ncat\necho END\n",
    "while_read_loop": b"while read line; do echo got:$line; done\n1\n2\n3\n",
    "read_then_cat": b"read a\necho a=$a\ncat\nD1\nD2\nD3\n",
    "mapfile_drains": b"mapfile -t arr\necho count=${#arr[@]}\nfirst\nsecond\n",
    "read_in_if": b"if read x; then echo got:$x; fi\nPAYLOAD\ntail\n",
    "interleave": b"echo A\nread x\necho x=$x\necho B\nMIDDLE\n",
    # The heredoc body is consumed from the SAME lazy stream, then `read`
    # must consume the line that follows the heredoc terminator.
    "heredoc_then_read": b"cat <<EOF\nbody\nEOF\nread x\necho x=$x\nAFTER\n",
}


# On a SEEKABLE fd 0, `read`, `read -d ""`, `cat`, and (on a pipe) `mapfile`
# all consume from the shared position in both shells — psh matches. The one
# exception is `mapfile` on a SEEKABLE fd: bash reads it from EOF (a bash quirk
# inconsistent with its OWN read/read-d/cat seekable handling and with its own
# mapfile-on-a-pipe), capturing nothing and letting the script continue. psh is
# internally consistent — mapfile shares the position like every other consumer,
# on seekable and pipe alike — so we deliberately DIVERGE from that lone quirk
# rather than special-case the mapfile builtin to seek to EOF. See
# test_seekable_mapfile_is_consistent below.
_SEEKABLE_MATCH = sorted(set(STDIN_SHARING_SCRIPTS) - {"mapfile_drains"})


class TestStdinReadSharing:
    @pytest.mark.parametrize("name", sorted(STDIN_SHARING_SCRIPTS))
    def test_pipe_matches_bash(self, name):
        script = STDIN_SHARING_SCRIPTS[name]
        prc, pout, brc, bout = _both(script)
        assert (prc, pout) == (brc, bout)

    @pytest.mark.parametrize("name", _SEEKABLE_MATCH)
    def test_seekable_matches_bash(self, name):
        script = STDIN_SHARING_SCRIPTS[name]
        prc, pout, brc, bout = _both(script, seekable=True)
        assert (prc, pout) == (brc, bout)

    def test_seekable_mapfile_is_consistent(self):
        """mapfile on a SEEKABLE fd 0 shares the position like read/cat (drains
        the remaining lines into the array), matching mapfile-on-a-pipe.

        bash instead reads mapfile from EOF on a seekable fd (empty array, the
        rest of the script runs) — a documented, deliberately-not-replicated
        bash quirk. Here mapfile captures the 3 trailing lines, so nothing is
        left to run and the shell exits 0 with no output.
        """
        prc, pout = _run(PSH, STDIN_SHARING_SCRIPTS["mapfile_drains"],
                         seekable=True)
        assert (prc, pout) == (0, b"")

    @pytest.mark.parametrize("name", ["read_next_line", "cat_consumes_rest",
                                      "while_read_loop"])
    def test_dash_s_matches_bash(self, name):
        script = STDIN_SHARING_SCRIPTS[name]
        prc, pout, brc, bout = _both(script, psh_args=["-s"], bash_args=["-s"])
        assert (prc, pout) == (brc, bout)

    def test_read_gets_the_next_physical_line_exactly(self):
        """Pin the exact consumed value, not just parity: `read a` eats the
        NEXT script line verbatim (bash: a=[read b])."""
        prc, pout = _run(PSH, STDIN_SHARING_SCRIPTS["read_next_line"],
                         seekable=False)
        assert b"a=[read b] b=[]\n" == pout


class TestStdinByteModel:
    def test_non_utf8_line_round_trips(self):
        """A raw non-UTF-8 byte in a stdin-script argument round-trips to
        stdout (surrogateescape), matching bash."""
        script = b"echo caf\xe9\n"
        prc, pout, brc, bout = _both(script)
        assert (prc, pout) == (brc, bout)
        assert pout == b"caf\xe9\n"

    def test_crlf_kept_on_stdin(self):
        """psh keeps the CR on the stdin path (bash does too — this is NOT the
        FileInput CRLF divergence)."""
        script = b"echo a\r\necho b\r\n"
        prc, pout, brc, bout = _both(script)
        assert (prc, pout) == (brc, bout)

    def test_binary_garbage_no_traceback(self):
        prc, pout = _run(PSH, b"\xff\xfe\n", seekable=False)
        r = _run_case(PSH, b"\xff\xfe\n", seekable=False)
        rstderr = r.stderr.encode("utf-8", "surrogateescape")
        assert b"Traceback" not in rstderr
        assert r.returncode == 127


class TestStdinControlsStayCorrect:
    """The script-FILE and -c paths already share the real fd; keep them so."""

    def test_script_file_reads_pipe_not_drained(self, tmp_path):
        """`psh script.sh` with a separate piped stdin: the script's `read`
        consumes the PIPE, matching bash."""
        script = tmp_path / "s.sh"
        script.write_text("read a\necho a=$a\ncat\n")
        piped = b"LINE1\nLINE2\nLINE3\n"
        p = _run_case(PSH + [str(script)], piped, seekable=False)
        b = _run_case([BASH, str(script)], piped, seekable=False)
        assert (p.returncode, p.stdout) == (b.returncode, b.stdout)

    def test_dash_c_reads_pipe(self):
        """`psh -c 'read a; echo $a; cat'` reads the separate piped stdin."""
        piped = b"FIRST\nrest of the data\n"
        cmd = "read a; echo a=$a; cat"
        p = _run_case(PSH + ["-c", cmd], piped, seekable=False)
        b = _run_case([BASH, "-c", cmd], piped, seekable=False)
        assert (p.returncode, p.stdout) == (b.returncode, b.stdout)

    def test_stdin_script_can_redirect_fd0_midway(self, tmp_path):
        """A stdin script that does `exec < file` reads its SUBSEQUENT commands
        from the new fd 0 (the file), abandoning the rest of the pipe — because
        the reader consumes fd 0 by NUMBER each line, not a cached descriptor.
        Matches bash exactly."""
        data = tmp_path / "data.txt"
        data.write_text("FROMFILE\nSECOND\n")
        script = f"echo before\nexec < {data}\nread x\necho got:$x\ncat\n".encode()
        prc, pout, brc, bout = _both(script)
        assert (prc, pout) == (brc, bout)


class TestStdinTrivialInputs:
    @pytest.mark.parametrize("script", [b"", b"\n\n\n", b"# comment only\n",
                                        b"echo hi", b"echo hi\n"])
    def test_trivial_matches_bash(self, script):
        prc, pout, brc, bout = _both(script)
        assert (prc, pout) == (brc, bout)
