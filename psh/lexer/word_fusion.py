"""Word fusion: collapse adjacent word-like tokens into one WORD-with-parts.

Historically the lexer emitted MANY tokens per shell word — a plain ``WORD``
for the literal run, then a separate ``STRING`` / ``VARIABLE`` / ``COMMAND_SUB``
/ ... token for every quote or expansion — and the PARSER re-assembled the
adjacent run into one composite :class:`~psh.ast_nodes.Word` (via the now-retired
``TokenStream.peek_composite_sequence``).

This module moves that assembly into the lexer's post-processing pass
(``psh.lexer._post_lex``, BEFORE keyword normalization). A maximal run of
adjacent word-like tokens (``adjacent_to_previous`` True after the first) is
fused into a single ``WORD`` token whose ``parts`` list carries one
:class:`~psh.lexer.token_parts.TokenPart` per constituent piece, so the parser
sees one token per shell word and never re-assembles.

Running fusion FIRST realizes the complete-lexical-word invariant (campaign
S1): word boundaries are fixed by metacharacters alone — exactly bash's word
rule — and only then does the KeywordNormalizer decide reserved words, on
COMPLETE words. A keyword spelling adjacent to an expansion or quote
(``then$x``, ``then""``) therefore fuses into one plain WORD and is never a
keyword, matching bash's syntax-error behavior for glued keyword prefixes.

``sub_token_to_parts`` is the per-token half (a word-like token → the
TokenPart(s) it contributes); it mirrors the per-token dispatch of the old
``WordBuilder.build_composite_word`` so that mapping the fused parts through
``WordBuilder.token_part_to_word_part`` reproduces the identical Word AST.
"""

from typing import List

from .token_parts import TokenPart
from .token_types import Token, TokenType

# The single canonical set of word-like token kinds that fuse into one word.
# This is exactly the set the parser's peek_composite_sequence used (minus the
# emit-dead PARAM_EXPANSION), and the parser-side WORD_LIKE sets are pointed at
# it once fusion lands. Keeping it here (the lexer, where fusion now happens)
# makes it the one place the membership is decided.
WORD_LIKE_TYPES = frozenset({
    TokenType.WORD,
    TokenType.STRING,
    TokenType.VARIABLE,
    TokenType.COMMAND_SUB,
    TokenType.COMMAND_SUB_BACKTICK,
    TokenType.ARITH_EXPANSION,
    TokenType.PROCESS_SUB_IN,
    TokenType.PROCESS_SUB_OUT,
    TokenType.LBRACKET,
    TokenType.RBRACKET,
})


def sub_token_to_parts(token: Token) -> List[TokenPart]:
    """The TokenPart(s) one word-like token contributes to a fused word.

    The mapping mirrors ``WordBuilder.build_composite_word``'s per-token
    dispatch so the fused word's parts, mapped via
    ``WordBuilder.token_part_to_word_part``, build the same Word AST the parser
    built from the un-fused adjacent tokens:

    * A ``STRING`` is handled exactly as ``build_composite_word`` handled it: a
      double-quoted string with inner expansions is FLATTENED into its parts
      (they carry per-part quote context); every other string (single-quoted,
      ANSI-C ``$'...'``, plain ``"..."`` without expansions, empty ``""``)
      becomes ONE literal part from the token value + the token's OUTER
      quote_type — the part-level quote_type differs (``'`` vs the token's
      ``$'``), so the token value/quote must be used, not the spliced part.
    * Any EOF-truncated expansion (``$(`` / ``${`` / ``$((``) carries its
      ``*_unclosed`` marker part and is spliced verbatim so the unclosed check
      still fires after fusion.
    * A part-less standalone expansion token (``$x``, ``${x}``, ``$(cmd)``,
      ``$((e))``, `` `cmd` ``, ``<(cmd)`` / ``>(cmd)``) is re-expressed as one
      expansion TokenPart. ``VARIABLE`` keeps the token's stripped name form
      (``x`` or ``{v}``) under etype ``variable``; the shared name classifier
      then maps a simple braced name to VariableExpansion(braced=True) exactly
      as the standalone/composite path does. Command/arith/backtick carry the
      full source under their named etype. Process substitution has no
      quote-embedded form, so it uses the fresh ``process_in`` / ``process_out``
      etypes ``_parse_token_part_expansion`` now understands.
    * Anything else (plain ``WORD``, bare ``[`` / ``]``) becomes one literal
      TokenPart from the token value.
    """
    ttype = token.type
    value = token.value

    if ttype == TokenType.STRING:
        # Mirror build_composite_word: flatten a double-quoted string only when
        # it has inner expansions; otherwise one literal from value + outer qt.
        if token.quote_type == '"' and any(
                getattr(p, 'is_expansion', False) for p in token.parts):
            return list(token.parts)
        return [TokenPart(value=value, quote_type=token.quote_type)]

    # A non-string token that carries parts is an EOF-truncated expansion whose
    # part holds the *_unclosed marker the parser keys off — splice verbatim.
    if token.parts:
        return list(token.parts)

    if ttype == TokenType.VARIABLE:
        # Keep the token's stripped name form ('x' or '{v}'); the 'variable'
        # etype classifier handles simple-vs-braced (braced -> braced=True).
        return [TokenPart(value=value, is_variable=True, is_expansion=True,
                          expansion_type='variable')]

    if ttype == TokenType.COMMAND_SUB:
        return [TokenPart(value=value, is_expansion=True,
                          expansion_type='command')]

    if ttype == TokenType.COMMAND_SUB_BACKTICK:
        return [TokenPart(value=value, is_expansion=True,
                          expansion_type='backtick')]

    if ttype == TokenType.ARITH_EXPANSION:
        return [TokenPart(value=value, is_expansion=True,
                          expansion_type='arithmetic')]

    if ttype == TokenType.PROCESS_SUB_IN:
        return [TokenPart(value=value, is_expansion=True,
                          expansion_type='process_in')]

    if ttype == TokenType.PROCESS_SUB_OUT:
        return [TokenPart(value=value, is_expansion=True,
                          expansion_type='process_out')]

    # Plain WORD, bare '[' / ']', or any other value carried verbatim.
    return [TokenPart(value=value)]


def _fuse_run(run: List[Token], source: str) -> Token:
    """Fuse a run (len>=2) of adjacent word-like tokens into one WORD token.

    The fused token's ``value`` is the source lexeme it spans (a Phase-C span
    payoff — it round-trips ``source[position:end_position]``, unlike the
    per-sub-token values which drop quotes/``$``); its ``parts`` concatenate
    each sub-token's contribution. Operator-token fields (``fd``/``var_fd``/
    ``combined_redirect``/``heredoc_id``/``array_init``) are never carried by a
    word run, so they stay at their defaults.
    """
    start = run[0].position
    end = run[-1].end_position
    parts: List[TokenPart] = []
    for tok in run:
        parts.extend(sub_token_to_parts(tok))
    return Token(
        type=TokenType.WORD,
        value=source[start:end],
        position=start,
        end_position=end,
        quote_type=None,
        line=run[0].line,
        column=run[0].column,
        adjacent_to_previous=run[0].adjacent_to_previous,
        is_keyword=False,
        parts=parts,
    )


def fuse_words(tokens: List[Token], source: str) -> List[Token]:
    """Collapse each maximal run of adjacent word-like tokens into one WORD.

    This is the lexer-stage relocation of the parser's ``peek_composite_sequence``:
    a maximal run of word-like tokens (:data:`WORD_LIKE_TYPES`) where every token
    after the first is ``adjacent_to_previous`` becomes a single WORD carrying
    the run's parts, so the parser sees one token per shell word.

    Runs of length 1 are left untouched — a standalone ``STRING`` / ``VARIABLE`` /
    ``COMMAND_SUB`` / bare ``[`` keeps its kind (the parser's single-token word
    build handles those unchanged). Fusion is SUPPRESSED inside ``(( ... ))`` and
    C-style ``for (( ; ; ))`` headers (tracked by ``DOUBLE_LPAREN`` /
    ``DOUBLE_RPAREN`` depth): those interiors are consumed by
    ``collect_arithmetic_expression``, never composited, so fusing there would
    change the reconstructed arithmetic expression (e.g. ``(( a["x"] ))``).
    """
    result: List[Token] = []
    i = 0
    n = len(tokens)
    arith_depth = 0
    while i < n:
        tok = tokens[i]
        if tok.type == TokenType.DOUBLE_LPAREN:
            arith_depth += 1
            result.append(tok)
            i += 1
            continue
        if tok.type == TokenType.DOUBLE_RPAREN:
            arith_depth = max(0, arith_depth - 1)
            result.append(tok)
            i += 1
            continue
        if arith_depth == 0 and tok.type in WORD_LIKE_TYPES:
            j = i + 1
            while (j < n and tokens[j].type in WORD_LIKE_TYPES
                   and tokens[j].adjacent_to_previous):
                j += 1
            if j - i >= 2:
                result.append(_fuse_run(tokens[i:j], source))
                i = j
                continue
        result.append(tok)
        i += 1
    return result
