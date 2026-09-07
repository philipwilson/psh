"""The ONE rule for expanding a PATTERN word.

A *pattern word* is a Word the shell expands and then matches against, rather
than executing or assigning: the patterns of a ``case`` item, and the right
hand operand of ``[[ x == pat ]]`` / ``[[ x != pat ]]`` / ``[[ x =~ re ]]``.
Bash gives all of them the same word expansion — tilde, parameter, command and
arithmetic expansion plus quote removal, with NO field splitting and NO
pathname expansion — and then reads the result as a pattern in which the text
that was QUOTED matches literally and the text that was not keeps its
metacharacter power.

Before v0.787.0 each of those sites walked the Word itself, and the ``case``
walker was the one that forgot tilde expansion, so a pattern bash matched
silently took the ``*)`` branch instead (C042)::

    env HOME=/h/me psh -c 'case $HOME in ~) echo tilde;; *) echo other;; esac'
    # bash 5.3.15: tilde     psh <= v0.786.0: other

:func:`expand_pattern_word` is now that single walker. The tilde PLACEMENT
rule is not reimplemented here: it is driven through the same
``WordExpander.tilde_walk_begin`` / ``tilde_apply_unquoted_literal`` state
machine the ordinary command-word engine uses, so a pattern word and a command
word agree on every tilde form — the leading prefix (``~``, ``~/x``, ``~+``,
``~-``, ``~user``, bounded at the first unquoted ``/`` or ``:``) and the
assignment-shaped value tilde after the first ``=`` and each later ``:``
(``case "x=$HOME" in x=~)`` matches in bash).

The sibling for the ``${var#pat}`` family lives in ``expansion/operands.py``
(``_expand_pattern_operand``): the parser hands those operators a raw operand
STRING, not a Word, so they cannot consume this function. Both paths share the
tilde boundary and expansion rules through ``TildeExpander.prefix_end`` /
``TildeExpander.expand``, and ``tests/unit/expansion/test_pattern_words.py``
pins the two shapes to the same answers.
"""
from typing import TYPE_CHECKING, Callable, List, Optional

from ..ast_nodes import ExpansionPart, LiteralPart, ProcessSubstitution, Word

if TYPE_CHECKING:  # pragma: no cover - import cycle: manager imports this
    from .manager import ExpansionManager


def expand_pattern_word(
        word: Word,
        *,
        manager: 'ExpansionManager',
        escape: Callable[[str], str],
        dquote_literal: Optional[Callable[[str], str]] = None,
        procsub_literal: bool = False,
) -> str:
    """Expand *word* into ONE pattern string.

    Args:
        word: the pattern Word from the parser.
        manager: the :class:`~psh.expansion.manager.ExpansionManager`.
        escape: makes text match literally — ``glob_escape`` for a glob
            pattern (``case``, ``==``/``!=``), ``re.escape`` for the ``=~``
            regex source. Applied to every quoted part and to the result of
            every quoted expansion; unquoted text is passed through raw so
            its metacharacters stay live.
        dquote_literal: converts the text of a DOUBLE-QUOTED LiteralPart.
            ``[[ ]]`` needs this because its lexer keeps ``"$x"`` as the
            literal text ``$x`` inside a quoted LiteralPart, so the caller
            expands it (and strips only the double-quote escapes) itself.
            ``None`` — the ``case`` shape — takes the text as already
            quote-removed by the lexer.
        procsub_literal: keep a ``<(cmd)`` part as its own source text
            instead of running it. ``case`` patterns do not perform process
            substitution.

    Returns:
        The pattern string, ready for ``expansion/pattern.match_shell_pattern``
        (or ``re.compile`` for the ``=~`` regex operand).
    """
    we = manager.word_expander
    word, ctx = we.tilde_walk_begin(word, assignment_tilde=True)

    out: List[str] = []
    # Mirrors the field engine's ``_FieldBuilder.has_content``: the
    # word-leading tilde rule only fires while nothing has been emitted yet.
    has_content = False
    for part_index, part in enumerate(word.parts):
        if isinstance(part, LiteralPart):
            if part.quoted:
                we.tilde_note_quoted_literal(ctx)
                text = part.text
                if dquote_literal is not None and part.quote_char == '"':
                    text = dquote_literal(text)
                out.append(escape(text))
                has_content = True
                continue
            text = we.tilde_apply_unquoted_literal(
                word, part_index, part, ctx, has_content=has_content)
            out.append(text)
            has_content = has_content or bool(text)
        elif isinstance(part, ExpansionPart):
            if procsub_literal and isinstance(part.expansion,
                                              ProcessSubstitution):
                out.append(str(part.expansion))
            else:
                out.append(_expansion_text(manager, part, escape))
            we.tilde_note_expansion(ctx)
            has_content = True
    return ''.join(out)


def _expansion_text(manager: 'ExpansionManager', part: ExpansionPart,
                    escape: Callable[[str], str]) -> str:
    """One ExpansionPart's contribution to a pattern string.

    RULED TERMINAL CONSUMER: a pattern is ONE string, so a value operand's
    field vector is joined here (``as_scalar``). DOCUMENTED PRE-EXISTING
    DIVERGENCE (integrator R2.1, successor-owned): on a MULTI-FIELD pattern
    operand bash matches the FIRST FIELD only, e.g. ``set -- a b; case a in
    ${x:-"$@"})`` matches in bash and not in psh. The join RESTORES the
    historical behaviour exactly — it neither creates nor fixes that
    divergence, which is pinned both-sides.
    """
    from .operands import DQ_WORD, OperandValue

    expanded = manager.expand_expansion(
        part.expansion, quote_ctx=DQ_WORD if part.quoted else None)
    if isinstance(expanded, OperandValue):
        expanded = expanded.as_scalar()
    return escape(expanded) if part.quoted else expanded
