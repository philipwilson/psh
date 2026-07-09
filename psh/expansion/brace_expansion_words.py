"""Word-stage brace expansion for psh.

``WordBraceExpander`` applies the textual brace-expansion algorithm
(:class:`~psh.expansion.brace_expansion.BraceExpander`) to a parsed
:class:`~psh.ast_nodes.Word`, turning one Word into the list of Words it
expands to (``{a,b}`` -> two Words). This runs at WORD-EXPANSION time —
per command, reading the LIVE ``braceexpand`` option — which is where bash
performs brace expansion, so:

- a ``set +B`` / ``shopt -uo braceexpand`` that actually RUNS updates the
  option and the NEXT command's expansion honours it, with no look-ahead
  scanner (retiring the 6-class parse-time approximation the token-stream
  expander needed — see the git history of ``brace_expansion_tokens.py``);
- a function or loop body brace-expands when it EXECUTES, not when it is
  defined/parsed;
- positions bash does not brace-expand (case subjects/patterns, here-strings)
  simply never call this, so they stay literal.

Brace expansion is purely textual and runs BEFORE parameter/command/arithmetic
expansion, so it operates on the word's literal SKELETON (unquoted literal text
is structural; quoted literals and every expansion part are opaque) and only
``{ , } ..`` in unquoted literal text are structural. Delegates the per-string
algorithm to ``BraceExpander``; this module handles the Word-level concerns
(skeleton encoding, decode, and bare-``$name`` name fusion).

This module is in mypy's checked scope; keep it clean.
"""
import copy
import re
from typing import Dict, List

from ..ast_nodes import (
    ExpansionPart,
    LiteralPart,
    VariableExpansion,
    Word,
    WordPart,
)
from ..core.assignment_utils import NAME_RE
from .brace_expansion import BraceExpander, BraceExpansionError

# The leading run a bare ``$name`` absorbs during fusion (``$v{1,2}`` -> v1/v2):
# ANY name char, since brace expansion runs before the name is looked up.
_NAME_CHARS_RE = re.compile(r'[A-Za-z0-9_]+')


class WordBraceExpander:
    """Brace expansion performed on a parsed Word (word-expansion stage).

    ``expand(word)`` returns the list of Words the input expands to — just
    ``[word]`` (unchanged, same object) when there is nothing structural to
    expand, so the overwhelmingly common brace-free word costs one scan.
    """

    def __init__(self) -> None:
        self._core = BraceExpander()

    def expand(self, word: Word) -> List[Word]:
        """Expand brace expressions in ``word`` into a list of Words."""
        # Fail loudly on a non-Word (v0.300 policy): brace expansion is the
        # first thing every field-producing path runs, so this also guards the
        # word_expander behind it. Message shares 'expects a Word' with the
        # WordExpander guard so callers see one contract.
        if not isinstance(word, Word):
            raise TypeError(
                f"WordBraceExpander.expand expects a Word AST node, got "
                f"{type(word).__name__}: {word!r}")
        parts = word.parts
        # Fast path: brace expansion is only possible when an UNQUOTED literal
        # part carries a '{'. Everything else (quoted literals, expansions) is
        # opaque, so a word without one cannot expand.
        if not any(isinstance(p, LiteralPart) and not p.quoted and '{' in p.text
                   for p in parts):
            return [word]

        # 1. Encode parts into a skeleton string + placeholder map. Only
        #    unquoted literal text is structural; quoted literals and every
        #    expansion part become a single opaque placeholder.
        placeholders: Dict[str, WordPart] = {}
        forbidden = {ord(c) for p in parts for c in str(p)}
        next_cp = [0xE000]

        def new_placeholder() -> str:
            cp = next_cp[0]
            while cp in forbidden:
                cp += 1
            if cp > 0x10FFFF:
                raise BraceExpansionError(
                    "brace expansion: no free placeholder code point")
            next_cp[0] = cp + 1
            return chr(cp)

        # Reserve the range-empty sentinel first (dodging input + placeholders),
        # so a cross-case range's backslash position survives the empty filter.
        range_empty = new_placeholder()
        self._core._range_empty = range_empty

        skeleton_chunks: List[str] = []
        for part in parts:
            if isinstance(part, LiteralPart) and not part.quoted:
                skeleton_chunks.append(part.text)
            else:
                ph = new_placeholder()
                placeholders[ph] = part
                skeleton_chunks.append(ph)
        skeleton = ''.join(skeleton_chunks)

        # 2. Expand with the shared core (sees only unquoted braces/commas). A
        #    budget overflow propagates loudly (typed BraceExpansionError).
        results = self._core._expand_braces(skeleton)
        if len(results) == 1 and results[0] == skeleton:
            return [word]

        # 3. bash drops results that expand to the empty string ({a,,b} -> a b);
        #    a range backslash carried as the sentinel is a KEPT empty word
        #    (the whole result is the sentinel, not ''), decoded to '' below.
        out: List[Word] = []
        for result in results:
            if result == '':
                continue
            out.append(self._decode(result, placeholders, range_empty))
        return out

    def _decode(self, result: str, placeholders: Dict[str, WordPart],
                range_empty: str) -> Word:
        """Turn one expanded skeleton result into a new Word.

        Structural chars become unquoted LiteralParts; each placeholder becomes
        a shallow copy of its mapped part (so results never share mutable part
        objects). The range-empty sentinel decodes to nothing.
        """
        new_parts: List[WordPart] = []
        buf: List[str] = []

        def flush() -> None:
            if buf:
                new_parts.append(LiteralPart(''.join(buf), quoted=False))
                buf.clear()

        for ch in result:
            if ch == range_empty:
                continue  # kept-empty range position contributes no text
            part = placeholders.get(ch)
            if part is None:
                buf.append(ch)  # structural char -> unquoted literal
            else:
                flush()
                new_parts.append(copy.copy(part))
        flush()

        if not new_parts:
            # A result that decoded to nothing (only the range sentinel) is a
            # KEPT empty word — bash emits the empty word for {Z..a}'s backslash.
            new_parts.append(LiteralPart('', quoted=False))

        self._fuse_bare_variables(new_parts)
        return Word(parts=new_parts)

    @staticmethod
    def _fuse_bare_variables(new_parts: List[WordPart]) -> None:
        """Fuse a trailing name-char run into a BARE ``$name`` in place.

        Brace expansion precedes parameter expansion, so ``$v{1,2}`` re-forms
        the names ``v1``/``v2``: an unquoted bare-``$name`` VariableExpansion
        immediately followed by unquoted literal name-chars absorbs that
        literal's leading ``[A-Za-z0-9_]+`` run. A brace-delimited ``${v}``
        (``braced``) and any quoted part never fuse. A NEW VariableExpansion is
        created so the shared original node (referenced by sibling result Words)
        is never mutated.
        """
        i = 0
        while i < len(new_parts) - 1:
            part = new_parts[i]
            nxt = new_parts[i + 1]
            if (isinstance(part, ExpansionPart) and not part.quoted
                    and isinstance(part.expansion, VariableExpansion)
                    and not part.expansion.braced
                    and part.expansion.name
                    and NAME_RE.match(part.expansion.name)
                    and isinstance(nxt, LiteralPart) and not nxt.quoted):
                m = _NAME_CHARS_RE.match(nxt.text)
                if m:
                    part.expansion = VariableExpansion(
                        part.expansion.name + m.group(0))
                    rest = nxt.text[m.end():]
                    if rest:
                        nxt.text = rest
                    else:
                        del new_parts[i + 1]
            i += 1
