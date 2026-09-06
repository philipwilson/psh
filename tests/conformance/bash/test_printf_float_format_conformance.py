"""Conformance: printf float formatting — %a/%A precision + '#' flag (5R rider).

bash's ``printf`` builtin formats ``%a``/``%A`` through C ``long double``;
psh formats a Python ``float`` (IEEE double).  Whether a hex-float cell
matches therefore depends on the ORACLE HOST's ``long double``, and the
sensitive cells are classified by predicates PROBED on the oracle binary
(``tests/harness/oracle_policy.py``), never by an OS or bash-version
literal in test code (D5).  Park P-6: a property of the oracle's
libc/``long double``, not a psh defect; psh is unchanged.  Three oracle
hosts have been run, each with a transcript:

- **macOS libc, arm64** (``long double`` == double; ``printf '%a' 1`` ->
  ``0x1p+0``, ``printf '%a' 0.1`` -> ``0x1.999999999999ap-4``): every cell
  identical, nothing skipped.  Local gate: Homebrew bash 5.3.15 and a
  source-built 5.3.15 (tools/ci/build_bash_oracle.sh), 2026-09-06.
- **x86-64 glibc** (x87 80-bit ``long double`` with an EXPLICIT integer
  bit, so the leading hex digit is 8..f: ``printf '%a' 1`` -> ``0x8p-3``):
  every finite non-zero ``%a``/``%A`` cell differs.  Nightly run
  34008477403 (2026-09-06, the 5.2.21 system bash, x86_64-pc-linux-gnu) reported seven
  red methods, each stopping at its first differing cell:
  ``printf '%.2a' 3.14`` -> bash ``0xc.8fp-2`` vs psh ``0x1.92p+1``;
  ``'%.2a' 0.1`` -> ``0xc.cdp-7`` vs ``0x1.9ap-4``; ``'%.20a' 3.14`` ->
  ``0xc.8f5c28f5c28f5c300000p-2`` vs ``0x1.91eb851eb851f0000000p+1``;
  ``'%.2a' -3.14`` -> ``-0xc.8fp-2`` vs ``-0x1.92p+1``; ``'%.2A' 3.14`` ->
  ``0XC.8FP-2`` vs ``0X1.92P+1``; ``'%#a' 2`` -> ``0x8.p-2`` vs
  ``0x1.p+1``; ``'%020.2a' 3.14`` -> ``0x00000000000c.8fp-2`` vs
  ``0x000000000001.92p+1``.  The package verifier (w0-verify-b,
  2026-09-06, ubuntu:24.04 amd64 container) then ran every cell: 23 of
  those methods' 26 cells differ; the other three — ``'%.2a' 0``,
  ``'%#a' 0``, ``'%A %A' inf nan`` — match on every host and now live in
  the unmarked ``test_zero_and_nonfinite_hex_forms``.
- **aarch64 glibc** (IEEE binary128 ``long double``, implicit bit:
  ``printf '%a' 1`` -> ``0x1p+0``, but ``printf '%a' 0.1`` ->
  ``0x1.999999999999999999999999999ap-4``): only the two cells that print
  the FULL mantissa differ — ``printf '%.20a' 3.14`` -> bash
  ``0x1.91eb851eb851eb851eb8p+1`` vs psh ``0x1.91eb851eb851f0000000p+1``,
  and ``printf '%A' 3.14`` -> bash ``0X1.91EB851EB851EB851EB851EB851FP+1``
  vs psh ``0X1.91EB851EB851FP+1``.  w0-verify-b, ubuntu:24.04 arm64
  container, the 5.2.21 system bash, aarch64-unknown-linux-gnu, 2026-09-06 (the
  previous revision of this module: 2 failed, 7 passed, 0 skipped).

Why the low-precision cells match on binary128 but not on x87: 3.14 is
not dyadic, so ``strtold`` yields a DIFFERENT number in a 64-bit (x87) or
113-bit (binary128) significand than the 53-bit double psh formats; a
precision of at most three hex digits rounds both to the same digits
(``0x1.92``), while the x87 explicit integer bit changes the leading
digit and exponent at every precision.  Only the dyadic inputs (2, 100,
0) and the non-finite ones are "the same value" on every host.

Two predicates follow:

- ``oracle_feature('x87_long_double')`` (probe ``printf '%a' 1``, leading
  digit other than 1): the seven methods whose EVERY cell differs on x87
  (21 cells).
- ``oracle_feature('long_double_wider_than_double')`` (probe
  ``printf '%a' 0.1``, more than 13 fraction digits or a leading digit
  other than 1 — true on x87 AND on binary128): the two full-mantissa
  cells, one method each.

Skips by oracle host, THIS revision run against the real binaries
(w0-pkg-b, 2026-09-06, colima ubuntu:24.04 containers, their 5.2.21 system bash):
macOS 12 passed, 0 skipped; x86-64 glibc (``printf '%a' 0.1`` ->
``0xc.ccccccccccccccdp-7``) 3 passed, 9 skipped — both predicates hold;
aarch64 glibc 10 passed, 2 skipped.  The predicates are evaluated at
import, so with no resolvable oracle this module fails at COLLECTION
(``BashOracleUnavailable``) rather than per test — louder and earlier
than before, and moot under ``run_tests.py``, whose preflight resolves the
oracle first.

Deliberately excluded as platform-divergent (never pinned here):

- rounding TIES (macOS truncates exact halves; pinned engine-direct in
  tests/unit/utils/test_printf_formatter.py::TestHexFloatPrecisionAltForm)
- subnormals (macOS renormalizes to 0x1p-1074 + ERANGE warning; glibc
  keeps the denormalized 0x0...p-1022 form psh implements — the
  DECLARED divergence recorded in the 5R LEDGER row)

Probe provenance: tmp/5r-probes/ battery vs bash 5.2.26, 2026-08-09;
re-verified 2026-09-06 on the three hosts listed above.
"""

import pytest
from conformance_framework import ConformanceTest
from oracle_policy import oracle_feature

# Park P-6 classifiers (see the module docstring for the per-host evidence).
# Every cell in an x87-marked method differs on x86-64 glibc; every cell in a
# wider-marked method differs on any long double wider than 53 bits.
x87_oracle = pytest.mark.skipif(
    oracle_feature('x87_long_double'),
    reason="oracle formats long double %a in x87 explicit-integer-bit form "
           "(platform, Park P-6)",
)
wide_long_double_oracle = pytest.mark.skipif(
    oracle_feature('long_double_wider_than_double'),
    reason="oracle's long double is wider than double, so a full-mantissa %a "
           "prints digits a double cannot hold (platform, Park P-6)",
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
        self.assert_identical_behavior("printf '%.2a\\n' 2")
        self.assert_identical_behavior("printf '%.2a\\n' 100")

    @wide_long_double_oracle
    def test_explicit_precision_beyond_double_width(self):
        # 20 hex digits ask for 80 fraction bits: a double pads with zeros
        # after its 13th digit, a wider long double prints real ones.
        self.assert_identical_behavior("printf '%.20a\\n' 3.14")

    @x87_oracle
    def test_precision_signs_and_extremes(self):
        self.assert_identical_behavior("printf '%.2a\\n' -3.14")
        self.assert_identical_behavior("printf '%.2a\\n' 1e308")
        self.assert_identical_behavior("printf '%.2La\\n' 3.14")

    @x87_oracle
    def test_uppercase(self):
        self.assert_identical_behavior("printf '%.2A\\n' 3.14")
        self.assert_identical_behavior("printf '%+.2A\\n' 3.14")

    @wide_long_double_oracle
    def test_default_precision_prints_full_mantissa(self):
        # No precision: the whole significand is printed, so its width
        # (13, 16 or 28 hex digits) is the output.
        self.assert_identical_behavior("printf '%A\\n' 3.14")

    def test_zero_and_nonfinite_hex_forms(self):
        # No mantissa bits to widen or renormalise: identical on every host
        # (x86-64 glibc, aarch64 glibc and macOS, verified 2026-09-06).
        self.assert_identical_behavior("printf '%.2a\\n' 0")
        self.assert_identical_behavior("printf '%#a\\n' 0")
        self.assert_identical_behavior("printf '%A %A\\n' inf nan")


class TestPrintfFloatAltFlag(ConformanceTest):
    """'#' (alternate form) across the float conversions."""

    @x87_oracle
    def test_alt_hex_float(self):
        self.assert_identical_behavior("printf '%#a\\n' 2")
        self.assert_identical_behavior("printf '%#.0a\\n' 3.14")
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
