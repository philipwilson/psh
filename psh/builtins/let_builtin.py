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

        from ..expansion.arithmetic import evaluate_arithmetic

        result = 0
        for expr in exprs:
            try:
                # `let` args are already shell-word-processed (quotes removed by
                # the shell), so a source-spelled associative subscript gets NO
                # extra dquote round — unlike `(( ))`/`$(( ))` (W2/CV1 B1).
                result = evaluate_arithmetic(expr, shell,
                                             arith_source_quotes=False)
            except (ValueError, ArithmeticError) as e:
                self.error(f"{expr}: {e}", shell)
                return 1
        # Like ((...)): success when the (last) value is non-zero.
        return 0 if result != 0 else 1
