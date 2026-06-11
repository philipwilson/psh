"""
Lexer driver with heredoc support.

Separates heredoc BODY lines from command text, then tokenizes the joined
command text in ONE ModularLexer pass — so cross-line lexer state (open
quotes, case/bracket depth, command position) survives. Earlier versions
re-lexed each physical line with a fresh lexer, which broke any multi-line
construct sharing a command with a heredoc.
"""

from typing import Dict, List, Tuple

from .heredoc_collector import HeredocCollector
from .modular_lexer import ModularLexer
from .token_types import Token, TokenType


class HeredocLexer:
    """Lexer with heredoc collection support."""

    def __init__(self, source: str, config=None):
        self.source = source
        self.config = config
        self.heredoc_collector = HeredocCollector()

    def tokenize_with_heredocs(self) -> Tuple[List[Token], Dict[str, Dict[str, any]]]:
        """Tokenize and return (tokens, heredoc_map).

        Algorithm:
        1. Classify each physical line as command text or heredoc body.
           Heredoc operators are found by tokenizing the ACCUMULATED command
           text (so quoted ``"<<EOF"`` is never a heredoc). While that text
           is mid-construct (e.g. an unclosed multi-line string), following
           lines are command continuation, like bash — bodies only start
           once the command tokenizes.
        2. Tokenize the joined command text once, with full cross-line state.
        """
        command_lines: List[str] = []
        registered = 0  # heredoc operators accounted for so far

        for raw_line in self.source.splitlines():
            if self.heredoc_collector.has_pending_heredocs():
                self.heredoc_collector.collect_line(raw_line)
                continue

            command_lines.append(raw_line)
            text = '\n'.join(command_lines)
            try:
                toks = ModularLexer(text, config=self.config).tokenize()
            except SyntaxError:
                # The accumulated command text is mid-construct (an unclosed
                # quote/expansion spans lines). Like bash, the next line is
                # command CONTINUATION — heredoc bodies only begin once the
                # command itself tokenizes completely.
                continue
            registered = self._register_from_tokens(toks, registered)

        command_text = '\n'.join(command_lines)
        if self.source.endswith('\n'):
            command_text += '\n'

        # The single full-state tokenization of the command text.
        tokens = ModularLexer(command_text, config=self.config).tokenize()
        self._mark_heredoc_tokens(tokens)

        heredoc_map: Dict[str, Dict[str, any]] = {}
        for key, info in self.heredoc_collector.collected.items():
            if info['complete']:
                heredoc_map[key] = {
                    'content': self.heredoc_collector.get_content(key),
                    'quoted': info['quoted'],
                }
        return tokens, heredoc_map

    # Backwards-compatible two-step API
    def tokenize(self) -> List[Token]:
        tokens, heredoc_map = self.tokenize_with_heredocs()
        self._collected = heredoc_map
        return tokens

    def get_heredoc_map(self) -> Dict[str, Dict[str, any]]:
        return getattr(self, '_collected', {}).copy()

    # === Heredoc operator discovery ===

    def _register_from_tokens(self, toks: List[Token], registered: int) -> int:
        """Register heredocs for operator tokens beyond ``registered``."""
        seen = 0
        for i, token in enumerate(toks):
            if token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
                seen += 1
                if seen <= registered:
                    continue
                if i + 1 < len(toks):
                    delim_tok = toks[i + 1]
                    self.heredoc_collector.register_heredoc(
                        delimiter=delim_tok.value,
                        strip_tabs=(token.type == TokenType.HEREDOC_STRIP),
                        quoted=(delim_tok.type == TokenType.STRING),
                        line=0, col=0,
                    )
        return max(seen, registered)

    def _mark_heredoc_tokens(self, tokens: List[Token]) -> None:
        """Attach collector keys to heredoc operator tokens, in order.

        KeywordNormalizer uses the presence of ``heredoc_key`` to know that
        body lines are NOT in the token stream.
        """
        keys = list(self.heredoc_collector.collected.keys())
        idx = 0
        for token in tokens:
            if token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
                if idx < len(keys):
                    token.heredoc_key = keys[idx]
                    idx += 1


def tokenize_with_heredocs(source: str, config=None) -> Tuple[List[Token], Dict[str, Dict[str, any]]]:
    """Convenience function to tokenize source with heredoc support."""
    lexer = HeredocLexer(source, config=config)
    return lexer.tokenize_with_heredocs()
