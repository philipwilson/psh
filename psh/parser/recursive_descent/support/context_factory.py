"""Factory functions for creating parser contexts."""

from typing import List, Optional

from ....lexer.keyword_normalizer import KeywordNormalizer
from ....lexer.token_types import Token
from ...config import ParserConfig
from ..context import ParserContext


def create_context(tokens: List[Token],
                   config: Optional[ParserConfig] = None,
                   source_text: Optional[str] = None,
                   **kwargs) -> ParserContext:
    """Create parser context with configuration.

    Args:
        tokens: List of tokens to parse
        config: Parser configuration (creates default if not provided)
        source_text: Source text for better error messages
        **kwargs: Additional context options

    Returns:
        Configured ParserContext instance
    """
    config = config or ParserConfig()

    normalizer = KeywordNormalizer()
    normalized_tokens = normalizer.normalize(list(tokens))

    ctx = ParserContext(
        tokens=normalized_tokens,
        config=config,
        source_text=source_text,
        **kwargs
    )

    return ctx
