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

**These seam cells are labelled psh-CONTRACT, not bash parity.** bash assigns
the stranded partial byte to the read that timed out; psh holds it on the
cursor, so the two shells legitimately split the same bytes at different points.
That was successor row **D-4B.2-s1**, and slot 4B.4 RULED it psh's permanent
contract: the dup and temp-frame gaps that made holding a byte unsafe are
closed, so a held byte can no longer reach another source or be lost, and the
divergence is now DOCUMENTED in
``docs/user_guide/17_differences_from_bash.md`` beside the CHARACTER MODEL
prose this fix PROTECTS ("a multibyte ``é`` arrives whole, not split across two
reads"). Each cell still asserts psh's value AND that bash's differs, so the
declared divergence cannot drift silently in either shell.

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


def _write(tmp_path, arm: str, name: str, data: bytes) -> str:
    p = tmp_path / f"{arm}.{name}"
    p.write_bytes(data)
    return str(p)


def _run_both(args_builder, tmp_path):
    """Run one cell under psh and bash; ``args_builder(arm)`` is called PER ARM.

    Per-arm construction is not cosmetic: a FIFO is a mutable OS object, and a
    producer or reader that outlives its arm can deliver bytes into the other
    arm's run. Sharing one between the two shells produced exactly that
    cross-arm leak in this slot's unit file. Read-only payload files could be
    shared safely, but they are built per-arm too so the rule has no exceptions
    to remember.
    """
    kwargs = dict(cwd=str(tmp_path), timeout=KILL_AFTER,
                  env={"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"})
    psh = run_psh(args_builder("psh"), **kwargs)
    bash = run_bash(args_builder("oracle"), **kwargs)
    assert is_comparable(bash), f"bash oracle unusable: {bash}"
    assert is_comparable(psh), (
        f"psh did not complete within {KILL_AFTER}s: {psh}")
    return _report(psh), _report(bash)


def _report(result) -> str:
    lines = [ln for ln in result.stdout.splitlines() if ln.startswith("rc=")]
    assert lines, f"no report line in {result.stdout!r} / {result.stderr!r}"
    return lines[-1]


def _control_script(payload: str) -> str:
    """CONTROL: mapfile alone, with no timed read, so nothing is ever stranded."""
    return (f"cat {payload} | {{ mapfile arr; "
            f"printf 'rc=0 a0len=%s nelem=%s a0bytes=' "
            f'"${{#arr[0]}}" "${{#arr[@]}}"; '
            f"printf '%s' \"${{arr[0]}}\" | od -An -tx1 | tr -d ' \\n'; "
            f"printf '\\n'; }}")


def _seam_script(tmp_path, arm: str, head: bytes, tail: bytes) -> str:
    """A timed read strands a partial character; mapfile then drains the rest.

    ``mapfile`` with no count is the only production caller of the bulk drain,
    so this is the one route by which the seam is reachable from shell syntax.
    The producer writes the head, holds past the deadline, then writes the tail
    and exits (EOF) so ``mapfile`` can finish. Bytes come from files via ``cat``
    — never from the shell's own ``printf``, whose octal escapes differ between
    the two shells.
    """
    h = _write(tmp_path, arm, "head.bin", b"a" + head)
    t = _write(tmp_path, arm, "tail.bin", tail + b"\n")
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
            lambda arm: ["-c", _seam_script(tmp_path, arm, head, tail)],
            tmp_path)

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
            "D-4B.2-s1 (timeout-partial hold-and-resume, RULED psh's contract "
            "in 4B.4): psh now "
            f"equals bash ({bash!r}). If that successor was ruled, update this "
            "pin, and re-check the user-guide text that documents it — "
            "it up; :596-598 documents only the char model this fix protects.")
        assert bash.startswith("rc=142 xlen=2 "), (
            f"bash oracle shape changed: {bash!r}")

    def test_without_a_timeout_both_shells_agree(self, tmp_path):
        """CONTROL: no timed read, so nothing is ever stranded at the seam."""
        def build(arm):
            payload = _write(tmp_path, arm, "whole.bin", b"a\xc3\xa9\n")
            return ["-c", _control_script(payload)]

        psh, bash = _run_both(build, tmp_path)
        assert psh == bash == "rc=0 a0len=3 nelem=1 a0bytes=61c3a90a"



class TestRiderEndToEndFromAScriptFile:
    """The LEDGER's `read -t X -N n` repro, run from a script FILE.

    ``exec 3<>fifo`` opens the FIFO read-write so a writer always exists and EOF
    never arrives — which is what makes the base behaviour an unbounded block
    rather than a short read at the producer's exit, and what the runner's
    process-group watchdog bounds.
    """

    def _script_file(self, tmp_path, arm: str, opts: str,
                     data: bytes = b"") -> str:
        # Per-arm fifo, feed and script: see _run_both for why a FIFO must never
        # be shared between the two arms.
        fifo = str(tmp_path / f"{arm}.fifo")
        if not os.path.exists(fifo):
            os.mkfifo(fifo)
        feed = (f"cat {_write(tmp_path, arm, 'feed.bin', data)} >&3\n"
                if data else "")
        body = (
            f"exec 3<>{fifo}\n"
            f"{feed}"
            f"read {opts} x <&3\n"
            "rc=$?\n"
            "printf 'rc=%s bytes=' \"$rc\"\n"
            "printf '%s' \"$x\" | od -An -tx1 | tr -d ' \\n'\n"
            "printf '\\n'\n")
        return _write(tmp_path, arm, "case.sh", body.encode())

    def test_exact_count_honors_the_deadline_with_no_input(self, tmp_path):
        psh, bash = _run_both(
            lambda arm: [self._script_file(tmp_path, arm, f"-t {TIMEOUT} -N 3")],
            tmp_path)
        assert psh == bash == "rc=142 bytes="

    def test_exact_count_honors_the_deadline_with_partial_input(self, tmp_path):
        psh, bash = _run_both(
            lambda arm: [self._script_file(tmp_path, arm,
                                           f"-t {TIMEOUT} -N 3", b"ab")],
            tmp_path)
        assert psh == bash == "rc=142 bytes=6162"
