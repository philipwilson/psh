"""Helpers for lexer-recognizer characterization tests.

Word fusion (``psh.lexer.word_fusion.fuse_words``, run as the last step of
``_post_lex``) composites adjacent word-like tokens into ONE WORD, so the public
``tokenize()`` no longer exposes the individual recognizer tokens. Lexer tests
that characterize RECOGNIZER behaviour (how the literal / operator-debris
recognizers SPLIT a word at quotes, brackets, ``$``, ``=`` …) assert on the
pre-fusion stream — the layer they actually test. The fused public shape is
frozen and verified separately by the corpus (``test_lexer_stream_corpus``) and
the base-vs-branch differential, not here.

``tokenize_unfused`` returns the normalized-but-unfused stream (recognizer
output + keyword normalization, without the fusion pass).
"""

from typing import Any, List, Mapping, Optional

from psh.lexer import _make_config
from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.modular_lexer import ModularLexer
from psh.lexer.token_types import Token


def tokenize_unfused(input_string: str,
                     shell_options: Optional[Mapping[str, Any]] = None) -> List[Token]:
    """``tokenize()`` output BEFORE word fusion (the recognizer/normalizer stream)."""
    lexer = ModularLexer(input_string, config=_make_config(shell_options))
    return KeywordNormalizer().normalize(lexer.tokenize())
