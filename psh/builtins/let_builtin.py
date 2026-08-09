"""let builtin: evaluate arithmetic expressions."""
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class LetBuiltin(Builtin):
    """Evaluate arithmetic expressions."""

    @property
    def name(self) -> str:
        return "let"

    @property
    def synopsis(self) -> str:
        return "let arg [arg ...]"

    @property
    def help(self) -> str:
        return """let: let arg [arg ...]
    Evaluate arithmetic expressions.

    Each ARG is an arithmetic expression evaluated using the same rules as
    $((...)) and ((...)). Assignments and side effects (e.g. x=5, ++x, x+=2)
    take effect. This is equivalent to ((ARG)) for each argument.

    Exit Status:
    Returns 0 if the last ARG evaluates to a non-zero value, 1 otherwise (or if
    an argument is an invalid expression)."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        exprs = args[1:]
        if not exprs:
            self.error("expression expected", shell)
            return 1

        # ONE deferred import statement, deliberately: the layering ratchet
        # counts import STATEMENTS, and this module's cap is 1 with zero slack
        # (test_import_layering.py::test_every_cap_equals_its_modules_actual_count).
        # ShellArithmeticError is re-exported by the arithmetic package's
        # __init__, so pulling both names through the existing statement keeps
        # the deferred-import floor exactly where it was.
        from ..expansion.arithmetic import (
            ShellArithmeticError,
            evaluate_arithmetic,
        )

        result = 0
        for expr in exprs:
            try:
                # `let` args are already shell-word-processed (quotes removed by
                # the shell), so a source-spelled associative subscript gets NO
                # extra dquote round — unlike `(( ))`/`$(( ))` (W2/CV1 B1).
                result = evaluate_arithmetic(expr, shell,
                                             arith_source_quotes=False)
            except ShellArithmeticError as e:
                # THE evaluator's contract type, not the broader
                # `(ValueError, ArithmeticError)` pair this used to catch
                # (remediation 5C.1, successor D-3.5-s2).
                #
                # The ValueError leg was DEAD: forced over 42 user-reachable
                # cells varying expression shape AND shell OPTION, it never
                # fired once — every arithmetic failure arrives as
                # ShellArithmeticError. And no RAW ArithmeticError can escape
                # either: `_apply_binary_op` is the single door for raw
                # arithmetic and guards every operation (divide/modulo check
                # for zero, power checks for a negative exponent and uses
                # modular pow, shifts mask their count), measured over a
                # further 90 operator x form x danger-value cells with zero
                # non-Shell escapes. So a raw ZeroDivisionError here would be a
                # genuine internal defect and SHOULD surface.
                #
                # Nothing user-visible moves: ShellArithmeticError is both a
                # PshError and a builtins.ArithmeticError.
                #
                # NOT caught, and never was: `set -u` raises
                # UnboundVariableError and a readonly target raises
                # ReadonlyVariableError. Both are PshError but NEITHER leg, so
                # they propagate past `let` to the top-level handler — bash
                # agrees on exit status for both.
                self.error(f"{expr}: {e}", shell)
                return 1
        # Like ((...)): success when the (last) value is non-zero.
        return 0 if result != 0 else 1
