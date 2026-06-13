"""Array assignment nodes.

These appear as the ``array_assignments`` prefix of a SimpleCommand (and
``ArrayInitialization`` also as ``Word.array_init``). They depend on
:class:`Word`, so they live downstream of ``words.py``.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Union

from .base import ASTNode
from .words import Word

if TYPE_CHECKING:
    from ..lexer.token_types import Token


@dataclass
class ArrayAssignment(ASTNode):
    """Base class for array assignments."""
    pass


def _word_element_type(word: 'Word') -> str:
    """Legacy element-type string DERIVED from a Word's quote context.

    Reproduces the value the parsers used to STORE in
    ``ArrayInitialization.element_types`` (display/tooling metadata only;
    the executor never reads it). The recursive-descent parser computed
    this exact mapping from the element Word; deriving it here keeps the
    formatter/validator output byte-identical after the stored field was
    dropped (A2, 2026-06-13).
    """
    if word.is_quoted:
        return 'STRING'
    if any(getattr(p, 'quoted', False) for p in word.parts):
        return 'COMPOSITE_QUOTED'
    if len(word.parts) > 1:
        return 'COMPOSITE'
    return 'WORD'


@dataclass
class ArrayInitialization(ArrayAssignment):
    """Array initialization: arr=(one two three) or arr+=(four five)"""
    name: str
    elements: List[str]  # The elements inside parentheses (flat strings)
    is_append: bool = False  # True for += initialization
    # Word AST nodes for each element (REQUIRED, parallel to `elements`).
    # Both parsers always populate this; the executor expands each element
    # through the same Word expansion pipeline as command arguments (IFS
    # splitting, quote-aware globbing, tilde, noglob/nullglob/dotglob) and
    # raises an internal error on a missing Word (fallback audit 2026-06-12).
    words: List[Word] = field(default_factory=list)

    # Legacy string-list metadata, now DERIVED from `words` rather than
    # stored. Sole consumers: formatter_visitor / validator_visitor
    # (the executor uses `words` exclusively). A2 dropped the parallel
    # stored fields so a node can no longer "claim two truths at once".
    @property
    def element_types(self) -> List[str]:
        """Per-element legacy type string (WORD/STRING/COMPOSITE/…)."""
        return [_word_element_type(w) for w in self.words]

    @property
    def element_quote_types(self) -> List[Optional[str]]:
        """Per-element dominant quote char, derived from each Word."""
        return [w.effective_quote_char for w in self.words]


@dataclass
class ArrayElementAssignment(ArrayAssignment):
    """Array element assignment: arr[0]=value or arr[0]+=value"""
    name: str
    index: Union[str, List['Token']]  # The index expression (str for compatibility, List[Token] for late binding)
    value: str  # The value to assign
    # Word AST node for the value (REQUIRED — no default). Both parsers
    # always build it; the executor expands it with bash assignment-value
    # semantics (all expansions, no word splitting, no pathname expansion,
    # tilde after '='/':'). The A1 invariant tests enforce population.
    value_word: Word
    is_append: bool = False  # True for += assignment

    # Legacy string metadata, now DERIVED from `value_word` rather than
    # stored. Sole consumer: formatter_visitor (re-quotes the value).
    @property
    def value_type(self) -> str:
        """'STRING' if the value Word is quoted, else 'WORD' (derived)."""
        return 'STRING' if self.value_word.is_quoted else 'WORD'

    @property
    def value_quote_type(self) -> Optional[str]:
        """The value Word's dominant quote char (derived)."""
        return self.value_word.effective_quote_char
