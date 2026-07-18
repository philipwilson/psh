"""Array parsers for the parser combinator implementation."""

from typing import List, cast

from ...ast_nodes import (
    ArrayAssignment,
    ArrayElementAssignment,
    ArrayInitialization,
    LiteralPart,
    Word,
    WordPart,
)
from ...lexer.token_types import Token
from ..recursive_descent.parsers.arrays import (
    _NAME_START_RE,
    _unquoted_leading_literal,
)
from ..recursive_descent.support.syntax_templates import build_subscript_spec
from ..recursive_descent.support.word_builder import WordBuilder
from .core import ParseResult
from .diagnostics import raise_committed_error
from .tokens import TokenParsers

_WORD_LIKE_TYPES = frozenset({
    'WORD', 'STRING', 'VARIABLE', 'COMMAND_SUB',
    'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION', 'PROCESS_SUB_IN', 'PROCESS_SUB_OUT',
})

class ArrayParsers:
    """Parse array assignment forms into the shared AST contract."""

    def __init__(self, token_parsers: TokenParsers):
        self.tokens = token_parsers

    def parse_word_as_word(self, tokens: List[Token], pos: int) -> ParseResult:
        """Parse one word-like shell word.

        Word fusion emits one WORD per shell word (carrying its parts), so this
        consumes a single token; an un-fused hand-built stream is handled one
        token at a time by the callers' adjacency loops.
        """
        token_result = self.tokens.word_like.parse(tokens, pos)
        if not token_result.success:
            return ParseResult(success=False, error=token_result.error, position=pos)

        token_value = token_result.value
        assert token_value is not None  # success implies a value
        quote_type = token_value.quote_type if token_value.type.name == 'STRING' else None
        return ParseResult(
            success=True,
            value=WordBuilder.build_word_from_token(token_value, quote_type),
            position=token_result.position,
        )

    @staticmethod
    def is_initializer_head(tokens: List[Token], pos: int) -> bool:
        """Return True if position starts ``name=(...)`` / ``name+=(...)``."""
        if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
            return False

        # The '(' (and a separate '='/'+=' operator) must be lexically ADJACENT
        # to the assignment head — bash only treats a glued `(` as an array
        # initializer; `a= (x)`, `a =(x)`, `a = (x)`, `a += (x)` are syntax
        # errors, not inits (finding 5b). Mirrors the recursive descent parser.
        # The name= head must also be a valid identifier in the word's UNQUOTED
        # LEADING LITERAL, so a fused quoted/expansion prefix (`"q"a=(1 2)`) is
        # NOT an init (bash syntax-errors it) — mirrors _normalize_assignment_head.
        value = _unquoted_leading_literal(tokens[pos])
        if not _NAME_START_RE.match(value):
            return False
        if value.endswith('=') or value.endswith('+='):
            return (pos + 1 < len(tokens)
                    and tokens[pos + 1].type.name == 'LPAREN'
                    and tokens[pos + 1].adjacent_to_previous)

        return (
            pos + 2 < len(tokens)
            and tokens[pos + 1].type.name == 'WORD'
            and tokens[pos + 1].value in ('=', '+=')
            and tokens[pos + 1].adjacent_to_previous
            and tokens[pos + 2].type.name == 'LPAREN'
            and tokens[pos + 2].adjacent_to_previous
        )

    @staticmethod
    def is_element_head(tokens: List[Token], pos: int) -> bool:
        """Return True if position starts an array element assignment."""
        if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
            return False

        # Classify off the UNQUOTED LEADING LITERAL with a valid identifier, so a
        # fused quoted/expansion prefix (`"q"a[0]=v`, `${v}a[0]=v`, `a[0]$x=y`)
        # is NOT an element assignment (bash runs it as a command) — mirrors
        # _normalize_assignment_head.
        value = _unquoted_leading_literal(tokens[pos])
        if not _NAME_START_RE.match(value):
            return False
        if '[' in value and ']' in value:
            if '=' in value:
                equals_pos = value.index('+=') if '+=' in value else value.index('=')
                return value.index('[') < equals_pos
            # Split head `a[i]` + `=value` requires the operator token ADJACENT
            # to `a[i]`; a space (`a[0] =v`) makes `a[0]` a command word, not an
            # element assignment (finding 5c). Mirrors the recursive descent parser.
            return (
                pos + 1 < len(tokens)
                and tokens[pos + 1].type.name == 'WORD'
                and tokens[pos + 1].adjacent_to_previous
                and (
                    tokens[pos + 1].value.startswith('=')
                    or tokens[pos + 1].value.startswith('+=')
                )
            )

        return pos + 1 < len(tokens) and tokens[pos + 1].type.name == 'LBRACKET'

    def parse_assignment(self, tokens: List[Token], pos: int) -> ParseResult[ArrayAssignment]:
        """Parse a prefix array assignment for SimpleCommand.array_assignments."""
        # ArrayInitialization / ArrayElementAssignment both subclass
        # ArrayAssignment; ParseResult is invariant, so widen explicitly.
        if self.is_initializer_head(tokens, pos):
            return cast('ParseResult[ArrayAssignment]',
                        self.parse_initialization(tokens, pos))
        if self.is_element_head(tokens, pos):
            return cast('ParseResult[ArrayAssignment]',
                        self.parse_element_assignment(tokens, pos))
        return ParseResult(success=False, error="No array assignment", position=pos)

    def parse_initialization(self, tokens: List[Token], pos: int) -> ParseResult[ArrayInitialization]:
        """Parse ``name=(...)`` / ``name+=(...)`` into ArrayInitialization."""
        head = tokens[pos]
        pos += 1

        if head.value.endswith('=') or head.value.endswith('+='):
            is_append = head.value.endswith('+=')
            name = head.value[:-2] if is_append else head.value[:-1]
        else:
            if pos >= len(tokens) or tokens[pos].type.name != 'WORD' or tokens[pos].value not in ('=', '+='):
                return ParseResult(success=False, error="Expected '=' or '+=' after array name", position=pos)
            is_append = tokens[pos].value == '+='
            name = head.value
            pos += 1

        if pos >= len(tokens) or tokens[pos].type.name != 'LPAREN':
            return ParseResult(success=False, error="Expected '(' for array initialization", position=pos)
        pos += 1

        words: List[Word] = []
        while pos < len(tokens):
            if tokens[pos].type.name == 'RPAREN':
                break
            if tokens[pos].type.name == 'NEWLINE':
                pos += 1
                continue
            if tokens[pos].type.name == 'EOF':
                raise_committed_error(tokens, pos, "Expected ')' to close array initialization")

            word_result = self.parse_word_as_word(tokens, pos)
            if not word_result.success:
                raise_committed_error(tokens, pos, "Expected array element")
            word = word_result.value
            assert word is not None  # success implies a value
            words.append(word)
            pos = word_result.position

        if pos >= len(tokens) or tokens[pos].type.name != 'RPAREN':
            raise_committed_error(tokens, pos, "Expected ')' to close array initialization")

        return ParseResult(
            success=True,
            value=ArrayInitialization(
                name=name,
                elements=[word.display_text() for word in words],
                is_append=is_append,
                words=words,
            ),
            position=pos + 1,
        )

    def parse_element_assignment(self, tokens: List[Token], pos: int) -> ParseResult[ArrayElementAssignment]:
        """Parse ``arr[index]=value`` into ArrayElementAssignment."""
        head = tokens[pos]
        pos += 1
        value = head.value
        # A word-fused element head (`a[i]=$x`, `a[0]="q"`) carries its value in
        # this token's parts; recover it from there (see _element_value_from_parts).
        # An un-fused stream (hand-built combinator test tokens) keeps the value
        # in adjacent tokens, collected by _collect_element_value.
        use_parts = False
        head_len = 0

        if '[' in value and ']' in value:
            lbracket_pos = value.index('[')
            rbracket_pos = value.index(']')
            name = value[:lbracket_pos]
            subscript = value[lbracket_pos + 1:rbracket_pos]

            if '=' in value:
                is_append = '+=' in value
                equals_pos = value.index('+=') if is_append else value.index('=')
                head_len = equals_pos + (2 if is_append else 1)
                tail = value[head_len:]
                use_parts = bool(head.parts)
            else:
                if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
                    return ParseResult(success=False, error="Expected '=' after array index", position=pos)
                op_token = tokens[pos]
                is_append = op_token.value.startswith('+=')
                tail = '' if op_token.value in ('=', '+=') else op_token.value[2 if is_append else 1:]
                pos += 1
        else:
            name = value
            if pos >= len(tokens) or tokens[pos].type.name != 'LBRACKET':
                return ParseResult(success=False, error="Expected '[' for array index", position=pos)
            pos += 1
            index_tokens = []
            while pos < len(tokens) and tokens[pos].type.name != 'RBRACKET':
                index_tokens.append(tokens[pos])
                pos += 1
            if pos >= len(tokens) or tokens[pos].type.name != 'RBRACKET':
                return ParseResult(success=False, error="Expected ']' to close array index", position=pos)
            pos += 1
            subscript = ''.join(
                f'${tok.value}' if tok.type.name == 'VARIABLE' else tok.value
                for tok in index_tokens
            )

            if pos >= len(tokens) or tokens[pos].type.name != 'WORD' or tokens[pos].value not in ('=', '+='):
                return ParseResult(success=False, error="Expected '=' or '+=' after array index", position=pos)
            is_append = tokens[pos].value == '+='
            pos += 1
            tail = ''

        if use_parts:
            value_word, value_text = self._element_value_from_parts(head, head_len)
        else:
            value_word, value_text, pos = self._collect_element_value(tokens, pos, tail)
        return ParseResult(
            success=True,
            value=ArrayElementAssignment(
                name=name,
                index=subscript,
                value=value_text,
                is_append=is_append,
                value_word=value_word,
                index_spec=build_subscript_spec(subscript),
            ),
            position=pos,
        )

    @staticmethod
    def _element_value_from_parts(head: Token, head_len: int):
        """Value (Word, text) of a word-fused element head, dropping the
        ``name[subscript]operator`` prefix (``head_len`` chars) from its parts.

        Mirrors the recursive-descent ``_element_value_from_head``: the head
        prefix and any leading literal value share the first part; expansion /
        quoted value pieces follow.
        """
        full = WordBuilder.build_word_from_token(head)
        parts = list(full.parts)
        value_parts: List[WordPart] = []
        if parts:
            first = parts[0]
            remainder = getattr(first, 'text', '')[head_len:]
            if remainder:
                value_parts.append(LiteralPart(
                    remainder, quoted=getattr(first, 'quoted', False),
                    quote_char=getattr(first, 'quote_char', None)))
            value_parts.extend(parts[1:])
        word = Word(parts=value_parts)
        return word, ''.join(str(part) for part in value_parts)

    def _collect_element_value(self, tokens: List[Token], pos: int, tail: str):
        """Collect literal tail plus adjacent value tokens into a Word."""
        parts: List[WordPart] = []
        if tail:
            parts.append(LiteralPart(tail))

        # A value token is part of the value only when lexically ADJACENT to the
        # assignment head, for BOTH a non-empty inline tail and an empty one:
        # `a[0]= v` is an empty assignment plus the separate command `v`, so the
        # following non-adjacent word is NOT consumed (finding 5c). Mirrors the
        # recursive descent parser (previously an empty tail consumed any word).
        while pos < len(tokens) and tokens[pos].type.name in _WORD_LIKE_TYPES:
            if not getattr(tokens[pos], 'adjacent_to_previous', False):
                break
            word_result = self.parse_word_as_word(tokens, pos)
            inner = word_result.value
            assert inner is not None  # success implies a value
            parts.extend(inner.parts)
            pos = word_result.position

        return Word(parts=parts), ''.join(str(part) for part in parts), pos
