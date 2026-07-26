"""bash's KEY-rendering of a procsub body, for subscript keying ONLY (2.3 B2).

When bash keys an associative subscript containing a procsub SPELLING, the
spelling it stores is NOT the raw source text: bash reconstructs it FROM ITS
PARSE (its ``print_command``), so whitespace runs collapse, a trailing ``;``
drops, and redirects take canonical spacing — ``a[<( echo  hi ; )]=v`` keys
``<(echo hi)`` (probe-verified, bash 5.2; slot-2.3 ledger, B2 stage-1
assessment: 390-cell generated matrix).

:func:`render_procsub_body` is that rule for the COVERED construct subset —
simple-command bodies (words as spelled, redirects with bash's spacing),
pipelines, and/or lists, ``;``-joined statements, and brace groups.
It returns None for ANY other construct: that single structural predicate is
the render-vs-raw boundary. Uncovered bodies (``if``/``for``/``while``/
``case``, SUBSHELLS (bash treats glued/separated forms bimodally — see
_render_command), heredocs, ``|&``, negation, ``time``, backgrounding,
fd-moves, ``&>``) keep their RAW source spelling — the DECLARED NORMALIZATION RESIDUAL:
bash embeds its printer's multiline byte-layout for compounds (4-space
indents, per-construct breaks), which psh does not replicate (ruled carry;
both-sides pins in test_subscript_keying_conformance.py).

This renderer is OWNED BY THE KEYING SEAM (``subscript.py``). It is NOT a
general formatter: ``declare -f`` must NEVER migrate to it — bash itself
renders the two surfaces differently (probe: a subshell body is ``(echo s)``
in a key but ``( echo s )`` in ``declare -f``), so the surfaces are distinct
by bash's own behavior, not merely by implementation.
"""
from typing import TYPE_CHECKING, List, Optional

from ..ast_nodes import (
    AndOrList,
    BraceGroup,
    Pipeline,
    Program,
    SimpleCommand,
    StatementList,
    SubshellGroup,
)

if TYPE_CHECKING:
    from ..ast_nodes import Redirect

#: Redirect node types the key-render covers (word-target + fd-duplication).
_WORD_TARGET_REDIRECTS = frozenset({'<', '>', '>>'})
_DUP_REDIRECTS = frozenset({'>&', '<&'})


def render_procsub_body(program: 'Program') -> Optional[str]:
    """The bash key-rendered body text, or None when any construct is
    outside the covered subset (the ONE render-vs-raw-fallback predicate)."""
    return _render_statements(program.statements)


def _render_statements(statements) -> Optional[str]:
    parts: List[str] = []
    for st in statements:
        if not isinstance(st, AndOrList) or st.background:
            return None
        rendered = _render_and_or(st)
        if rendered is None:
            return None
        parts.append(rendered)
    if not parts:
        return None
    return '; '.join(parts)


def _render_and_or(node: AndOrList) -> Optional[str]:
    if len(node.pipelines) != len(node.operators) + 1:
        return None
    out: List[str] = []
    for i, pipeline in enumerate(node.pipelines):
        if i:
            out.append(f' {node.operators[i - 1]} ')
        rendered = _render_pipeline(pipeline)
        if rendered is None:
            return None
        out.append(rendered)
    return ''.join(out)


def _render_pipeline(node: Pipeline) -> Optional[str]:
    if node.negated or node.timed or any(node.pipe_stderr):
        return None
    out: List[str] = []
    for cmd in node.commands:
        rendered = _render_command(cmd)
        if rendered is None:
            return None
        out.append(rendered)
    if not out:
        return None
    return ' | '.join(out)


def _render_command(node) -> Optional[str]:
    if isinstance(node, SimpleCommand):
        return _render_simple(node)
    if isinstance(node, SubshellGroup):
        # UNCOVERED by ruling refinement (B2 stage-2 matrix): bash's own
        # handling is bimodal via its `((` disambiguation — a GLUED
        # subshell (`<((echo  s))`) is RAW-preserved byte-for-byte
        # (trailing `;` and spacing runs kept!), while a SEPARATED one
        # (`<( (echo s) )`) re-renders declare-f-style (`( echo s )`).
        # Raw fallback matches the glued family exactly; the separated
        # family is part of the declared normalization residual.
        return None
    if isinstance(node, BraceGroup):
        if node.redirects:
            return None
        inner = _render_statement_list(node.statements)
        return None if inner is None else f'{{ {inner}; }}'
    return None


def _render_statement_list(node: 'StatementList') -> Optional[str]:
    if not isinstance(node, StatementList):
        return None
    return _render_statements(node.statements)


def _render_simple(node: SimpleCommand) -> Optional[str]:
    if node.array_assignments:
        return None
    words = [_render_word(w) for w in node.words]
    if not words:
        return None
    for redirect in node.redirects:
        rendered = _render_redirect(redirect)
        if rendered is None:
            return None
        words.append(rendered)
    return ' '.join(words)


def _render_redirect(node: 'Redirect') -> Optional[str]:
    if node.heredoc_content is not None or node.move or node.combined:
        return None
    prefix = '' if node.fd is None else str(node.fd)
    if node.type in _WORD_TARGET_REDIRECTS and node.target is not None:
        # bash's key-render puts a SPACE before a word target (`> /dev/null`,
        # `2> e`) — spelling from target_word when present (expansion-bearing
        # targets keep their source form).
        spelled = str(node.target_word) if node.target_word is not None else node.target
        return f'{prefix}{node.type} {spelled}'
    if node.type in _DUP_REDIRECTS and node.dup_fd is not None:
        # fd duplication attaches without spaces (`2>&1`).
        return f'{prefix}{node.type}{node.dup_fd}'
    return None

def _render_word(word) -> str:
    """A word's spelling with NESTED procsub parts key-rendered recursively.

    bash renders inner spellings too: ``a[<(cat  <(echo  z))]=v`` keys
    ``<(cat <(echo z))`` (matrix nested_ps cells). An inner body outside the
    covered subset keeps its raw spelling — same residual rule as the outer.
    """
    from ..ast_nodes.words import ExpansionPart, ProcessSubstitution
    out = []
    for part in word.parts:
        if (isinstance(part, ExpansionPart)
                and isinstance(part.expansion, ProcessSubstitution)
                and part.expansion.program is not None):
            rendered = render_procsub_body(part.expansion.program)
            if rendered is not None:
                frame = '<' if part.expansion.direction == 'in' else '>'
                out.append(f'{frame}({rendered})')
                continue
        out.append(str(part))
    return ''.join(out)

