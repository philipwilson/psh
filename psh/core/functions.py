#!/usr/bin/env python3
"""Function management for Python Shell (psh)."""

from typing import Dict, List, Optional, Tuple

from ..ast_nodes import StatementList
from .exceptions import FunctionDefinitionError


class Function:
    """Represents a shell function definition."""
    def __init__(self, name: str, body: StatementList, readonly: bool = False,
                 redirects: Optional[List] = None, exported: bool = False,
                 trace: bool = False):
        self.name = name
        self.body = body
        self.readonly = readonly
        # `export -f` attribute. psh does not serialise functions into the
        # environment for external children, so this is observable only via
        # the `export -f` / `declare -Fx` listing — but it makes the attribute
        # round-trip and matches bash's exit status.
        self.exported = exported
        # `declare -t` trace attribute: the function inherits the RETURN
        # trap (bash also inherits DEBUG) even without `set -T`.
        self.trace = trace
        # Redirections from the definition (f() { ...; } > file),
        # applied at each call (bash).
        self.redirects = redirects or []
        self.source_location = None  # Could add file:line info later


class FunctionManager:
    """Manages shell function definitions."""

    def __init__(self):
        self.functions: Dict[str, Function] = {}

    def define_function(self, name: str, body: StatementList,
                        redirects: Optional[List] = None) -> None:
        """Define or redefine a function.

        Name policy matches bash: any single word works (``my-func``,
        ``.dot``, ``f.g``, builtin names like ``true`` — functions shadow
        builtins in lookup). Reserved words are rejected by the PARSER
        (they never lex as a plain name), so the only validity check left
        here is the empty name, plus the readonly guard.
        """
        if self._is_invalid_name(name):
            raise FunctionDefinitionError(f"`{name}': not a valid function name")

        # Check if function is readonly
        existing = self.functions.get(name)
        if existing and existing.readonly:
            raise FunctionDefinitionError(f"{name}: readonly function")

        # Preserve readonly/export/trace status if redefining
        readonly = existing.readonly if existing else False
        exported = existing.exported if existing else False
        trace = existing.trace if existing else False
        self.functions[name] = Function(name, body, readonly, redirects,
                                        exported=exported, trace=trace)

    def get_function(self, name: str) -> Optional[Function]:
        """Get a function by name."""
        return self.functions.get(name)

    def undefine_function(self, name: str) -> bool:
        """Remove a function. Returns True if removed, False if not found."""
        func = self.functions.get(name)
        if func and func.readonly:
            raise FunctionDefinitionError(f"{name}: readonly function")
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

    def set_function_exported(self, name: str, exported: bool = True) -> bool:
        """Set/clear a function's export attribute (`export -f`/`export -fn`).

        Returns True if the function exists, False otherwise.
        """
        func = self.functions.get(name)
        if func:
            func.exported = exported
            return True
        return False

    def set_function_trace(self, name: str, trace: bool = True) -> bool:
        """Set/clear a function's trace attribute (`declare -ft`/`declare +t`).

        A traced function inherits the RETURN trap without `set -T` (bash).
        Returns True if the function exists, False otherwise.
        """
        func = self.functions.get(name)
        if func:
            func.trace = trace
            return True
        return False

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

    def _is_invalid_name(self, name: str) -> bool:
        """Check if name is invalid as a function name.

        bash is permissive: a function name is any non-empty word (it can
        contain ``-``, ``.``, ``/``, glob characters, ...). The lexer
        guarantees a name from real source has no whitespace; the check
        here also covers hand-built ASTs.
        """
        return not name or any(c.isspace() for c in name)
