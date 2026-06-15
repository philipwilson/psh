"""Data model for Word expansion: the policy table and walk IR.

These are the value types the Word-expansion engine (``word_expander.py``)
operates on, separated from the engine itself:

- :class:`WordExpansionPolicy` and its named instances name what each
  expansion context permits (the three axes ``split``/``glob``/
  ``assignment_tilde``). Callers across the codebase import the named
  policies to say what context they are expanding in.
- :class:`ExpandedSegment` and :class:`_WalkState` are the intermediate
  representation a single composite/unquoted word walk accumulates.

This module is pure data (no shell or AST dependencies); keep it that way.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class WordExpansionPolicy:
    """What the surrounding context permits for one Word expansion.

    The three axes are the complete set of differences between psh's
    Word-expansion contexts (tabulated from every caller of the old
    ``_expand_word``/``expand_word_to_fields`` flag pairs):

    Attributes:
        split: IFS-split the results of unquoted expansions. In splitting
            contexts, multi-field expansions ("$@", "${a[@]}") produce
            multiple fields regardless — the axis governs IFS splitting
            only. In NO-split contexts bash instead joins a field
            expansion's fields into one word with single spaces (probed
            2026-06-13: assoc-init `h=($@)` / `h=("$@")` and
            `declare v="$@"` all join), so split=False suppresses field
            production too.
        glob: pathname-expand unquoted glob characters (honoring
            noglob/nullglob/dotglob as always).
        assignment_tilde: when the word is shaped like an assignment
            (``NAME=...``/``NAME+=...``), expand unquoted tilde prefixes
            after the first ``=`` and after each ``:`` in the value.
    """
    split: bool
    glob: bool
    assignment_tilde: bool


#: Ordinary command arguments: the full pipeline — IFS splitting of
#: unquoted expansion results, pathname expansion, and value-tilde in
#: assignment-shaped words (bash: ``ls P=~/x`` tilde-expands).
COMMAND_ARGUMENT = WordExpansionPolicy(
    split=True, glob=True, assignment_tilde=True)

#: for/select item lists behave exactly like command arguments
#: (bash word-splits, globs, and tilde-expands ``for i in P=~/x``).
#: Kept as a named alias so call sites say what they mean.
LOOP_ITEM = COMMAND_ARGUMENT

#: Assignment-shaped arguments of declaration builtins (declare/export/
#: local/readonly/typeset/alias): the value is not word-split and not
#: pathname-expanded (``declare v=$x`` keeps "$x" whole; ``declare v=*``
#: keeps the literal ``*``), but value-tilde still applies
#: (``declare v=~/x`` expands) — bash 5.2.
DECLARATION_ASSIGNMENT = WordExpansionPolicy(
    split=False, glob=False, assignment_tilde=True)

#: Indexed-array initializer elements (``a=(x $v "q")``): full split and
#: glob like command arguments, but NO value-tilde — bash keeps
#: ``a=(P=~/x)`` literal.
ARRAY_INIT_ELEMENT = WordExpansionPolicy(
    split=True, glob=True, assignment_tilde=False)

#: Associative-array bare initializer elements (``h=(k v ...)`` under
#: declare -A): no splitting, no globbing (``h=($x)`` with x="k v"
#: creates the single key "k v"), and NO value-tilde — bash 5.2 keeps
#: ``h=(P=~/x v)``'s tilde literal (the element is the key "P=~/x"),
#: exactly like indexed-array initializer elements. A LEADING tilde
#: still expands (``h=(~ v)`` / ``h=(k ~/x)`` — bash), as does the
#: value of an explicit ``[k]=~/x`` element, which goes through the
#: scalar assignment-value walker instead of this policy.
#:
#: History: assignment_tilde was True until v0.326 — a pinned accident
#: from pre-policy code that aliased ``suppress_split_glob`` onto the
#: ``declaration_assignment`` flag (re-enabling value-tilde). Flipped to
#: the bash-correct value 2026-06-13 (Tier B10a); pinned by
#: tests/unit/expansion/test_word_expansion_policy.py and the assoc
#: rows in tests/conformance/bash/test_array_init_conformance.py.
ASSOC_INIT_ELEMENT = WordExpansionPolicy(
    split=False, glob=False, assignment_tilde=False)


@dataclass
class ExpandedSegment:
    """One contiguous piece of an expanded composite/unquoted word.

    The segment list is the explicit intermediate representation that
    replaced the old parallel arrays (``result_parts`` +
    ``splittable_idx``) plus the scattered word-level flags. Each part
    walker appends one (or, for affixed ``$@``, the walker short-circuits)
    segment; :meth:`WordExpander._finish` then reads the list in visibly
    separate passes (field-split → glob → join).

    Attributes:
        text: the expanded text of this segment, in word order.
        quoted: True when the segment came from quoted context (a quoted
            literal or a quoted expansion result). Drives the
            "all parts quoted" decision for extglob detection — quoted
            text never contributes globbing.
        splittable: True only for the text of an UNQUOTED expansion
            result — the sole text POSIX field-splitting may break apart
            (literal/quoted text merges with neighbors but never splits).
        glob_eligible: True when this segment contributes UNescaped glob
            metacharacters from unquoted context (an unquoted literal
            whose globs were all escaped is NOT eligible; quoted text is
            never eligible). Drives the globbing pass.
    """
    text: str
    quoted: bool
    splittable: bool = False
    glob_eligible: bool = False


@dataclass
class _WalkState:
    """Mutable accumulator for one composite/unquoted word walk."""
    #: The expanded segments, in word order; turned into the final
    #: result by _finish() over explicit passes.
    segments: List[ExpandedSegment] = field(default_factory=list)
    #: True once any expansion (quoted or not) has been seen — gates the
    #: leading-tilde rule (tilde expands only on the very first part,
    #: before any expansion). Walk-time only; not used by _finish().
    has_expansion: bool = False
    # --- assignment-shaped word (NAME=...) value-tilde tracking ---
    #: The unquoted ``NAME=``/``NAME+=`` prefix, or None when the word is
    #: not assignment-shaped (or the policy disables assignment_tilde).
    assign_prefix: Optional[str] = None
    assign_seen: int = 0    # chars of assign_prefix consumed so far
    value_len: int = 0      # value chars emitted before the current part
    prev_char: str = ''     # last unquoted-literal char ('' after others)

    # -- derived word-level views over the segment list (no separate
    #    bookkeeping: each is computed from the segments on demand) --

    @property
    def has_unquoted_expansion(self) -> bool:
        """Any unquoted-expansion text present (the only splittable text)."""
        return any(s.splittable for s in self.segments)

    @property
    def has_unquoted_glob(self) -> bool:
        """Any segment contributes unescaped unquoted glob metacharacters."""
        return any(s.glob_eligible for s in self.segments)

    @property
    def all_parts_quoted(self) -> bool:
        """No unquoted segment was emitted (gates extglob detection)."""
        return all(s.quoted for s in self.segments)
