"""Registry system for shell builtins."""

from typing import Dict, List, Optional, Set, Type

from .base import Builtin


class BuiltinRegistry:
    """Registry for shell builtins."""

    def __init__(self):
        self._builtins: Dict[str, Builtin] = {}
        self._instances: Set[Builtin] = set()

    def register(self, builtin_class: Type[Builtin]) -> None:
        """Register a builtin class.

        Raises ``ValueError`` if the primary name or any alias is already
        claimed by another builtin. A duplicate registration is a
        programming error — two builtins fighting over one name would
        silently shadow each other (last import wins) — so we surface it at
        registration/import time rather than let it hide as a runtime shadow.
        """
        builtin = builtin_class()

        # Reject a name/alias already owned by a different builtin.
        for name in (builtin.name, *builtin.aliases):
            existing = self._builtins.get(name)
            if existing is not None:
                raise ValueError(
                    f"builtin name {name!r} is already registered by "
                    f"{type(existing).__name__}; cannot register "
                    f"{builtin_class.__name__}")

        self._instances.add(builtin)

        # Register primary name
        self._builtins[builtin.name] = builtin

        # Register aliases
        for alias in builtin.aliases:
            self._builtins[alias] = builtin

    def get(self, name: str) -> Optional[Builtin]:
        """Get a builtin by name."""
        return self._builtins.get(name)

    def has(self, name: str) -> bool:
        """Check if a builtin exists."""
        return name in self._builtins

    def all(self) -> Dict[str, Builtin]:
        """Get all registered builtins (including aliases)."""
        return self._builtins.copy()

    def names(self) -> List[str]:
        """Get all primary builtin names (excluding aliases)."""
        return sorted([builtin.name for builtin in self._instances])

    def instances(self) -> List[Builtin]:
        """Get all unique builtin instances."""
        return list(self._instances)


# Global registry instance
registry = BuiltinRegistry()


def builtin(cls: Type[Builtin]) -> Type[Builtin]:
    """Decorator to auto-register builtins."""
    registry.register(cls)
    return cls
