"""Shell expansion package."""
from .manager import ExpansionManager

__all__ = ['ExpansionManager']

# Convenience imports (not in __all__)
from .extglob import contains_extglob
