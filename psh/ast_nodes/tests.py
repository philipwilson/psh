"""Enhanced test expression nodes for ``[[ ... ]]``."""

from dataclasses import dataclass, field
from typing import List, Optional

from .base import ASTNode, Statement
from .redirects import Redirect
from .words import Word


class TestExpression(ASTNode):
    """Base class for test expressions."""
    pass


@dataclass
class BinaryTestExpression(TestExpression):
    """Binary test expression like STRING1 < STRING2.

    Operands are :class:`Word` nodes (Tier C-D2, 2026-06-13): quote context
    comes from the Word's parts, like everywhere else in the AST, replacing
    the former plain-string operands plus ``left_quote_type``/
    ``right_quote_type`` side-channels. ``left_quote_type`` was dead (no
    consumer) and is gone; ``right_quote_type`` is now a derived read-only
    property keyed off ``right_word.is_quoted`` for the evaluator's
    quoted-pattern/regex literal-matching path.

    ``left``/``right`` remain available as derived read-only strings (the
    operand's pre-expansion text) for the formatters/debug visitors.
    """
    left_word: 'Word'
    operator: str  # =, !=, <, >, =~, -eq, -ne, etc.
    right_word: 'Word'

    @property
    def left(self) -> str:
        """Pre-expansion text of the left operand (derived from the Word)."""
        return self.left_word.display_text()

    @property
    def right(self) -> str:
        """Pre-expansion text of the right operand (derived from the Word)."""
        return self.right_word.display_text()

    @property
    def right_quote_type(self) -> Optional[str]:
        """Legacy quote-type signal for the right operand, derived from the
        Word. The evaluator's quoted-literal vs glob/regex decision only
        needs the boolean "is the whole operand quoted"; this returns the
        dominant quote char when so (so ``is not None`` reproduces the old
        ``right_quote_type is not None``), else None — exactly matching the
        former stored field for every operand shape the parser builds
        (wholly-quoted -> set; unquoted or mixed-quote -> None)."""
        if self.right_word.is_quoted:
            return self.right_word.effective_quote_char or '"'
        return None


@dataclass
class UnaryTestExpression(TestExpression):
    """Unary test expression like -f FILE."""
    operator: str  # -f, -d, -z, -n, etc.
    operand: str


@dataclass
class CompoundTestExpression(TestExpression):
    """Compound test expression with && or ||."""
    left: TestExpression
    operator: str  # && or ||
    right: TestExpression


@dataclass
class NegatedTestExpression(TestExpression):
    """Negated test expression with !."""
    expression: TestExpression


@dataclass
class EnhancedTestStatement(Statement):
    """Enhanced test construct [[ ... ]]."""
    expression: TestExpression  # The test expression to evaluate
    redirects: List[Redirect] = field(default_factory=list)
