"""Conformance: printf float formatting — %a/%A precision + '#' flag (5R rider).

Every cell here is libc-STABLE: glibc (Linux nightly) and macOS libc
(local gate) agree on it, so the suite passes against live bash on both
hosts.  Deliberately excluded as platform-divergent:

- rounding TIES (macOS truncates exact halves; pinned engine-direct in
  tests/unit/utils/test_printf_formatter.py::TestHexFloatPrecisionAltForm)
- subnormals (macOS renormalizes to 0x1p-1074 + ERANGE warning; glibc
  keeps the denormalized 0x0...p-1022 form psh implements — the
  DECLARED divergence recorded in the 5R LEDGER row)

Probe provenance: tmp/5r-probes/ battery vs bash 5.2.26, 2026-08-09.
"""

from conformance_framework import ConformanceTest


class TestPrintfHexFloatPrecision(ConformanceTest):
    """%a/%A precision: mantissa rounded/padded to N hex digits."""

    def test_precision_rounds(self):
        self.assert_identical_behavior("printf '%.2a\\n' 3.14")
        self.assert_identical_behavior("printf '%.1a\\n' 3.14")
        self.assert_identical_behavior("printf '%.3a\\n' 3.14")
        self.assert_identical_behavior("printf '%.0a\\n' 3.14")

    def test_precision_round_up_and_carry(self):
        self.assert_identical_behavior("printf '%.2a\\n' 0.1")
        self.assert_identical_behavior("printf '%.4a\\n' 0.1")
        self.assert_identical_behavior("printf '%.0a\\n' 1.9999999999")

    def test_precision_zero_pads(self):
        self.assert_identical_behavior("printf '%.20a\\n' 3.14")
        self.assert_identical_behavior("printf '%.2a\\n' 2")
        self.assert_identical_behavior("printf '%.2a\\n' 100")
        self.assert_identical_behavior("printf '%.2a\\n' 0")

    def test_precision_signs_and_extremes(self):
        self.assert_identical_behavior("printf '%.2a\\n' -3.14")
        self.assert_identical_behavior("printf '%.2a\\n' 1e308")
        self.assert_identical_behavior("printf '%.2La\\n' 3.14")

    def test_uppercase(self):
        self.assert_identical_behavior("printf '%.2A\\n' 3.14")
        self.assert_identical_behavior("printf '%A\\n' 3.14")
        self.assert_identical_behavior("printf '%+.2A\\n' 3.14")
        self.assert_identical_behavior("printf '%A %A\\n' inf nan")


class TestPrintfFloatAltFlag(ConformanceTest):
    """'#' (alternate form) across the float conversions."""

    def test_alt_hex_float(self):
        self.assert_identical_behavior("printf '%#a\\n' 2")
        self.assert_identical_behavior("printf '%#.0a\\n' 3.14")
        self.assert_identical_behavior("printf '%#a\\n' 0")
        self.assert_identical_behavior("printf '%#.2a\\n' 2")
        self.assert_identical_behavior("printf '%#A\\n' 2")

    def test_alt_decimal_floats(self):
        self.assert_identical_behavior("printf '%#.0f\\n' 3")
        self.assert_identical_behavior("printf '%#.0f\\n' 3.7")
        self.assert_identical_behavior("printf '%#.0e\\n' 3")
        self.assert_identical_behavior("printf '%#g\\n' 3")
        self.assert_identical_behavior("printf '%#.0g\\n' 3")
        self.assert_identical_behavior("printf '%#.10g\\n' 3.14")
        self.assert_identical_behavior("printf '%#G\\n' 0.0001234")


class TestPrintfFloatPadding(ConformanceTest):
    """Width/zero-flag interactions: '0' pads after the 0x prefix and
    is ignored for non-finite values (space padding)."""

    def test_zero_pad_after_prefix(self):
        self.assert_identical_behavior("printf '%020.2a\\n' 3.14")
        self.assert_identical_behavior("printf '%#020.3a\\n' 3.14")
        self.assert_identical_behavior("printf '%20.2a|\\n' 3.14")

    def test_nonfinite_space_padded(self):
        self.assert_identical_behavior("printf '%010a\\n' inf")
        self.assert_identical_behavior("printf '%010f\\n' inf")
        self.assert_identical_behavior("printf '%010e\\n' -inf")
        self.assert_identical_behavior("printf '%.2a %#a %+a\\n' inf inf inf")
