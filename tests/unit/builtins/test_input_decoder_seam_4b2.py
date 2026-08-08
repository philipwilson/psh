"""The cursor/bulk decoder seam: one incremental decoder across the drain.

Slot 4B.2 / MEDIUM-2. ``InputCursor`` decodes the fd byte stream through ONE
incremental surrogateescape decoder, but ``read_all`` used to FINALIZE that
decoder with empty input and then decode the bulk tail with a FRESH one-shot
decode. A multibyte character split across that seam therefore came back as one
surrogate per byte (``'\\udcc3\\udca9'``) instead of the character (``'é'``).
The bytes still round-tripped — character IDENTITY was the broken half, which is
why a byte-level probe cannot see this defect at all (see
``tests/system/test_read_seam_end_to_end_4b2.py`` for the shell-level cells,
which use CHARACTER length because byte dumps are blind to it).

Structure of this file:

* ``TestSplitCharIdentityAcrossSeam`` — the defect. Every internal split point of
  a 2-, 3- and 4-byte character, drained by ``read_all``. RED before the fix.
* ``TestSeamControls*`` — three control classes that must NOT move: a stranded
  lead whose completion never arrives, a stranded lead followed by a
  NON-continuation byte, and genuinely malformed input. These discriminate
  "fed through the existing decoder" from "swallowed" or "policy changed".
* ``TestResumeRoutesArePshContract`` — the OTHER drain routes. These are green
  both before and after, but they are **psh-CONTRACT cells, not bash parity**:
  bash assigns a stranded partial byte to the timed-out read and moves on, while
  psh holds it for the next read. That divergence is successor row D-4B.2-s1
  (deferred to slot 4B.4, integrator ruling (c)). It is **documented NOWHERE in
  the user guide** — that ABSENCE is part of what s1 carries to 4B.4. The
  adjacent prose at ``docs/user_guide/17_differences_from_bash.md:596-598``
  documents the CHARACTER MODEL this fix PROTECTS ("a multibyte ``é`` arrives
  whole, not split across two reads"), not the timeout divergence.
* ``TestCursorStateCensus`` — the invariants the fix relies on, pinned so a
  later change cannot quietly invalidate them.

Only TIMEOUT and ERROR can strand a partial sequence: EOF flushes the decoder
(``input_reader.py`` ``_next_char_from_fd``), and the character loop never
returns mid-character, so a ``-N`` count boundary cannot split one. These cells
use a timeout as the SETUP STEP; the assertion is about decoding, not timing,
and nothing can race the deadline because the completing bytes are written only
after it has expired. The genuine deadline-behaviour cells live in
``test_read_exact_timeout_4b2.py`` and use >= 1s margins.
"""
import codecs
import os
import time
from typing import Optional

import pytest

from psh.builtins.input_reader import InputCursor, Outcome

# The timeout here is scaffolding, not the thing under test: it exists only to
# park a partial sequence in the decoder. Nothing is written until after it
# fires, so it cannot race anything.
SETUP_TIMEOUT = 0.25

E_ACUTE = 'é'      # C3 A9
EURO = '€'         # E2 82 AC
SMILE = '🙂'       # F0 9F 99 82

SPLIT_CASES = [
    pytest.param(ch, split, id=f"{name}-split{split}")
    for name, ch in (('e_acute', E_ACUTE), ('euro', EURO), ('smile', SMILE))
    for split in range(1, len(ch.encode('utf-8')))
]

SUFFIX = 'Z\n'     # trailing context: a merge-ORDER error would show up here


def _strand_then_drain(head: bytes, tail: bytes, route: str = 'read_all', *,
                       expect_pending: Optional[bytes]) -> str:
    """Park ``head``'s trailing partial sequence in the decoder, then drain.

    Writes ``head``, lets a timed read expire mid-sequence (leaving the decoder
    holding the incomplete bytes), writes ``tail``, closes the writer and drains
    through ``route``. Returns everything the cursor yielded, in order.

    ``expect_pending`` is the ANTI-VACUITY guard and is MANDATORY: it states the
    exact bytes the decoder must hold when the drain begins, or ``None`` when the
    head resolves to a surrogate immediately and the decoder stays clean
    (``\\xa9``, ``\\xff`` and ``\\xc0`` are invalid as LEAD bytes, so they emit at
    once instead of buffering — measured, not assumed). Asserting only that the
    read TIMED OUT would let a cell pass without ever reaching the seam: the
    timeout is guaranteed here, so a cell that stranded nothing would still go
    green, silently and forever. With this assertion such a cell FAILS.

    That guard is also why this module needs no ``serial`` marker. The timeout is
    a setup step nothing can race — the completing bytes are written only after
    it has expired — and any scheduler delay that prevented the intended
    stranding now trips this assertion instead of passing vacuously.
    """
    r, w = os.pipe()
    w_open = True
    try:
        if head:
            os.write(w, head)
        cursor = InputCursor(fd=r)
        first = cursor.read_record(delimiter='\n', include_delimiter=True,
                                   deadline=time.monotonic() + SETUP_TIMEOUT)
        assert first.outcome is Outcome.TIMEOUT, (
            f"setup did not strand a partial sequence: {first!r}")
        pending = (cursor._decoder.getstate()[0]
                   if cursor._decoder is not None else None)
        assert pending == expect_pending, (
            f"cell did not reach the seam in its intended state: the decoder "
            f"holds {pending!r}, expected {expect_pending!r}. A cell that "
            f"strands nothing exercises no seam and would pass vacuously.")
        if tail:
            os.write(w, tail)
        os.close(w)
        w_open = False

        if route == 'read_all':
            return first.data + cursor.read_all()
        out = [first.data]
        while True:
            if route == 'read_record':
                nxt = cursor.read_record(delimiter='\n', include_delimiter=True,
                                         deadline=time.monotonic() + 5.0)
            elif route == 'read_limited':
                nxt = cursor.read_limited(delimiter=None, max_chars=1,
                                          deadline=time.monotonic() + 5.0)
            else:
                raise AssertionError(f"unknown route {route!r}")
            out.append(nxt.data)
            if nxt.outcome is not Outcome.DATA:
                return ''.join(out)
    finally:
        os.close(r)
        if w_open:
            os.close(w)


def _assert_exact(got: str, want_text: str, want_bytes: bytes) -> None:
    """Assert BOTH halves of the slot's exit criterion for one cell."""
    assert got == want_text, (
        f"character identity lost: {got!r} != {want_text!r}")
    assert got.encode('utf-8', 'surrogateescape') == want_bytes, (
        f"byte round-trip lost: {got.encode('utf-8', 'surrogateescape')!r} "
        f"!= {want_bytes!r}")


class TestSplitCharIdentityAcrossSeam:
    """MEDIUM-2 itself: a valid character split across the drain seam.

    RED before the fix (6/6 lost character identity; 0/6 lost the bytes).
    """

    @pytest.mark.parametrize("ch,split", SPLIT_CASES)
    def test_split_character_survives_the_bulk_drain(self, ch, split):
        raw = ch.encode('utf-8')
        payload = raw + SUFFIX.encode('utf-8')
        got = _strand_then_drain(payload[:split], payload[split:],
                                 expect_pending=payload[:split])
        _assert_exact(got, ch + SUFFIX, payload)


class TestSeamControlsNoCompletion:
    """The completing bytes never arrive: the stranded lead must surrogate."""

    @pytest.mark.parametrize("ch,split", SPLIT_CASES)
    def test_stranded_lead_at_eof_round_trips(self, ch, split):
        raw = ch.encode('utf-8')
        got = _strand_then_drain(raw[:split], b'',
                                 expect_pending=raw[:split])
        _assert_exact(got, raw[:split].decode('utf-8', 'surrogateescape'),
                      raw[:split])


class TestSeamControlsNonContinuation:
    """The next byte is NOT a continuation, so the lead is genuinely malformed.

    This is the cell that discriminates "the tail went through the EXISTING
    decoder" from "the tail was swallowed into the pending sequence".
    """

    @pytest.mark.parametrize("ch,split", SPLIT_CASES)
    def test_non_continuation_after_stranded_lead(self, ch, split):
        raw = ch.encode('utf-8')
        payload = raw[:split] + SUFFIX.encode('utf-8')
        got = _strand_then_drain(payload[:split], payload[split:],
                                 expect_pending=payload[:split])
        _assert_exact(got, payload.decode('utf-8', 'surrogateescape'), payload)


class TestSeamControlsMalformed:
    """surrogateescape POLICY for malformed bytes is settled; it must not move."""

    # `pending` is MEASURED, not assumed: a byte that is invalid as a LEAD
    # (\xa9 continuation, \xff, \xc0) emits its surrogate at once and leaves the
    # decoder clean, while an incomplete-but-valid lead buffers.
    @pytest.mark.parametrize("payload,split,pending", [
        pytest.param(b'\xc3A' + SUFFIX.encode('utf-8'), 1, b'\xc3',
                     id="lone-lead-then-ascii"),
        pytest.param(b'\xa9' + SUFFIX.encode('utf-8'), 1, None,
                     id="orphan-continuation"),
        pytest.param(b'\xc3\xc3' + SUFFIX.encode('utf-8'), 1, b'\xc3',
                     id="two-leads"),
        pytest.param(b'\xf0\x9fA' + SUFFIX.encode('utf-8'), 2, b'\xf0\x9f',
                     id="truncated-4byte-then-ascii"),
        pytest.param(b'\xff' + SUFFIX.encode('utf-8'), 1, None, id="bare-ff"),
        pytest.param(b'\xc0\x80' + SUFFIX.encode('utf-8'), 1, None,
                     id="overlong-c0-80"),
    ])
    def test_malformed_bytes_round_trip_across_the_seam(self, payload, split,
                                                        pending):
        got = _strand_then_drain(payload[:split], payload[split:],
                                 expect_pending=pending)
        _assert_exact(got, payload.decode('utf-8', 'surrogateescape'), payload)


class TestResumeRoutesArePshContract:
    """The non-bulk drain routes resume a split character correctly.

    GREEN both before and after the fix — but these are **psh-CONTRACT** cells,
    NOT bash parity. bash assigns the stranded partial byte to the read that
    timed out and does not resume; psh holds it on the cursor for the next read.
    That divergence is successor row **D-4B.2-s1**, deferred to slot 4B.4 by
    integrator ruling (c). It is **UNDOCUMENTED**: no user-guide line describes
    it, and that absence travels with s1. What
    ``docs/user_guide/17_differences_from_bash.md:596-598`` documents is the
    adjacent CHARACTER MODEL ("a multibyte ``é`` arrives whole, not split across
    two reads") — the property this fix PROTECTS, not the timeout behaviour. If
    4B.4 rules the other way, these cells and that documentation gap move
    together.
    """

    @pytest.mark.parametrize("ch,split", SPLIT_CASES)
    def test_next_read_record_resumes_the_split_character(self, ch, split):
        raw = ch.encode('utf-8')
        payload = raw + SUFFIX.encode('utf-8')
        got = _strand_then_drain(payload[:split], payload[split:],
                                 route='read_record',
                                 expect_pending=payload[:split])
        _assert_exact(got, ch + SUFFIX, payload)

    @pytest.mark.parametrize("ch,split", SPLIT_CASES)
    def test_next_read_limited_resumes_the_split_character(self, ch, split):
        raw = ch.encode('utf-8')
        payload = raw + SUFFIX.encode('utf-8')
        got = _strand_then_drain(payload[:split], payload[split:],
                                 route='read_limited',
                                 expect_pending=payload[:split])
        _assert_exact(got, ch + SUFFIX, payload)


class TestCursorStateCensus:
    """The invariants the seam fix rests on."""

    def test_read_all_merge_order_is_decoded_then_fd(self):
        """Order pin: already-decoded chars come before the fd's remaining bytes.

        Renamed and narrowed in slot 4B.4, which REMOVED the ``_pushback``
        bytearray this cell used to place in the middle of the merge. That
        buffer was provably always empty — its only non-empty writer re-pushed
        the remainder of what it had just drained, and the seed was empty — so
        the three-way order was never reachable through the public API, which is
        why the old cell had to construct it directly. The two-way order that
        remains is the real contract.

        This cell keeps BOTH of its M8 roles unchanged: it BREAKS under
        ``seam-merge-order-scrambled`` (the merge is exactly what it asserts),
        and it STAYS GREEN under ``seam-fresh-decoder-reintroduced`` because the
        cursor's decoder is CLEAN here — with nothing buffered mid-sequence,
        "which decoder consumes the tail" cannot change the answer. That is
        precisely the property that arm needs from its discrimination row.
        """
        r, w = os.pipe()
        try:
            os.write(w, b'FD')
            os.close(w)
            cursor = InputCursor(fd=r)
            cursor._decoded.extend('DE')          # already-decoded characters
            assert cursor.read_all() == 'DEFD'
        finally:
            os.close(r)

    def test_read_all_leaves_the_decoder_clean(self):
        """After a drain the cursor is back to the ``_decoder is None`` state."""
        r, w = os.pipe()
        w_open = True
        try:
            os.write(w, '€'.encode('utf-8')[:2])
            cursor = InputCursor(fd=r)
            cursor.read_record(delimiter='\n', include_delimiter=True,
                               deadline=time.monotonic() + SETUP_TIMEOUT)
            assert cursor._decoder is not None
            os.write(w, '€'.encode('utf-8')[2:])
            os.close(w)
            w_open = False
            cursor.read_all()
            assert cursor._decoder is None
            assert not cursor._decoded
        finally:
            os.close(r)
            if w_open:
                os.close(w)

    def test_byte_and_char_paths_never_share_a_cursor_by_construction(self):
        """P2: the two paths cannot mix, because the consumers never share one.

        The byte path (``StdinInput``/``LazyFileInput``) builds its cursor
        directly at ``scripting/input_sources.py#_make_input_cursor``; the
        character path (``read``/``mapfile``) obtains one from
        ``io_redirect/input_cursor.py#InputCursorRegistry.cursor_for_fd``.
        The invariant therefore holds BY CONSTRUCTION, not by a runtime guard —
        this pin fails if a future change routes both through one factory.
        """
        import inspect

        from psh.io_redirect.input_cursor import InputCursorRegistry
        from psh.scripting import input_sources

        direct = inspect.getsource(input_sources._make_input_cursor)
        assert 'InputCursor(fd=fd)' in direct
        assert 'cursor_for_fd' not in direct, (
            "the byte path now goes through the registry: the 'never mixed' "
            "invariant no longer holds by construction and needs a guard")
        registry = inspect.getsource(InputCursorRegistry.cursor_for_fd)
        assert 'make_reader' in registry


class TestDecoderEquivalencePremise:
    """The premise the clean-decoder branch of the fix relies on.

    When the cursor has no pending state, feeding the tail through a fresh
    incremental decoder with ``final=True`` must be indistinguishable from the
    one-shot ``bytes.decode`` the code used before — otherwise the fix would
    change behaviour on the untouched common path.
    """

    def test_incremental_final_matches_one_shot(self):
        payloads = [
            b'', b'abc\n', '€'.encode('utf-8'), '🙂'.encode('utf-8'),
            b'\xc3A', b'\xa9', b'a\xffb', '€'.encode('utf-8')[:2],
            '🙂'.encode('utf-8')[:1], b'\x80\x80',
        ]
        differing = []
        for payload in payloads:
            decoder = codecs.getincrementaldecoder('utf-8')('surrogateescape')
            incremental = decoder.decode(payload, final=True)
            one_shot = payload.decode('utf-8', errors='surrogateescape')
            if incremental != one_shot:
                differing.append((payload, incremental, one_shot))
        assert not differing, f"incremental-final diverges from one-shot: {differing}"
