# Shell Variable Implementation in PSH - Detailed Analysis

## Overview

This document provides a comprehensive analysis of how shell variables are implemented in the Python Shell (PSH) project. It covers the core architecture, data structures, scope management, and integration points throughout the system.

## 1. Core Architecture

The shell variable system in PSH is built on several key components:

### Variable Data Model (`psh/core/variables.py`)

- **Variable Class**: A dataclass containing:
  - `name`: Variable identifier
  - `value`: Can be string, int, IndexedArray, or AssociativeArray
  - `attributes`: Bitwise flags from VarAttributes enum
- **VarAttributes Enum**: Flags for variable properties:
  - READONLY (-r): Cannot be modified
  - EXPORT (-x): Exported to environment
  - INTEGER (-i): Arithmetic evaluation
  - LOWERCASE (-l): Auto-lowercase conversion
  - UPPERCASE (-u): Auto-uppercase conversion
  - ARRAY (-a): Indexed array
  - ASSOC_ARRAY (-A): Associative array
  - NAMEREF (-n): Name reference (indirect)
  - TRACE (-t): Function tracing
  - UNSET: Tombstone marker for unset variables

### Array Types

- **IndexedArray**: Sparse array implementation
  - Supports negative indices for reverse access
  - Maintains max_index for efficiency
  - Provides bash-compatible element access
- **AssociativeArray**: Dictionary-based implementation
  - Preserves insertion order (Python 3.7+ dict behavior)
  - String keys only
  - Empty string value when accessed without subscript

## 2. Scope Management (`psh/core/scope_enhanced.py`)

The `EnhancedScopeManager` implements a sophisticated scope chain:

### Scope Stack Architecture

- Global scope at base
- Function scopes pushed/popped on entry/exit
- Each scope contains a `VariableScope` with its own variable dictionary

### Variable Resolution Algorithm

1. Check special variables (LINENO, SECONDS, RANDOM, etc.)
2. Search scope stack from innermost to outermost
3. Skip "unset tombstones" (UNSET attribute)
4. Return None if not found

### Variable Assignment Logic

```python
# Simplified flow:
if local or in_global_scope:
    target = current_scope
elif variable_exists_with_unset_tombstone:
    target = current_scope  # Replace tombstone
elif variable_exists_in_parent_scope:
    target = parent_scope   # Update existing
else:
    target = global_scope   # Create new global
```

### Unset Handling

- Creates "tombstone" entries with UNSET attribute
- Prevents fallback to parent scopes
- Maintains bash-compatible unset semantics

## 3. Attribute System

### Attribute Application

- **UPPERCASE/LOWERCASE**: Applied during assignment
- **INTEGER**: Triggers arithmetic evaluation
- **READONLY**: Enforced with ReadonlyVariableError
- **EXPORT**: Synchronized with os.environ

### Attribute Merging

- New attributes are OR'd with existing ones
- UNSET attribute cleared on assignment
- Some attributes are mutually exclusive (uppercase vs lowercase)

## 4. Special Variables

Handled dynamically in `_get_special_variable()`:
- **LINENO**: Current line number in script
- **SECONDS**: Seconds since shell start
- **RANDOM**: Random number generator
- **$?**: Last exit code
- **$$**: Shell PID
- **$!**: Last background PID
- **$#**: Positional parameter count
- **$@/$\***: Positional parameters
- **$0-$9**: Individual positional parameters

## 5. Integration Points

### Shell State (`psh/core/state.py`)

- Contains `scope_manager` instance
- Provides backward-compatible `variables` property
- Manages positional parameters separately
- Initializes special variables (PS1, PS2, PSH_VERSION)

### Executor (`psh/visitor/executor_visitor.py`)

- Handles variable assignments in commands
- Manages function scope push/pop
- Applies redirections before assignments
- Catches ReadonlyVariableError

### Expansion System (`psh/expansion/variable.py`)

- Complex parameter expansion support
- Array subscript evaluation
- Pattern matching and string operations
- Arithmetic expansion integration

## 6. Key Features

1. **Bash Compatibility**
   - Matches bash behavior for most operations
   - Proper scope resolution
   - Array handling
   - Special variable support

2. **Type Safety**
   - Strong typing with Python dataclasses
   - Clear attribute flags
   - Proper error handling

3. **Performance Optimizations**
   - Sparse array implementation
   - Efficient scope lookup
   - Cached special variables where appropriate

4. **Debug Support**
   - Optional debug output for scope operations
   - Clear logging of variable operations
   - Traceable scope chain

## 7. Proposed Improvements

### Performance Enhancements

**Variable Lookup Cache**
```python
class EnhancedScopeManager:
    def __init__(self):
        self._lookup_cache = {}
        self._cache_generation = 0
    
    def invalidate_cache(self):
        self._cache_generation += 1
    
    def get_variable_object(self, name: str) -> Optional[Variable]:
        cache_key = (name, self._cache_generation)
        if cache_key in self._lookup_cache:
            return self._lookup_cache[cache_key]
        
        # ... existing lookup logic ...
        self._lookup_cache[cache_key] = result
        return result
```

### Memory Efficiency

**Copy-on-Write for Arrays**
```python
class IndexedArray:
    def __init__(self, source=None):
        if source:
            self._elements = source._elements
            self._is_shared = True
            source._is_shared = True
        else:
            self._elements = {}
            self._is_shared = False
    
    def _ensure_unique(self):
        if self._is_shared:
            self._elements = self._elements.copy()
            self._is_shared = False
    
    def set(self, index: int, value: str):
        self._ensure_unique()
        # ... existing logic ...
```

### Better NAMEREF Support

Currently NAMEREF is defined but not fully implemented:
```python
def get_variable_object(self, name: str) -> Optional[Variable]:
    var = self._get_variable_raw(name)
    
    # Follow namerefs
    max_depth = 10  # Prevent infinite loops
    while var and var.is_nameref and max_depth > 0:
        target_name = var.as_string()
        var = self._get_variable_raw(target_name)
        max_depth -= 1
    
    return var
```

### Attribute Validation

Add validation for mutually exclusive attributes:
```python
def validate_attributes(attributes: VarAttributes) -> None:
    if (attributes & VarAttributes.UPPERCASE and 
        attributes & VarAttributes.LOWERCASE):
        raise ValueError("Cannot have both uppercase and lowercase")
    
    if (attributes & VarAttributes.ARRAY and 
        attributes & VarAttributes.ASSOC_ARRAY):
        raise ValueError("Cannot be both indexed and associative array")
```

### Better Array Serialization

For declare -p and debugging:
```python
class AssociativeArray:
    def to_declare_format(self) -> str:
        """Generate declare -A compatible string."""
        items = []
        for key, value in self._elements.items():
            escaped_key = self._escape_key(key)
            escaped_value = self._escape_value(value)
            items.append(f'[{escaped_key}]="{escaped_value}"')
        return f"({' '.join(items)})"
```

### Thread Safety

If PSH ever needs concurrent execution:
```python
import threading

class EnhancedScopeManager:
    def __init__(self):
        self._lock = threading.RLock()
        # ... existing init ...
    
    def set_variable(self, name: str, value: Any, **kwargs):
        with self._lock:
            # ... existing logic ...
```

### Variable Persistence

For saving/restoring shell state:
```python
def serialize_state(self) -> dict:
    """Serialize all variables for persistence."""
    return {
        'global': self._serialize_scope(self.global_scope),
        'stack_depth': len(self.scope_stack),
        'special_state': {
            'start_time': self._shell_start_time,
            'line_number': self._current_line_number,
        }
    }

def restore_state(self, state: dict) -> None:
    """Restore variables from serialized state."""
    # Implementation details...
```

## Summary

PSH's variable implementation is well-architected with clear separation of concerns, strong typing, and comprehensive bash compatibility. The scope management system correctly handles complex scenarios like unset tombstones and function-local variables. The attribute system provides powerful transformations while maintaining type safety.

The proposed improvements focus on performance optimization, memory efficiency, and completing partially implemented features like NAMEREF. The current implementation already handles the vast majority of bash variable semantics correctly, making it an excellent educational tool for understanding shell internals.

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Overall system architecture
- [ARCHITECTURE.llm](./ARCHITECTURE.llm) - Detailed component guide
- [CLAUDE.md](../CLAUDE.md) - Development guide for AI assistants