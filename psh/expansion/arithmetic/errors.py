"""Exception types and the 64-bit signed wrapping helper for arithmetic."""

import builtins

from ...core.exceptions import PshError


# Inherit from the Python builtin ArithmeticError so that callers that
# catch the builtin (without importing psh's version) still work.
class ShellArithmeticError(PshError, builtins.ArithmeticError):
    """Exception for arithmetic evaluation errors"""
    pass


# Keep the old name as an alias so that callers that import
# ``from psh.expansion.arithmetic import ArithmeticError`` continue to work.
ArithmeticError = ShellArithmeticError  # noqa: A001


def _to_signed64(value: int) -> int:
    """Wrap an arbitrary-precision integer into the signed 64-bit range."""
    value &= 0xFFFFFFFFFFFFFFFF
    if value & 0x8000000000000000:
        value -= 0x10000000000000000
    return value
