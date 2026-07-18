"""Typed syntax templates for expansion-bearing regions (campaign S3).

A *syntax-bearing region* is a stretch of shell source whose own grammar is
parsed LAZILY at evaluation time — a parameter-expansion operand
(``${x:-WORD}``), an arithmetic expression (``$((EXPR))``, ``(( EXPR ))``, a
C-style ``for`` clause), or an array subscript (``arr[SUB]``). bash parses the
region's own grammar (pattern / arithmetic) only when evaluation reaches it, so
dynamically generated syntax keeps working (``op='+'; echo $((1 $op 2))``).

But bash validates the *nested shell grammar* — modern ``$(...)``/``<(...)``/
``>(...)`` command and process substitutions — inside these regions when it
READS the enclosing command, rejecting the whole input buffer before anything
runs, even in a branch that never executes (``true || echo ${x:-$(if)}``).
Legacy backticks are the deliberate exception: bash defers them and continues
around inner errors (``echo ${x:-`if`}`` runs, empty).

A :class:`SyntaxTemplate` carries BOTH facts, with a designed authority split:

* ``text`` — the raw region source. This is the LAZY-GRAMMAR authority: the
  expansion/arithmetic engines re-parse it at evaluation time, which is exactly
  bash's dynamic-syntax timing (NOT information loss — it is required behavior).
* ``subs`` — the validated nested modern substitutions (each an
  :class:`~psh.ast_nodes.words.Expansion` whose body was parsed into a
  ``Program`` at read time) plus deferred-backtick markers, with their source
  spans. This is the READ-TIME-VALIDATION and analysis authority; it is what a
  raw string could never carry.

So the region is never represented ONLY by an untyped string (campaign exit
criterion #3): the typed ``subs`` is the authority for "is the nested shell
grammar valid, and here are the parsed sub-programs", while ``text`` is the
bash-blessed lazy-grammar view. The two are kept consistent by a guard
(:meth:`SyntaxTemplate.spans_reconstruct`).

The expansion-side field IR (how the region's own value/pattern grammar is
finally materialised) is owned by W1/W2; these templates deliberately do not
restructure it. ``WordTemplate`` is the parser-word-builder authority;
``SubscriptSpec`` is interpreted by W2's ``SubscriptEvaluator`` only after the
target array's kind (indexed vs associative) is known.
"""

from dataclasses import dataclass, field
from typing import Tuple

from .words import CommandSubstitution, Expansion


@dataclass(frozen=True)
class NestedSub:
    """One nested modern substitution found inside a syntax-bearing region.

    ``expansion`` is a :class:`CommandSubstitution` or
    :class:`ProcessSubstitution` whose ``program`` was parsed at READ time
    (validated) — except a DEFERRED backtick, which is a
    ``CommandSubstitution(backtick_style=True, program=None)`` carried but NOT
    validated (bash defers backtick parsing). ``start``/``end`` are the
    half-open span of the substitution's SOURCE spelling within the region's
    ``text`` (``text[start:end]`` is the exact source), so a guard can prove the
    typed value reconstructs the raw region.
    """
    expansion: Expansion
    start: int
    end: int

    @property
    def is_deferred_backtick(self) -> bool:
        """THE named predicate for the deferred-backtick timing policy.

        A legacy backtick substitution has an explicit, Bash-pinned deferred
        timing: it is NOT validated at read time, and at expansion time an
        inner syntax error is non-fatal (the surrounding command still runs,
        the backtick yields empty). This predicate is the single seam the
        read-time validator and every consumer use to recognise that policy —
        no scattered raw ``backtick_style`` checks in the validation path.
        The invariant it encodes (``backtick_style`` implies ``program is
        None``) is enforced by ``tests/unit/tooling/test_syntax_template_guards.py``.
        """
        exp = self.expansion
        return isinstance(exp, CommandSubstitution) and exp.backtick_style


@dataclass(frozen=True)
class SyntaxTemplate:
    """Base: a syntax-bearing region's raw text plus its validated nested subs.

    See the module docstring for the authority split. ``subs`` is source-ordered
    and flattened (a substitution nested inside a ``${...}``/``$((...))`` within
    the region appears with its absolute span in ``text``).
    """
    text: str
    subs: Tuple[NestedSub, ...] = field(default_factory=tuple)

    @property
    def validated(self) -> Tuple[NestedSub, ...]:
        """The read-time-validated modern substitutions (excludes backticks)."""
        return tuple(s for s in self.subs if not s.is_deferred_backtick)

    @property
    def deferred_backticks(self) -> Tuple[NestedSub, ...]:
        """The deferred (un-validated) legacy backtick substitutions."""
        return tuple(s for s in self.subs if s.is_deferred_backtick)

    def spans_reconstruct(self) -> bool:
        """Guard: every sub's span selects its own source spelling from ``text``.

        This is the consistency check that keeps ``text`` (the lazy-grammar
        authority) and ``subs`` (the typed read-time authority) from drifting:
        a template whose spans no longer index the raw text is a defect.
        """
        for s in self.subs:
            if not (0 <= s.start <= s.end <= len(self.text)):
                return False
            source = str(s.expansion)
            if self.text[s.start:s.end] != source:
                return False
        return True


@dataclass(frozen=True)
class WordTemplate(SyntaxTemplate):
    """A parameter-expansion operand region (``${x:-WORD}``, ``${x#PAT}`` ...).

    Grammar: parameter-operand word/pattern (lazy). Authority: the parser word
    builder (``support/syntax_templates.build_word_template``). Nested modern
    ``$()``/``<()``/``>()`` are read-time validated; backticks deferred.
    """


@dataclass(frozen=True)
class ArithmeticTemplate(SyntaxTemplate):
    """An arithmetic region (``$((E))``, ``(( E ))``, C-style ``for`` clause).

    Grammar: arithmetic (LAZY — parsed only at evaluation, so dynamic operators
    and expressions keep working). Authority for the lazy parse: the arithmetic
    evaluator. Nested modern ``$()`` are read-time validated; backticks deferred.
    """


@dataclass(frozen=True)
class SubscriptSpec(SyntaxTemplate):
    """An array subscript region (``arr[SUB]``, ``arr[SUB]=v``).

    "Structured word template interpreted only after target type is known"
    (§5): the read-time job here is nested-shell-grammar validation and carrying
    the raw subscript; the indexed-vs-associative interpretation (arithmetic for
    indexed, string key for associative — the r21 six-implementations
    consolidation) is W2's ``SubscriptEvaluator`` and is NOT decided here.
    """
