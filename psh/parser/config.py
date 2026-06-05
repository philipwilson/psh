"""Parser configuration system for PSH.

This module provides configurable parsing behavior to support different shell
modes, compliance levels, and feature sets.
"""

from dataclasses import dataclass
from enum import Enum


class ParsingMode(Enum):
    """Different parsing modes for shell compatibility."""
    STRICT_POSIX = "strict_posix"    # Strict POSIX compliance
    BASH_COMPAT = "bash_compat"      # Bash compatibility mode
    PERMISSIVE = "permissive"        # Permissive parsing
    EDUCATIONAL = "educational"      # Educational mode with extra help


class ErrorHandlingMode(Enum):
    """Error handling strategies."""
    STRICT = "strict"                # Stop on first error
    COLLECT = "collect"              # Collect multiple errors
    RECOVER = "recover"              # Attempt error recovery


@dataclass
class ParserConfig:
    """Parser configuration options.

    Only fields that are actually read by parser code are included here.
    Feature checks via is_feature_enabled() and should_allow() use getattr
    with a default of False, so removed fields safely return False.
    """

    # === Core Parsing Mode ===
    parsing_mode: ParsingMode = ParsingMode.BASH_COMPAT

    # === Error Handling ===
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT
    max_errors: int = 10
    collect_errors: bool = False
    enable_error_recovery: bool = False
    show_error_suggestions: bool = True

    # === Language Features (read by parser) ===
    enable_arithmetic: bool = True

    # === Bash Compatibility (read by parser via should_allow()) ===
    allow_bash_conditionals: bool = True     # Allow [[ ]] conditionals
    allow_bash_arithmetic: bool = True       # Allow (( )) arithmetic

    # === Development and Debugging ===
    trace_parsing: bool = False              # Trace parsing rules
    profile_parsing: bool = False            # Profile parser performance

    @classmethod
    def strict_posix(cls) -> 'ParserConfig':
        """Create strict POSIX configuration."""
        return cls(
            parsing_mode=ParsingMode.STRICT_POSIX,
            error_handling=ErrorHandlingMode.STRICT,
            allow_bash_conditionals=False,
            allow_bash_arithmetic=False,
        )

    @classmethod
    def permissive(cls) -> 'ParserConfig':
        """Create permissive configuration for error tolerance."""
        return cls(
            parsing_mode=ParsingMode.PERMISSIVE,
            error_handling=ErrorHandlingMode.RECOVER,
            max_errors=50,
            collect_errors=True,
            enable_error_recovery=True,
            show_error_suggestions=True,
        )

    def clone(self, **overrides) -> 'ParserConfig':
        """Create a copy of this config with optional overrides."""
        # Get all current field values
        values = {}
        for field_info in self.__dataclass_fields__.values():
            values[field_info.name] = getattr(self, field_info.name)

        # Apply overrides (only for fields that exist)
        for key, value in overrides.items():
            if key in values:
                values[key] = value

        return ParserConfig(**values)

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled."""
        attr_name = f"enable_{feature}"
        return getattr(self, attr_name, False)

    def should_allow(self, capability: str) -> bool:
        """Check if a capability should be allowed."""
        attr_name = f"allow_{capability}"
        return getattr(self, attr_name, False)
