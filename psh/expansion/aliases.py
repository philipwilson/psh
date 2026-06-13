#!/usr/bin/env python3
"""Alias management for psh."""

from typing import Dict, List, Optional, Set, Tuple

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

    def expand_aliases(self, tokens: List[Token]) -> List[Token]:
        """Expand aliases in token list."""
        if not self.aliases:
            return tokens

        result: List[Token] = []
        i = 0

        while i < len(tokens):
            token = tokens[i]

            # Only expand WORD tokens at command position
            if (token.type == TokenType.WORD and
                self._is_command_position(result) and
                token.value not in self.expanding):

                alias_value = self.aliases.get(token.value)
                if alias_value:
                    # Prevent recursive expansion
                    self.expanding.add(token.value)

                    try:
                        # Tokenize the alias value
                        alias_tokens = tokenize(alias_value)
                        # Remove EOF token
                        alias_tokens = [t for t in alias_tokens if t.type != TokenType.EOF]

                        # Recursively expand aliases in replacement
                        expanded = self.expand_aliases(alias_tokens)

                        # Check for trailing space (enables next word expansion)
                        check_next = alias_value.endswith(' ')

                        result.extend(expanded)
                        i += 1

                        # If trailing space and there's a next token, it might be expandable
                        if check_next and i < len(tokens) and tokens[i].type == TokenType.WORD:
                            # The next word should be treated as command position
                            next_token = tokens[i]
                            if next_token.value not in self.expanding:
                                next_alias = self.aliases.get(next_token.value)
                                if next_alias:
                                    # Expand the next token too
                                    self.expanding.add(next_token.value)
                                    try:
                                        next_tokens = tokenize(next_alias)
                                        next_tokens = [t for t in next_tokens if t.type != TokenType.EOF]
                                        next_expanded = self.expand_aliases(next_tokens)
                                        result.extend(next_expanded)
                                        i += 1
                                    finally:
                                        self.expanding.remove(next_token.value)
                                    continue
                    finally:
                        self.expanding.remove(token.value)
                else:
                    result.append(token)
                    i += 1
            else:
                result.append(token)
                i += 1

        return result

    def _is_command_position(self, tokens: List[Token]) -> bool:
        """Check if current position is a command position."""
        # Command position is:
        # - Start of input
        # - After pipe, semicolon, &&, ||, &

        if not tokens:
            return True

        # Skip trailing whitespace tokens if any
        for i in range(len(tokens) - 1, -1, -1):
            token = tokens[i]
            if token.type in (TokenType.PIPE,
                            TokenType.SEMICOLON,
                            TokenType.AND_AND,
                            TokenType.OR_OR,
                            TokenType.AMPERSAND):
                return True
            elif token.type in (TokenType.WORD, TokenType.STRING):
                # If we hit a word or string, we're not at command position
                return False

        # If we only saw redirections or other tokens, we're at command position
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

    def save_to_file(self, filename: str) -> None:
        """Save aliases to a file."""
        with open(filename, 'w') as f:
            for name, value in sorted(self.aliases.items()):
                # Escape single quotes in value
                escaped_value = value.replace("'", "'\"'\"'")
                f.write(f"alias {name}='{escaped_value}'\n")

    def load_from_file(self, filename: str) -> List[str]:
        """Load aliases from a file. Returns list of commands to execute."""
        commands = []
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        commands.append(line)
        except FileNotFoundError:
            pass
        return commands
