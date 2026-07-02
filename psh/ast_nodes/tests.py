"""Enhanced test expression nodes for ``[[ ... ]]``."""

from dataclasses import dataclass, field
from typing import List

from .base import ASTNode, CompoundCommand, Statement
from .redirects import Redirect
from .words import Word


class TestExpression(ASTNode):
    """Base class for test expressions."""
    pass


@dataclass
class BinaryTestExpression(TestExpression):
    """Binary test expression like STRING1 < STRING2.

    Operands are multi-part :class:`Word` nodes (Tier C-D2 introduced the
    Words; T3.1, 2026-06-14, made them genuinely multi-part). Each operand
    token keeps its own per-part quote context (``LiteralPart``/
    ``ExpansionPart`` with ``quoted``/``quote_char``), exactly like
    SimpleCommand arguments — so ``[[ ab == ab"?" ]]`` knows the ``?`` is a
    quoted literal while ``ab`` is unquoted. The evaluator reads that
    per-part quoting directly to decide, segment by segment, whether the
    RHS contributes glob/regex-active or literal text. The former
    ``left_quote_type``/``right_quote_type`` single-char sentinels (which
    could only describe the operand as a WHOLE) are gone.

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


@dataclass
class UnaryTestExpression(TestExpression):
    """Unary test expression like -f FILE.

    ``operand_word`` is a multi-part :class:`Word` carrying per-part quote
    context, exactly like :class:`BinaryTestExpression`'s operands — so a
    single-quoted operand (``[[ -n '$x' ]]``) stays literal instead of being
    re-expanded. ``operand`` remains available as the derived read-only
    pre-expansion string for the formatters/debug visitors and for ``-v``
    (which wants the variable name, not an expansion).
    """
    operator: str  # -f, -d, -z, -n, etc.
    operand_word: 'Word'

    @property
    def operand(self) -> str:
        """Pre-expansion text of the operand (derived from the Word)."""
        return self.operand_word.display_text()


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
class EnhancedTestStatement(Statement, CompoundCommand):
    """Enhanced test construct [[ ... ]].

    Inherits both Statement and CompoundCommand: ``[[ ... ]]`` appears at
    statement level and also as a pipeline component (e.g. ``[[ -n x ]] | cat``),
    so the parser places it in ``Pipeline.commands`` like other control
    structures.
    """
    expression: TestExpression  # The test expression to evaluate
    redirects: List[Redirect] = field(default_factory=list)
