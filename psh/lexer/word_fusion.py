"""Word fusion: collapse adjacent word-like tokens into one WORD-with-parts.

Historically the lexer emitted MANY tokens per shell word — a plain ``WORD``
for the literal run, then a separate ``STRING`` / ``VARIABLE`` / ``COMMAND_SUB``
/ ... token for every quote or expansion — and the PARSER re-assembled the
adjacent run into one composite :class:`~psh.ast_nodes.Word` (via the now-retired
``TokenStream.peek_composite_sequence``).

This module moves that assembly into the lexer's post-processing pass
(``psh.lexer._post_lex``, after keyword normalization). A maximal run of
adjacent word-like tokens (``adjacent_to_previous`` True after the first) is
fused into a single ``WORD`` token whose ``parts`` list carries one
:class:`~psh.lexer.token_parts.TokenPart` per constituent piece, so the parser
sees one token per shell word and never re-assembles.

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
