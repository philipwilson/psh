#!/usr/bin/env python3
"""Function management for Python Shell (psh)."""

from typing import Dict, List, Optional, Tuple

from ..ast_nodes import CommandList


class Function:
    """Represents a shell function definition."""
    def __init__(self, name: str, body: CommandList, readonly: bool = False,
                 redirects: Optional[List] = None):
        self.name = name
        self.body = body
        self.readonly = readonly
        # Redirections from the definition (f() { ...; } > file),
        # applied at each call (bash).
        self.redirects = redirects or []
        self.source_location = None  # Could add file:line info later


class FunctionManager:
    """Manages shell function definitions."""

    # Reserved words that cannot be used as function names
    RESERVED_WORDS = {
        'if', 'then', 'else', 'elif', 'fi',
        'while', 'until', 'do', 'done',
        'for', 'in', 'case', 'esac',
        'function', 'return', 'break', 'continue',
        'true', 'false', 'exit'
    }

    def __init__(self):
        self.functions: Dict[str, Function] = {}

    def define_function(self, name: str, body: CommandList,
                        redirects: Optional[List] = None) -> None:
        """Define or redefine a function."""
        if self._is_reserved_word(name):
            raise ValueError(f"Cannot use reserved word '{name}' as function name")

        if self._is_invalid_name(name):
            raise ValueError(f"Invalid function name '{name}'")

        # Check if function is readonly
        existing = self.functions.get(name)
        if existing and existing.readonly:
            raise ValueError(f"'{name}': readonly function")

        # Preserve readonly status if redefining
        readonly = existing.readonly if existing else False
        self.functions[name] = Function(name, body, readonly, redirects)

    def get_function(self, name: str) -> Optional[Function]:
        """Get a function by name."""
        return self.functions.get(name)

    def undefine_function(self, name: str) -> bool:
        """Remove a function. Returns True if removed, False if not found."""
        func = self.functions.get(name)
        if func and func.readonly:
            raise ValueError(f"'{name}': readonly function")
        return self.functions.pop(name, None) is not None

    def set_function_readonly(self, name: str) -> bool:
        """Set a function as readonly. Returns True if successful, False if not found."""
        func = self.functions.get(name)
        if func:
            func.readonly = True
            return True
        return False

    def is_function_readonly(self, name: str) -> bool:
        """Check if a function is readonly."""
        func = self.functions.get(name)
        return func.readonly if func else False

    def list_functions(self) -> List[Tuple[str, Function]]:
        """List all defined functions."""
        return sorted(self.functions.items())

    def clear_functions(self) -> None:
        """Remove all function definitions."""
        self.functions.clear()

    def copy(self) -> 'FunctionManager':
        """Create a shallow copy of all functions.

        Note: For now, we share AST nodes between instances since they're
        immutable once created. If we need true isolation later, we can
        implement deep copying.
        """
        new_manager = FunctionManager()
        # Shallow copy is sufficient since we don't modify AST nodes
        new_manager.functions = self.functions.copy()
        return new_manager

    def _is_reserved_word(self, name: str) -> bool:
        """Check if name is a reserved word."""
        return name in self.RESERVED_WORDS

    def _is_invalid_name(self, name: str) -> bool:
        """Check if name is invalid as a function name."""
        if not name:
            return True

        # Function names must start with letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return True

        # Rest can be letters, numbers, or underscores
        for char in name[1:]:
            if not (char.isalnum() or char == '_'):
                return True

        return False
