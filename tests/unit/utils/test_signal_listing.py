"""Unit tests for the signal name<->number listing helpers.

Pins the real-time-signal naming used by `kill -l`/`trap -l` (R13 nightly
fix): Python's signal.Signals only exposes SIGRTMIN/SIGRTMAX as enum members,
so psh must synthesise the intermediate RT signal names itself to match bash's
`kill -l` on Linux. The naming rule is verified here platform-independently
(it is pure arithmetic over rtmin/rtmax), so it stays pinned even on macOS CI
where there are no real-time signals.
"""

import signal

import pytest

from psh.utils.signal_utils import (
    SIGNAL_NUMBER_TO_NAME,
    _rt_signal_name,
    list_all_signals,
    signal_name_to_number,
)


class TestRealtimeSignalNaming:
    """bash's SIGRTMIN+n / SIGRTMAX-n convention (probed on bash 5.2/Linux,
    where SIGRTMIN=34, SIGRTMAX=64)."""

    # The full bash 5.2 naming of the Linux RT range, number -> bare name.
    LINUX_EXPECTED = {
        34: "RTMIN",
        **{34 + n: f"RTMIN+{n}" for n in range(1, 16)},   # 35..49
        **{64 - n: f"RTMAX-{n}" for n in range(1, 15)},   # 50..63
        64: "RTMAX",
    }

    def test_endpoints(self):
        assert _rt_signal_name(34, 34, 64) == "RTMIN"
        assert _rt_signal_name(64, 34, 64) == "RTMAX"

    def test_low_half_uses_rtmin_plus(self):
        assert _rt_signal_name(35, 34, 64) == "RTMIN+1"
        assert _rt_signal_name(49, 34, 64) == "RTMIN+15"  # midpoint tie -> RTMIN side

    def test_high_half_uses_rtmax_minus(self):
        assert _rt_signal_name(50, 34, 64) == "RTMAX-14"
        assert _rt_signal_name(63, 34, 64) == "RTMAX-1"

    def test_full_linux_range_matches_bash(self):
        got = {n: _rt_signal_name(n, 34, 64) for n in range(34, 65)}
        assert got == self.LINUX_EXPECTED


class TestSignalListingTable:
    """The live mapping enumerates the platform's real-time signals (Linux)."""

    @pytest.mark.skipif(not hasattr(signal, "SIGRTMIN"),
                        reason="no real-time signals on this platform (macOS/BSD)")
    def test_rt_range_is_fully_populated(self):
        rtmin = int(signal.SIGRTMIN)
        rtmax = int(signal.SIGRTMAX)
        # Every number in [rtmin, rtmax] has a name, not just the two endpoints.
        for num in range(rtmin, rtmax + 1):
            assert num in SIGNAL_NUMBER_TO_NAME
        # An intermediate RT signal is present and round-trips by name.
        assert SIGNAL_NUMBER_TO_NAME[rtmin + 1] == "RTMIN+1"
        assert signal_name_to_number("SIGRTMIN+1") == rtmin + 1
        # The listing renders it.
        assert "SIGRTMIN+1" in list_all_signals()

    def test_listing_is_nonempty_and_well_formed(self):
        out = list_all_signals()
        assert out.endswith("\n")
        assert " 1) SIGHUP" in out
