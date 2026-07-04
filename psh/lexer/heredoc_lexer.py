"""
Lexer driver with heredoc support.

Separates heredoc BODY lines from command text, then tokenizes the joined
command text in ONE ModularLexer pass — so cross-line lexer state (open
quotes, case/bracket depth, command position) survives. Earlier versions
re-lexed each physical line with a fresh lexer, which broke any multi-line
construct sharing a command with a heredoc.
"""

from typing import Any, Dict, List, Tuple

from .heredoc_collector import HeredocCollector
from .modular_lexer import ModularLexer
from .token_types import Token, TokenType

# Token types that can be ADJACENT parts of one heredoc delimiter word
# (`<<E"O"F`, `<<E$X`). Operators (`;`, `|`, redirects) end the word even when
# they touch it (`<<EOF;`), so they are excluded.
_DELIMITER_PART_TYPES = frozenset({
    TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
    TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
    TokenType.ARITH_EXPANSION, TokenType.PARAM_EXPANSION,
})


def normalize_heredoc_delimiter(parts: List[Token]) -> Tuple[str, bool]:
    """Recover a heredoc's literal delimiter text and whether it was quoted.

    The body terminator line must equal this literal exactly, and any quoting
    or backslash in the delimiter makes the body literal (no expansion). The
    delimiter may arrive as one token or several adjacent ones:

      ``<<EOF``      -> ("EOF",  False)   plain word, body expands
      ``<<\\EOF``    -> ("EOF",  True)    backslash-quoted word
      ``<<EO\\F``    -> ("EOF",  True)    backslash mid-word
      ``<<'EOF'``    -> ("EOF",  True)    fully quoted (already a STRING token)
      ``<<"E F"``    -> ("E F",  True)    quoted, may contain non-word chars
      ``<<E"O"F``    -> ("EOF",  True)    composite of adjacent WORD/STRING

    A STRING part is already unquoted by the lexer; a WORD part with a
    backslash is unescaped here. Any quoted/escaped part sets ``quoted``.
    """
    literal_parts: List[str] = []
    quoted = False
    for part in parts:
        if part.type == TokenType.STRING:
            literal_parts.append(part.value)
            quoted = True
        elif '\\' in part.value:
            literal_parts.append(part.value.replace('\\', ''))
            quoted = True
        else:
            literal_parts.append(part.value)
    return ''.join(literal_parts), quoted


class HeredocLexer:
    """Lexer with heredoc collection support.

    ``source_name`` and ``base_line`` locate the source text within its
    input source, for the unterminated-heredoc warning: the name prefixes
    the message (a script path, or "psh" for -c/stdin/eval, like bash's
    "bash:" there) and ``base_line`` is the absolute line the source's
    first line sits on (source_processor passes the buffered command's
    start line). ``warn_unterminated=False`` finalizes EOF-delimited
    heredocs silently — for TRIAL parses (the command accumulator's
    completeness oracle), which must not print a warning the execution
    pass will print again.
    """

    def __init__(self, source: str, config=None,
                 source_name: str | None = None, base_line: int = 1,
                 warn_unterminated: bool = True):
        self.source = source
        self.config = config
        self.source_name = source_name
        self.base_line = base_line
        self.warn_unterminated = warn_unterminated
        self.heredoc_collector = HeredocCollector()

    @staticmethod
    def _split_physical_lines(source: str) -> List[str]:
        """Split *source* into physical lines: ``\\n`` boundaries only, one
        trailing CR dropped per line (the line-reading layer's CRLF
        handling, so a ``-c`` string with DOS line endings behaves like a
        CRLF script file). Unlike ``str.splitlines`` this keeps a lone CR,
        FF, or VT inside a line — they are ordinary word characters, not
        line boundaries (bash agrees)."""
        lines = source.split('\n')
        if lines and lines[-1] == '':
            lines.pop()  # trailing newline is a terminator, not a new line
        return [line[:-1] if line.endswith('\r') else line for line in lines]

    def tokenize_with_heredocs(self) -> Tuple[List[Token], Dict[str, Dict[str, Any]]]:
        """Tokenize and return (tokens, heredoc_map).

        Algorithm:
        1. Classify each physical line as command text or heredoc body.
           Heredoc operators are found by tokenizing the ACCUMULATED command
           text (so quoted ``"<<EOF"`` is never a heredoc). While that text
           is mid-construct (e.g. an unclosed multi-line string), following
           lines are command continuation, like bash — bodies only start
           once the command tokenizes.
        2. Tokenize the joined command text once, with full cross-line state.

        End of input with a heredoc still pending does NOT drop it: like
        bash, the gathered lines become the body ("delimited by
        end-of-file") and a warning is printed to stderr.
        """
        command_lines: List[str] = []
        registered = 0  # heredoc operators accounted for so far

        lines = self._split_physical_lines(self.source)
        lineno = 0
        for lineno, raw_line in enumerate(lines, start=1):
            if self.heredoc_collector.has_pending_heredocs():
                completed = self.heredoc_collector.collect_line(raw_line)
                if completed and self.heredoc_collector.pending:
                    # The next pending heredoc's body gathering begins here
                    # (bash reports this line in its EOF warning).
                    self.heredoc_collector.pending[0].start_line = lineno
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
            registered = self._register_from_tokens(toks, registered, text,
                                                    lineno)

        if self.heredoc_collector.has_pending_heredocs():
            finalized = self.heredoc_collector.finalize_at_eof(max(lineno, 1))
            if self.warn_unterminated:
                self._warn_eof_delimited(finalized, max(lineno, 1))

        command_text = '\n'.join(command_lines)
        if self.source.endswith('\n'):
            command_text += '\n'

        # The single full-state tokenization of the command text.
        tokens = ModularLexer(command_text, config=self.config).tokenize()
        self._mark_heredoc_tokens(tokens)

        heredoc_map: Dict[str, Dict[str, Any]] = {}
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

    def get_heredoc_map(self) -> Dict[str, Dict[str, Any]]:
        return getattr(self, '_collected', {}).copy()

    # === Heredoc operator discovery ===

    @staticmethod
    def _delimiter_from_source(raw: str) -> Tuple[str, bool]:
        """Quote/escape-remove a raw heredoc delimiter word.

        Returns (literal_terminator, quoted). The body terminator line must
        equal the literal exactly; ANY quote or backslash in the delimiter makes
        the body literal (no expansion). An unquoted ``$`` is just a literal
        terminator char (``<<E$X`` → terminator ``E$X``, body still expands).
        """
        literal: List[str] = []
        quoted = False
        i = 0
        n = len(raw)
        while i < n:
            c = raw[i]
            if c == '\\' and i + 1 < n:
                quoted = True
                literal.append(raw[i + 1])
                i += 2
            elif c in ('"', "'"):
                quoted = True
                quote = c
                i += 1
                while i < n and raw[i] != quote:
                    if quote == '"' and raw[i] == '\\' and i + 1 < n:
                        literal.append(raw[i + 1])
                        i += 2
                    else:
                        literal.append(raw[i])
                        i += 1
                i += 1  # skip the closing quote
            else:
                literal.append(c)
                i += 1
        return ''.join(literal), quoted

    def _warn_eof_delimited(self, pending: List[Tuple[str, int]],
                            last_line: int) -> None:
        """Print bash's unterminated-heredoc warning for each finalized
        heredoc: ``NAME: line M: warning: here-document at line N delimited
        by end-of-file (wanted `DELIM')`` — M is the EOF line, N the line
        the heredoc's body gathering began (both absolute via base_line).
        """
        import sys
        name = self.source_name or 'psh'
        eof_line = self.base_line + last_line - 1
        for delimiter, start_line in pending:
            at_line = self.base_line + start_line - 1
            print(f"{name}: line {eof_line}: warning: here-document at "
                  f"line {at_line} delimited by end-of-file "
                  f"(wanted `{delimiter}')", file=sys.stderr)

    def _register_from_tokens(self, toks: List[Token], registered: int,
                              text: str, lineno: int) -> int:
        """Register heredocs for operator tokens beyond ``registered``.

        ``text`` is the command text ``toks`` were tokenized from (heredoc
        bodies already stripped), so token positions index INTO ``text`` — NOT
        ``self.source`` (whose offsets include the removed body lines).
        ``lineno`` is the current physical source line — where the newly
        registered heredocs' body gathering begins.
        """
        seen = 0
        for i, token in enumerate(toks):
            if token.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP):
                seen += 1
                if seen <= registered:
                    continue
                if (i + 1 < len(toks)
                        and toks[i + 1].type in _DELIMITER_PART_TYPES):
                    # (An operator with NO delimiter word after it — e.g.
                    # `cat << #comment`, `cat <<` at end of line — registers
                    # nothing; the parser reports the syntax error.)
                    # Recover the FULL delimiter word from the raw SOURCE span of
                    # its adjacent tokens. The delimiter is taken LITERALLY (no
                    # expansion), so a `$X`/`$(...)` in it (`<<E$X`) is part of
                    # the terminator, and a composite (`E"O"F`, `<<E$X`) spans
                    # several tokens. Reconstructing from individual token
                    # *values* drops a VARIABLE part's `$` or a STRING's quotes;
                    # the source slice preserves them. Quote/escape removal then
                    # yields the literal terminator (and whether the body is
                    # quoted = not expanded).
                    delim_toks = [toks[i + 1]]
                    j = i + 2
                    while (j < len(toks) and toks[j].adjacent_to_previous
                           and toks[j].type in _DELIMITER_PART_TYPES):
                        delim_toks.append(toks[j])
                        j += 1
                    raw = text[delim_toks[0].position:delim_toks[-1].end_position]
                    delimiter, quoted = self._delimiter_from_source(raw)
                    self.heredoc_collector.register_heredoc(
                        delimiter=delimiter,
                        strip_tabs=(token.type == TokenType.HEREDOC_STRIP),
                        quoted=quoted,
                        line=lineno, col=0,
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
                    # Dynamic attribute: its *presence* (checked via hasattr
                    # in KeywordNormalizer / the parser) is the signal that
                    # heredoc bodies are absent from the token stream, so it
                    # is intentionally not a declared Token field.
                    setattr(token, 'heredoc_key', keys[idx])
                    idx += 1


def tokenize_with_heredocs(source: str, config=None,
                           source_name: str | None = None,
                           base_line: int = 1
                           ) -> Tuple[List[Token], Dict[str, Dict[str, Any]]]:
    """Convenience function to tokenize source with heredoc support."""
    lexer = HeredocLexer(source, config=config, source_name=source_name,
                         base_line=base_line)
    return lexer.tokenize_with_heredocs()
