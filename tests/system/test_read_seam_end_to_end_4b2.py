"""End-to-end shell-level legs for the decoder seam and the ``-N``/``-t`` rider.

Slot 4B.2. These are the LEDGER's named repro shapes, driven through a real
shell rather than the cursor API.

**Why these cells measure CHARACTER length and not bytes.** The seam defect
preserved the byte round-trip — ``'\\udcc3\\udca9'`` re-encodes to exactly
``c3 a9`` — so a byte dump of the drained text is IDENTICAL before and after the
fix and cannot see the defect at all. What changes is how many CHARACTERS those
bytes decode to: a 2-, 3- or 4-byte character came back as 2, 3 or 4 surrogates
instead of 1. ``${#arr[0]}`` is therefore the discriminating observable, and the
byte column is carried alongside only to show it does NOT move.

**These seam cells are labelled psh-CONTRACT, not bash parity** (integrator
ruling (c)). bash assigns the stranded partial byte to the read that timed out;
psh holds it on the cursor, so the two shells legitimately split the same bytes
at different points. That divergence is successor row **D-4B.2-s1**, deferred to
slot 4B.4, and is the behaviour documented at
``docs/user_guide/17_differences_from_bash.md:597``. Each cell asserts psh's
value AND that bash's differs, so it fails loudly when 4B.4 rules — at which
point this file and that doc line move together.

The rider legs run psh from a SCRIPT FILE rather than ``-c``: a ``-c``-only pin
suite is mode-blind, and this slot's defect lives in a builtin that a script
reaches by a different input path.
"""
import os

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

pytestmark = pytest.mark.serial  # real deadlines and FIFOs

TIMEOUT = 1.0
LATE = 2.0           # 2x the deadline: when the completing bytes arrive
KILL_AFTER = 8.0     # the runner's watchdog: 8x the deadline

# é, €, 🙂 split so the timed read strands an incomplete sequence, plus the
# surrogate-per-byte count the seam produced before the fix.
SEAM_CASES = [
    pytest.param(b"\xc3", b"\xa9", 3, id="e_acute-2byte"),
    pytest.param(b"\xe2\x82", b"\xac", 4, id="euro-3byte"),
    pytest.param(b"\xf0\x9f\x99", b"\x82", 5, id="smile-4byte"),
]


def _write(tmp_path, name: str, data: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _run_both(args_builder, tmp_path):
    kwargs = dict(cwd=str(tmp_path), timeout=KILL_AFTER,
                  env={"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"})
    psh = run_psh(args_builder(), **kwargs)
    bash = run_bash(args_builder(), **kwargs)
    assert is_comparable(bash), f"bash oracle unusable: {bash}"
    assert is_comparable(psh), (
        f"psh did not complete within {KILL_AFTER}s: {psh}")
    return _report(psh), _report(bash)


def _report(result) -> str:
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("rc=")]
    assert lines, f"no report line in {result.stdout!r} / {result.stderr!r}"
    return lines[-1]


def _seam_script(tmp_path, head: bytes, tail: bytes) -> str:
    """A timed read strands a partial character; mapfile then drains the rest.

    ``mapfile`` with no count is the only production caller of the bulk drain,
    so this is the one route by which the seam is reachable from shell syntax.
    The producer writes the head, holds past the deadline, then writes the tail
    and exits (EOF) so ``mapfile`` can finish. Bytes come from files via ``cat``
    — never from the shell's own ``printf``, whose octal escapes differ between
    the two shells.
    """
    h = _write(tmp_path, "head.bin", b"a" + head)
    t = _write(tmp_path, "tail.bin", tail + b"\n")
    return (
        f"{{ cat {h}; sleep {LATE}; cat {t}; }} | "
        f"{{ read -t {TIMEOUT} x; rc=$?; mapfile arr; "
        f"printf 'rc=%s xlen=%s a0len=%s nelem=%s a0bytes=' "
        f'"$rc" "${{#x}}" "${{#arr[0]}}" "${{#arr[@]}}"; '
        f"printf '%s' \"${{arr[0]}}\" | od -An -tx1 | tr -d ' \\n'; "
        f"printf '\\n'; }}")


class TestSeamEndToEndCharacterIdentity:
    """RED on base: the drained element decodes to one surrogate per byte."""

    @pytest.mark.parametrize("head,tail,surrogates_on_base", SEAM_CASES)
    def test_split_character_keeps_its_identity_through_mapfile(
            self, tmp_path, head, tail, surrogates_on_base):
        psh, bash = _run_both(
            lambda: ["-c", _seam_script(tmp_path, head, tail)], tmp_path)

        # The whole character, plus its newline: two characters, not one per
        # stranded byte. (surrogates_on_base is what this cell reported before
        # the fix: 3, 4 and 5 respectively.)
        assert surrogates_on_base > 2  # the parameter documents the base shape
        expected_bytes = (head + tail + b"\n").hex()
        assert psh == (f"rc=142 xlen=1 a0len=2 nelem=1 "
                       f"a0bytes={expected_bytes}"), (
            f"seam not fixed or psh contract moved: {psh!r}")

        # D-4B.2-s1: bash split the same bytes at a different point (it assigned
        # the stranded byte to x). Declared divergence — assert it is still real.
        assert psh != bash, (
            "D-4B.2-s1 (timeout-partial assignment, deferred to 4B.4): psh now "
            f"equals bash ({bash!r}). If that successor was ruled, update this "
            "pin and docs/user_guide/17_differences_from_bash.md:597 together.")
        assert bash.startswith("rc=142 xlen=2 "), (
            f"bash oracle shape changed: {bash!r}")

    def test_without_a_timeout_both_shells_agree(self, tmp_path):
        """CONTROL: no timed read, so nothing is ever stranded at the seam."""
        payload = _write(tmp_path, "whole.bin", b"a\xc3\xa9\n")
        script = (
            f"cat {payload} | {{ mapfile arr; "
            f"printf 'rc=0 a0len=%s nelem=%s a0bytes=' "
            f'"${{#arr[0]}}" "${{#arr[@]}}"; '
            f"printf '%s' \"${{arr[0]}}\" | od -An -tx1 | tr -d ' \\n'; "
            f"printf '\\n'; }}")
        psh, bash = _run_both(lambda: ["-c", script], tmp_path)
        assert psh == bash == "rc=0 a0len=3 nelem=1 a0bytes=61c3a90a"


class TestRiderEndToEndFromAScriptFile:
    """The LEDGER's `read -t X -N n` repro, run from a script FILE.

    ``exec 3<>fifo`` opens the FIFO read-write so a writer always exists and EOF
    never arrives — which is what makes the base behaviour an unbounded block
    rather than a short read at the producer's exit, and what the runner's
    process-group watchdog bounds.
    """

    def _script_file(self, tmp_path, opts: str, data: bytes = b"") -> str:
        fifo = str(tmp_path / "fifo")
        if not os.path.exists(fifo):
            os.mkfifo(fifo)
        feed = f"cat {_write(tmp_path, 'feed.bin', data)} >&3\n" if data else ""
        body = (
            f"exec 3<>{fifo}\n"
            f"{feed}"
            f"read {opts} x <&3\n"
            "rc=$?\n"
            "printf 'rc=%s bytes=' \"$rc\"\n"
            "printf '%s' \"$x\" | od -An -tx1 | tr -d ' \\n'\n"
            "printf '\\n'\n")
        return _write(tmp_path, "case.sh", body.encode())

    def test_exact_count_honors_the_deadline_with_no_input(self, tmp_path):
        path = self._script_file(tmp_path, f"-t {TIMEOUT} -N 3")
        psh, bash = _run_both(lambda: [path], tmp_path)
        assert psh == bash == "rc=142 bytes="

    def test_exact_count_honors_the_deadline_with_partial_input(self, tmp_path):
        path = self._script_file(tmp_path, f"-t {TIMEOUT} -N 3", b"ab")
        psh, bash = _run_both(lambda: [path], tmp_path)
        assert psh == bash == "rc=142 bytes=6162"
