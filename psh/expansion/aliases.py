#!/usr/bin/env python3
"""Alias management for psh."""

from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from ..lexer import tokenize
from ..lexer.token_types import Token, TokenType


class AliasManager:
    """Manages shell aliases and their expansion."""

    def __init__(self):
        self.aliases: Dict[str, str] = {}
        self.expanding: Set[str] = set()  # Track aliases being expanded to prevent recursion

    def define_alias(self, name: str, value: str) -> None:
        """Define or update an alias."""
        # Validate alias name
        if not self._is_valid_alias_name(name):
            raise ValueError(f"Invalid alias name: {name}")

        self.aliases[name] = value

    def undefine_alias(self, name: str) -> bool:
        """Remove an alias. Returns True if it existed."""
        if name in self.aliases:
            del self.aliases[name]
            return True
        return False

    def get_alias(self, name: str) -> Optional[str]:
        """Get alias value if exists."""
        return self.aliases.get(name)

    def has_alias(self, name: str) -> bool:
        """Check if an alias exists."""
        return name in self.aliases

    def list_aliases(self) -> List[Tuple[str, str]]:
        """Return all aliases as (name, value) pairs."""
        return list(self.aliases.items())

    def copy(self) -> 'AliasManager':
        """Create a copy of this alias manager for child shells."""
        new = AliasManager.__new__(AliasManager)
        new.aliases = self.aliases.copy()
        new.expanding = set()  # Fresh expansion-tracking for the child
        return new

    def clear_aliases(self) -> None:
        """Remove all aliases."""
        self.aliases.clear()

    def expand_aliases(self, tokens: List[Token],
                       effective: Optional[Dict[str, str]] = None,
                       shell_options: Optional[Mapping[str, Any]] = None
                       ) -> List[Token]:
        """Expand aliases on a token stream (the lex→parse-boundary transform).

        Aliases are expanded only in command position (see
        ``_is_command_position``), recursion is guarded by ``self.expanding``,
        and a value ending in a space chains expansion to the next word
        (bash semantics).

        psh deliberately diverges from bash by ALSO honouring alias
        definitions that occur EARLIER in the SAME token stream: in
        ``alias x=echo; x hi`` the later ``x`` expands. bash defers a
        definition to the next line; psh does not. This is implemented with
        an in-pass ``effective`` overlay seeded from ``self.aliases`` and
        updated as ``alias``/``unalias`` commands are seen in command
        position. The overlay is local to the call — it does NOT mutate the
        persistent table (the ``alias`` builtin still does that when it runs).
        """
        if effective is None:
            if not self.aliases:
                # Even with no aliases yet, a same-stream `alias` definition
                # could create one for a later word — but with nothing to
                # expand and no definitions to honour the common fast path is
                # to return unchanged. Only take it when there is no `alias`
                # word to interpret.
                if not any(t.type == TokenType.WORD and t.value == 'alias'
                           for t in tokens):
                    return tokens
            effective = dict(self.aliases)

        result: List[Token] = []
        i = 0
        n = len(tokens)

        while i < n:
            token = tokens[i]

            if (token.type == TokenType.WORD and
                    self._is_command_position(result)):

                # A same-stream `alias`/`unalias` definition updates the
                # in-pass overlay so later words in this stream expand.
                if token.value in ('alias', 'unalias'):
                    consumed = self._absorb_alias_command(tokens, i, effective)
                    result.extend(tokens[i:consumed])
                    i = consumed
                    continue

                alias_value = (effective.get(token.value)
                               if token.value not in self.expanding else None)
                if alias_value is not None:
                    self.expanding.add(token.value)
                    try:
                        result.extend(self._expand_value(alias_value, effective,
                                                         shell_options))
                        i += 1

                        # Trailing space chains expansion to the next word,
                        # which is then treated as command position too.
                        # Chaining is recursive: each expanded value whose
                        # own value ends in a space chains again
                        # (`alias a='x '; alias b='y '; alias c='C'; a b c`
                        # → `x y C`).
                        while (alias_value.endswith(' ') and i < n and
                               tokens[i].type == TokenType.WORD):
                            nxt = tokens[i]
                            nxt_value = (effective.get(nxt.value)
                                         if nxt.value not in self.expanding
                                         else None)
                            if nxt_value is None:
                                break
                            self.expanding.add(nxt.value)
                            try:
                                result.extend(
                                    self._expand_value(nxt_value, effective,
                                                       shell_options))
                                i += 1
                            finally:
                                self.expanding.remove(nxt.value)
                            alias_value = nxt_value
                    finally:
                        self.expanding.remove(token.value)
                else:
                    result.append(token)
                    i += 1
            else:
                result.append(token)
                i += 1

        return result

    def _expand_value(self, alias_value: str, effective: Dict[str, str],
                      shell_options: Optional[Mapping[str, Any]] = None
                      ) -> List[Token]:
        """Tokenize an alias value and recursively expand it (no EOF).

        ``shell_options`` (the live option mapping, when the caller has one)
        is threaded to ``tokenize`` so the alias VALUE is lexed in the same
        mode as the surrounding command — in particular ``set +B`` keeps
        braces in the value literal (bash: alias text joins the input stream
        and sees the same expansion settings).
        """
        alias_tokens = [t for t in tokenize(alias_value,
                                            shell_options=shell_options)
                        if t.type != TokenType.EOF]
        return self.expand_aliases(alias_tokens, effective, shell_options)

    def _absorb_alias_command(self, tokens: List[Token], start: int,
                              effective: Dict[str, str]) -> int:
        """Apply a same-stream ``alias``/``unalias`` command to ``effective``.

        ``start`` indexes the ``alias``/``unalias`` WORD. Scans its operands
        up to the next command terminator, updating the overlay so a later
        use in this same token stream expands (psh's same-line behaviour).
        Returns the index just past the consumed command (the terminator is
        left for the main loop). Never mutates the persistent table.
        """
        is_unalias = tokens[start].value == 'unalias'
        i = start + 1
        n = len(tokens)
        _terminators = (TokenType.SEMICOLON, TokenType.AMPERSAND,
                        TokenType.AND_AND, TokenType.OR_OR, TokenType.PIPE,
                        TokenType.PIPE_AND, TokenType.NEWLINE, TokenType.EOF)

        while i < n and tokens[i].type not in _terminators:
            tok = tokens[i]
            if tok.type != TokenType.WORD:
                i += 1
                continue
            name = tok.value
            if is_unalias:
                if name == '-a':
                    effective.clear()
                else:
                    effective.pop(name, None)
                i += 1
                continue

            # alias definition forms:
            #   WORD 'name=value'            (inline, possibly empty value)
            #   WORD 'name='  + STRING/WORD  (quoted value in the next token)
            if '=' in name:
                key, _, inline_val = name.partition('=')
                if not key:
                    i += 1
                    continue
                if inline_val == '' and i + 1 < n and \
                        tokens[i + 1].type in (TokenType.STRING, TokenType.WORD):
                    # `name=` followed by the value token (quoted value).
                    effective[key] = tokens[i + 1].value
                    i += 2
                else:
                    effective[key] = inline_val
                    i += 1
            else:
                # Bare name (listing form) — no definition to absorb.
                i += 1

        return i

    # Tokens after which a command word is expected (so an alias in that
    # slot IS expanded). Mirrors bash: start of input plus the separators
    # and reserved words that introduce a new command.
    _COMMAND_POSITION_AFTER = frozenset({
        # Command separators / list operators
        TokenType.SEMICOLON,
        TokenType.AMPERSAND,
        TokenType.AND_AND,
        TokenType.OR_OR,
        TokenType.PIPE,
        TokenType.PIPE_AND,
        TokenType.NEWLINE,
        # Grouping that opens a command list
        TokenType.LPAREN,    # subshell body
        TokenType.LBRACE,    # brace-group body
        TokenType.RPAREN,    # case-pattern body: `pat) CMD`
        # Reserved words that introduce a command list
        TokenType.THEN,
        TokenType.ELSE,
        TokenType.ELIF,
        TokenType.DO,
        TokenType.IF,
        TokenType.WHILE,
        TokenType.UNTIL,
    })

    # Tokens after which a NAME / selector / pattern (not a command) is
    # expected, so an alias there is NOT expanded. Kept explicit rather
    # than "anything not in the command-position set" so unexpected token
    # kinds (redirections, assignments) keep the prior conservative
    # behaviour of falling through to "command position".
    _NON_COMMAND_POSITION_AFTER = frozenset({
        TokenType.WORD,            # already past the command name
        TokenType.STRING,
        TokenType.FOR,             # next token is the loop variable name
        TokenType.SELECT,
        TokenType.CASE,            # next token is the case selector word
        TokenType.FUNCTION,        # next token is the function name
        TokenType.IN,              # for/select items, case patterns
        TokenType.DOUBLE_SEMICOLON,  # next token is the next case pattern
        TokenType.SEMICOLON_AMP,
        TokenType.AMP_SEMICOLON,
    })

    def _is_command_position(self, tokens: List[Token]) -> bool:
        """Check whether the next token is in command position.

        bash only expands an alias where a command name is expected: at the
        start of input and after a command separator (``;`` ``&`` ``&&``
        ``||`` ``|`` newline), after grouping that opens a command list
        (``(`` ``{`` and a case pattern's ``)``), and after the reserved
        words that introduce a command (``then`` ``else`` ``elif`` ``do``
        ``if`` ``while`` ``until``). It does NOT expand a word that is an
        argument, a loop variable / case selector (after ``for``/``case``),
        a loop item or case pattern (after ``in``/``;;``), etc.
        """
        if not tokens:
            return True

        last = tokens[-1]
        if last.type in self._COMMAND_POSITION_AFTER:
            return True
        if last.type in self._NON_COMMAND_POSITION_AFTER:
            return False

        # Unknown token kind (e.g. a redirection target/operator): keep the
        # historical conservative default of treating it as command position.
        return True

    def _is_valid_alias_name(self, name: str) -> bool:
        """Check if alias name is valid."""
        if not name:
            return False

        # Cannot contain certain characters
        invalid_chars = ['=', '/', ' ', '\t', '\n', '|', '&', ';', '(', ')', '<', '>', '`', '$', '"', "'", '\\']
        for char in invalid_chars:
            if char in name:
                return False

        # Cannot be empty or start with a digit
        if not name or name[0].isdigit():
            return False

        # Should not be shell keywords (basic list)
        keywords = {'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done',
                   'case', 'esac', 'function', 'return', 'in'}
        if name in keywords:
            return False

        return True
