"""bash's ``legal_number`` operand grammar (psh/builtins/numeric.py).

The validator every builtin NUMERIC OPERAND goes through, and the reason it
exists: Python's ``int()`` is more permissive than bash's ``strtoimax``-based
parser in three ways that are all observable, and psh silently accepted each
one where bash 5.3.15 reports ``numeric argument required`` (ledger W0-N30).

Grammar and values probed against bash 5.3.15 on 2026-09-07 in -c,
script-file and stdin modes; the operand parser itself did not change in 5.3
(empirical, no CHANGES/NEWS item) -- only the STATUS its callers report did.
The end-to-end pins are in
tests/conformance/bash/test_exit_cd_options_conformance.py.
"""

import pytest

from psh.builtins.numeric import INT64_MAX, INT64_MIN, legal_number


class TestAccepted:
    @pytest.mark.parametrize("text,value", [
        ("7", 7),
        ("0", 0),
        ("007", 7),                      # leading zeros are not octal
        ("+5", 5),
        ("-5", -5),
        ("-0", 0),
        ("  7  ", 7),                    # surrounding whitespace is skipped
        ("\t7", 7), ("\n7", 7), ("\v7", 7), ("\f7", 7), ("\r7", 7),
        ("7 \t", 7),
        ("9223372036854775807", INT64_MAX),
        ("-9223372036854775808", INT64_MIN),
    ])
    def test_operand_is_a_number(self, text, value):
        assert legal_number(text) == value


class TestRejected:
    @pytest.mark.parametrize("text", [
        # The three int() over-acceptances that motivated this module.
        "5_0",                           # PEP 515 separator
        "٥",                        # Arabic-Indic five
        "１",                        # fullwidth one
        "99999999999999999999",          # far past int64
        "9223372036854775808",           # int64 max + 1
        "-9223372036854775809",          # int64 min - 1
        # Shapes bash and psh already agreed on; pinned so a rewrite of the
        # regex cannot quietly widen them.
        "", " ", "abc", "7abc", "abc7", "0x10", "1e3", "1.5",
        "+ 7", "- 7", "++7", "--7", "-+7", "7 8",
        " 5",                       # NBSP is not C whitespace
    ])
    def test_operand_is_not_a_number(self, text):
        assert legal_number(text) is None


def test_zero_is_a_value_not_a_rejection():
    """The reason callers must test ``is None`` and never falsity."""
    assert legal_number("0") == 0
    assert legal_number("0") is not None


def test_int64_bounds_are_inclusive():
    assert legal_number(str(INT64_MAX)) == INT64_MAX
    assert legal_number(str(INT64_MIN)) == INT64_MIN
    assert legal_number(str(INT64_MAX + 1)) is None
    assert legal_number(str(INT64_MIN - 1)) is None
