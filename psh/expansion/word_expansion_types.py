"""Data model for Word expansion: the policy table and the field IR.

These are the value types the Word-expansion engine (``word_expander.py``)
operates on, separated from the engine itself:

- :class:`WordExpansionPolicy` and its named instances name what each
  expansion context permits (the three axes ``split``/``glob``/
  ``assignment_tilde``). Callers across the codebase import the named
  policies to say what context they are expanding in.
- :class:`FieldRun`, :class:`ExpandedField` and :class:`ExpandedWord` are the
  field IR the engine builds: a word expands to zero-or-more explicit
  ``ExpandedField`` values, each an ordered sequence of homogeneous-protection
  :class:`FieldRun`s. This representation keeps shell field boundaries,
  per-character glob protection, and split eligibility ALIVE through field
  splitting and pathname generation, instead of flattening to a
  ``str``/``list[str]`` before those passes run (reappraisal #20 H5/H6).

This module is pure data (no shell or AST dependencies); keep it that way.
"""
import enum
from dataclasses import dataclass, field
from typing import List


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

#: The subject word of a ``case`` statement (``case WORD in``). bash
#: applies tilde, parameter, command and arithmetic expansion plus quote
#: removal, but NO word splitting and NO pathname expansion — a
#: single-quoted subject stays literal, ``case ~ in`` expands the leading
#: tilde, and ``case a:~ in`` keeps the ``~`` (only a LEADING tilde
#: expands, not a value-tilde after ``:`` — probed against bash 5.2, the
#: one axis that separates this from an assignment value).
CASE_SUBJECT = WordExpansionPolicy(
    split=False, glob=False, assignment_tilde=False)


class Protection(enum.Enum):
    """Whether glob metacharacters in a :class:`FieldRun` act or stay literal.

    ``ACTIVE`` runs come from unquoted, unescaped text (an unquoted literal or
    an unquoted expansion result); their ``*``/``?``/``[`` act as pathname
    patterns. ``PROTECTED`` runs come from quoted or backslash-escaped text;
    their metacharacters are literal. Runs are homogeneous by protection, so a
    mixed word such as ``a\\*b*`` keeps the escaped ``*`` PROTECTED while the
    trailing ``*`` stays ACTIVE — the fix for #20 H6 (word-wide protection).
    """
    ACTIVE = enum.auto()
    PROTECTED = enum.auto()


class Split(enum.Enum):
    """Whether a :class:`FieldRun` may be broken on IFS.

    ``IFS_ELIGIBLE`` marks the text of an UNQUOTED expansion result — the sole
    text POSIX field splitting may break apart. ``NEVER`` marks literal and
    quoted text, which merges with neighbours into one field but is never split
    (``pre\\ post$x`` keeps ``pre post`` whole even with IFS spaces).
    """
    NEVER = enum.auto()
    IFS_ELIGIBLE = enum.auto()


@dataclass(frozen=True, slots=True)
class FieldRun:
    """One homogeneous-protection run of expanded text within a field.

    A run carries the two facts every later pass needs kept per-character:
    :class:`Protection` (does globbing treat this run's metacharacters as
    patterns) and :class:`Split` (may IFS splitting break this run). ``origin``
    is a provenance tag for debugging and guards only — never a decision input.

    Runs are the atoms the field-splicing algebra moves: field splitting slices
    ``IFS_ELIGIBLE`` runs and edge-joins ``NEVER`` runs; pathname generation
    passes ``ACTIVE`` run text into the glob pattern raw and bracket-escapes
    ``PROTECTED`` metacharacters.
    """
    text: str
    protection: Protection
    split: Split
    origin: str = 'literal'

    @property
    def is_protected(self) -> bool:
        return self.protection is Protection.PROTECTED

    @property
    def is_splittable(self) -> bool:
        return self.split is Split.IFS_ELIGIBLE


@dataclass(slots=True)
class ExpandedField:
    """One field of an expanded word: an ordered sequence of protection runs.

    An empty ``runs`` list is one explicit empty field (e.g. ``"$x"`` with
    ``x`` unset — one empty argument). Whether a word elides entirely versus
    contributes one empty field is a property of :class:`ExpandedWord`, not of
    this type.
    """
    runs: List[FieldRun] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The field's characters (quote removal already happened per run)."""
        return ''.join(r.text for r in self.runs)

    def add(self, run: FieldRun) -> None:
        self.runs.append(run)


@dataclass(slots=True)
class ExpandedWord:
    """The result of expanding one Word: zero or more explicit fields.

    An empty ``fields`` list means the word elided entirely — an unquoted
    expansion that produced no characters (``$unset`` alone). A single field
    with empty runs is one explicit empty field. Materialization
    (``WordExpander.materialize``) is the sole terminal boundary that turns
    this back into ``argv`` strings, after field splitting and globbing.
    """
    fields: List[ExpandedField] = field(default_factory=list)
