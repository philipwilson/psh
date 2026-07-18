"""Array assignment nodes.

These appear as the ``array_assignments`` prefix of a SimpleCommand (and
``ArrayInitialization`` also as ``Word.array_init``). They depend on
:class:`Word`, so they live downstream of ``words.py``.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from .base import ASTNode
from .words import Word

if TYPE_CHECKING:
    from .syntax_templates import SubscriptSpec  # noqa: F401


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
    # stored. Sole consumer: validator_visitor's mixed-element-type advisory
    # (the executor uses `words` exclusively). A2 dropped the parallel
    # stored fields so a node can no longer "claim two truths at once".
    @property
    def element_types(self) -> List[str]:
        """Per-element legacy type string (WORD/STRING/COMPOSITE/…)."""
        return [_word_element_type(w) for w in self.words]


@dataclass
class ArrayElementAssignment(ArrayAssignment):
    """Array element assignment: arr[0]=value or arr[0]+=value"""
    name: str
    index: str  # The subscript text (verbatim); expanded/evaluated by the executor
    value: str  # The value to assign
    # Word AST node for the value (REQUIRED — no default). Both parsers
    # always build it; the executor expands it with bash assignment-value
    # semantics (all expansions, no word splitting, no pathname expansion,
    # tilde after '='/':'). The A1 invariant tests enforce population.
    value_word: Word
    is_append: bool = False  # True for += assignment
    # Typed subscript carrier (campaign S3), set by both parsers. ``index``
    # stays the raw subscript (the lazy authority the executor expands/keys);
    # ``index_spec`` is the read-time-validation authority — a nested ``$()`` in
    # the subscript (``a[$(if)]=v``) is validated when the command is read. The
    # indexed-vs-associative KEYING (the r21 six-implementations consolidation)
    # is W2's SubscriptEvaluator, NOT decided here. None for manual nodes.
    # Guard: ``index_spec.text == index``.
    index_spec: Optional['SubscriptSpec'] = field(
        default=None, compare=False, repr=False)
