"""Conformance: printf float formatting — %a/%A precision + '#' flag (5R rider).

Every cell here is libc-STABLE on an IEEE-double oracle host: macOS libc
(the local gate, arm64) and glibc on arm64 agree on all of them, so the
suite passes against live bash there.  One PLATFORM exception is
classified, not fixed:

- x87 long double (x86-64 glibc — the Linux nightly).  bash's ``printf``
  builtin formats ``%a``/``%A`` through ``long double``, and on x86-64 that
  is the 80-bit x87 format whose integer bit is EXPLICIT, so glibc prints
  it as the leading hex digit: ``printf '%.2a' 3.14`` -> ``0xc.8fp-2``
  where an IEEE-double host (and psh, which formats a Python ``float``)
  prints ``0x1.92p+1``.  Same value, different normalisation.  This is a
  property of the ORACLE's libc/``long double``, not a psh defect (Park
  P-6), so the seven cells that format a finite non-zero value with
  ``%a``/``%A`` are skipped when the PROBED predicate
  ``oracle_feature('x87_long_double')`` holds — never an OS or bash-version
  literal in test code (D5).  psh is unchanged.

  Evidence: nightly run 34008477403 (2026-09-06, x86_64-pc-linux-gnu),
  exactly these seven cells, each the first cell of its test method
  (bash on the left, psh — identical to an IEEE-double bash — on the right):

  - ``printf '%.2a\\n' 3.14``    ``0xc.8fp-2``            vs ``0x1.92p+1``
  - ``printf '%.2a\\n' 0.1``     ``0xc.cdp-7``            vs ``0x1.9ap-4``
  - ``printf '%.20a\\n' 3.14``   ``0xc.8f5c28f5c28f5c300000p-2``
    vs ``0x1.91eb851eb851f0000000p+1``
  - ``printf '%.2a\\n' -3.14``   ``-0xc.8fp-2``           vs ``-0x1.92p+1``
  - ``printf '%.2A\\n' 3.14``    ``0XC.8FP-2``            vs ``0X1.92P+1``
  - ``printf '%#a\\n' 2``        ``0x8.p-2``              vs ``0x1.p+1``
  - ``printf '%020.2a\\n' 3.14`` ``0x00000000000c.8fp-2`` vs ``0x000000000001.92p+1``

  The decimal-float ``#`` cells and the inf/nan padding cells carry no hex
  mantissa, are unaffected, and run on every host.

Deliberately excluded as platform-divergent:

- rounding TIES (macOS truncates exact halves; pinned engine-direct in
  tests/unit/utils/test_printf_formatter.py::TestHexFloatPrecisionAltForm)
- subnormals (macOS renormalizes to 0x1p-1074 + ERANGE warning; glibc
  keeps the denormalized 0x0...p-1022 form psh implements — the
  DECLARED divergence recorded in the 5R LEDGER row)

Probe provenance: tmp/5r-probes/ battery vs bash 5.2.26, 2026-08-09;
re-verified 2026-09-06 against a source-built bash 5.3.15
(tools/ci/build_bash_oracle.sh, aarch64-apple-darwin, ``printf '%a' 1`` ->
``0x1p+0``): every cell identical.
"""

import pytest
from conformance_framework import ConformanceTest
from oracle_policy import oracle_feature

# Park P-6: the oracle's libc formats `long double` %a with the x87 explicit
# integer bit (`printf '%a' 1` -> `0x8p-3`); a platform property, probed on
# the oracle binary itself.  Applied to EXACTLY the seven test methods that
# were red in nightly run 34008477403 (see the module docstring).
x87_oracle = pytest.mark.skipif(
    oracle_feature('x87_long_double'),
    reason="oracle formats long double %a in x87 explicit-integer-bit form "
           "(platform, Park P-6)",
)


class TestPrintfHexFloatPrecision(ConformanceTest):
    """%a/%A precision: mantissa rounded/padded to N hex digits."""

    @x87_oracle
    def test_precision_rounds(self):
        self.assert_identical_behavior("printf '%.2a\\n' 3.14")
        self.assert_identical_behavior("printf '%.1a\\n' 3.14")
        self.assert_identical_behavior("printf '%.3a\\n' 3.14")
        self.assert_identical_behavior("printf '%.0a\\n' 3.14")

    @x87_oracle
    def test_precision_round_up_and_carry(self):
        self.assert_identical_behavior("printf '%.2a\\n' 0.1")
        self.assert_identical_behavior("printf '%.4a\\n' 0.1")
        self.assert_identical_behavior("printf '%.0a\\n' 1.9999999999")

    @x87_oracle
    def test_precision_zero_pads(self):
        self.assert_identical_behavior("printf '%.20a\\n' 3.14")
        self.assert_identical_behavior("printf '%.2a\\n' 2")
        self.assert_identical_behavior("printf '%.2a\\n' 100")
        self.assert_identical_behavior("printf '%.2a\\n' 0")

    @x87_oracle
    def test_precision_signs_and_extremes(self):
        self.assert_identical_behavior("printf '%.2a\\n' -3.14")
        self.assert_identical_behavior("printf '%.2a\\n' 1e308")
        self.assert_identical_behavior("printf '%.2La\\n' 3.14")

    @x87_oracle
    def test_uppercase(self):
        self.assert_identical_behavior("printf '%.2A\\n' 3.14")
        self.assert_identical_behavior("printf '%A\\n' 3.14")
        self.assert_identical_behavior("printf '%+.2A\\n' 3.14")
        self.assert_identical_behavior("printf '%A %A\\n' inf nan")


class TestPrintfFloatAltFlag(ConformanceTest):
    """'#' (alternate form) across the float conversions."""

    @x87_oracle
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

    @x87_oracle
    def test_zero_pad_after_prefix(self):
        self.assert_identical_behavior("printf '%020.2a\\n' 3.14")
        self.assert_identical_behavior("printf '%#020.3a\\n' 3.14")
        self.assert_identical_behavior("printf '%20.2a|\\n' 3.14")

    def test_nonfinite_space_padded(self):
        self.assert_identical_behavior("printf '%010a\\n' inf")
        self.assert_identical_behavior("printf '%010f\\n' inf")
        self.assert_identical_behavior("printf '%010e\\n' -inf")
        self.assert_identical_behavior("printf '%.2a %#a %+a\\n' inf inf inf")
