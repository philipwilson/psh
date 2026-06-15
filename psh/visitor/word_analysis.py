"""Structured inspection of the Word AST for the analysis visitors.

The analysis visitors (enhanced validator, linter, security) historically
extracted variable references and classified words by regexing the *rendered*
argument string (``word.display_text()``). That is architecturally behind the
runtime: since v0.120.0 ``Word.parts`` — ``LiteralPart``/``ExpansionPart``
carrying ``VariableExpansion``/``ParameterExpansion``/``CommandSubstitution``/
``ArithmeticExpansion`` plus per-part quote flags — is the authoritative model.

This module provides one structured layer over those parts so the visitors can
ask *what does this word reference* and *what kind of word is this* without
re-deriving quoting or expansion syntax from strings. The canonical ``Word``
properties (``is_quoted``, ``has_unquoted_expansion``, ``is_variable_expansion``,
...) are reused, never re-implemented here.

A small string-based fallback survives ONLY for content the part model leaves as
an unparsed string: the *operator word* of a parameter expansion
(``${FOO:-$BAR}`` stores ``$BAR`` in ``ParameterExpansion.word`` as raw text) and
any visitor entry point that still receives a legacy/manually-constructed Word
with no parts. Both are documented at their call sites.

Intended library surface: the ``has_*`` predicates (``has_command_substitution``,
``has_arithmetic_expansion``, ``has_parameter_expansion``,
``has_unquoted_variable_expansion``, ...), ``referenced_variable_names`` and the
``is_*`` classifiers form a stable structured-Word-analysis API for the analysis
visitors. Not every predicate currently has a production caller — they are kept
as a coherent, tested set so a new analysis visitor can ask these questions
without re-deriving them from rendered strings (rather than each visitor growing
its own ad-hoc string checks, the original problem this module solved).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple, Type, Union

from ..ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    Expansion,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    VariableExpansion,
    Word,
)

# Operators whose presence means a parameter expansion supplies a value when the
# variable is unset/empty, so a reference to it should NOT warn "undefined".
_DEFAULTING_OPERATORS = (":-", ":=")

# A bare ``$name`` / ``${name...}`` reference embedded in raw operator-word text.
# Used only by the string fallback (operator words, legacy part-less words).
_VAR_REF_RE = re.compile(
    r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)(\[[^]]*\])?([^}]*)\})"
)


@dataclass(frozen=True)
class VariableReference:
    """A single variable reference discovered structurally in a Word.

    Attributes:
        name: The bare variable name (no ``$``, no ``{}``, no ``[index]``).
        quoted: True if the reference is inside a quoted part.
        braced: True if written ``${...}`` (parameter expansion) rather than ``$x``.
        is_array_subscript: True if written with a subscript (``${a[i]}``/``$a[i]``).
        has_default: True if a ``:-``/``:=`` operator supplies a default value.
        part: The ``ExpansionPart`` this reference came from (None for fallback
            references parsed out of raw operator-word/legacy strings).
    """

    name: str
    quoted: bool = False
    braced: bool = False
    is_array_subscript: bool = False
    has_default: bool = False
    part: Optional[ExpansionPart] = None


def _split_name_and_subscript(raw: str) -> tuple[str, bool]:
    """Split a variable name that may carry an inline subscript.

    ``VariableExpansion``/``ParameterExpansion`` store the parameter with any
    ``[index]`` subscript folded into the name (``${a[@]}`` →
    ``VariableExpansion('a[@]')``). Return ``(bare_name, had_subscript)``.
    """
    bracket = raw.find("[")
    if bracket == -1:
        return raw, False
    return raw[:bracket], True


def _expansion_has_default(expansion: ParameterExpansion) -> bool:
    """True if a parameter expansion's operator supplies a default value."""
    op = expansion.operator
    return op in _DEFAULTING_OPERATORS


def iter_variable_references(word: Word) -> Iterator[VariableReference]:
    """Yield the variable references in a Word, read from its parts.

    Covers ``$x`` (``VariableExpansion``) and ``${...}`` (``ParameterExpansion``)
    expansion parts. Command/arithmetic/process substitutions are not variable
    references and are skipped (their internal variables live in re-parseable
    sub-command text, not in this word's reference surface).

    The operator word of a parameter expansion (``${FOO:-$BAR}`` — ``$BAR`` is
    raw text in ``.word``) is scanned with the string fallback so nested refs
    are still reported.
    """
    for part in word.parts:
        if not isinstance(part, ExpansionPart):
            continue
        exp = part.expansion
        if isinstance(exp, VariableExpansion):
            name, had_sub = _split_name_and_subscript(exp.name)
            if name:
                yield VariableReference(
                    name=name,
                    quoted=part.quoted,
                    braced=False,
                    is_array_subscript=had_sub,
                    has_default=False,
                    part=part,
                )
        elif isinstance(exp, ParameterExpansion):
            name, had_sub = _split_name_and_subscript(exp.parameter)
            if name:
                yield VariableReference(
                    name=name,
                    quoted=part.quoted,
                    braced=True,
                    is_array_subscript=had_sub,
                    has_default=_expansion_has_default(exp),
                    part=part,
                )
            # Nested references inside the operator word (${FOO:-$BAR}) are raw
            # text in the part model; recover them with the string fallback.
            if exp.word:
                for ref in iter_variable_references_in_text(exp.word):
                    yield VariableReference(
                        name=ref.name,
                        quoted=part.quoted,
                        braced=ref.braced,
                        is_array_subscript=ref.is_array_subscript,
                        has_default=ref.has_default,
                        part=part,
                    )


def iter_variable_references_in_text(text: str) -> Iterator[VariableReference]:
    """String fallback: scan raw text for ``$name`` / ``${name...}`` references.

    Used ONLY for content the Word part model leaves unparsed — parameter
    operator words (``${x:-$y}``) and legacy/manually-built words that lack
    parts. Prefer :func:`iter_variable_references` for real Word nodes.
    """
    if not text:
        return
    for match in _VAR_REF_RE.finditer(text):
        if match.group(1):  # $name
            yield VariableReference(name=match.group(1), braced=False)
        else:  # ${name...}
            name = match.group(2)
            had_sub = match.group(3) is not None
            tail = match.group(4) or ""
            has_default = any(op in tail for op in _DEFAULTING_OPERATORS)
            yield VariableReference(
                name=name,
                braced=True,
                is_array_subscript=had_sub,
                has_default=has_default,
            )


def referenced_variable_names(word: Word) -> List[str]:
    """The bare names of every variable referenced in *word* (in order)."""
    return [ref.name for ref in iter_variable_references(word)]


# --- word classification -------------------------------------------------

def is_pure_literal(word: Word) -> bool:
    """True if the word is only literal text (no expansions at all)."""
    return not word.has_expansion_parts


def _has_expansion_of(
    word: Word, kind: Union[Type[Expansion], Tuple[Type[Expansion], ...]]
) -> bool:
    return any(
        isinstance(p, ExpansionPart) and isinstance(p.expansion, kind)
        for p in word.parts
    )


def has_command_substitution(word: Word) -> bool:
    """True if the word contains a ``$(...)`` / backtick command substitution."""
    return _has_expansion_of(word, CommandSubstitution)


def has_arithmetic_expansion(word: Word) -> bool:
    """True if the word contains a ``$((...))`` arithmetic expansion."""
    return _has_expansion_of(word, ArithmeticExpansion)


def has_parameter_expansion(word: Word) -> bool:
    """True if the word contains a ``${...}`` parameter expansion."""
    return _has_expansion_of(word, ParameterExpansion)


def has_variable_reference(word: Word) -> bool:
    """True if the word references any variable (``$x`` or ``${...}``)."""
    return _has_expansion_of(word, (VariableExpansion, ParameterExpansion))


def is_arithmetic_only(word: Word) -> bool:
    """True if the word is a single arithmetic expansion (``$((...))``).

    Arithmetic expansion is not a *variable* expansion; classifying it as an
    "unquoted variable expansion" (word-split risk) is a false positive — bash
    does not word-split a bare ``$((expr))`` result.
    """
    return (
        len(word.parts) == 1
        and isinstance(word.parts[0], ExpansionPart)
        and isinstance(word.parts[0].expansion, ArithmeticExpansion)
    )


def has_unquoted_variable_expansion(word: Word) -> bool:
    """True if the word has an unquoted ``$var``/``${...}`` (word-split risk).

    Structured replacement for the old ``has_unquoted_expansion(word, arg)``
    that tested ``'$' in arg``. Command/arithmetic/process substitutions are
    intentionally excluded here — only *variable* expansions are subject to the
    word-splitting warning this predicate backs.
    """
    return any(
        isinstance(p, ExpansionPart)
        and not p.quoted
        and isinstance(p.expansion, (VariableExpansion, ParameterExpansion))
        for p in word.parts
    )


def has_unquoted_expansion_of_any_kind(word: Word) -> bool:
    """True if the word has any unquoted expansion part (the canonical sense).

    Thin pass-through to :attr:`Word.has_unquoted_expansion`; named here so
    visitors can use one import surface for word analysis.
    """
    return word.has_unquoted_expansion


def contains_metacharacters_in_unquoted_expansion(word: Word) -> bool:
    """True if an unquoted expansion part is adjacent to shell metacharacters.

    Backs the command-injection check: a literal metacharacter (``;``, ``|``,
    ``&``, backtick) sitting in the same (unquoted) word as a ``$``-expansion
    is the classic injection-via-unquoted-arg shape. Reads the parts directly
    rather than scanning the rendered string.
    """
    if not has_unquoted_variable_expansion(word) and not _has_expansion_of(
        word, (CommandSubstitution, ArithmeticExpansion)
    ):
        return False
    metachars = {";", "|", "&", "`"}
    for part in word.parts:
        if isinstance(part, LiteralPart) and not part.quoted:
            if any(c in metachars for c in part.text):
                return True
    return False
