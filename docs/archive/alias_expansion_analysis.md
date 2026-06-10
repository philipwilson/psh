# Alias Expansion Analysis

This document analyzes the xfail tests in `tests/integration/aliases/test_alias_expansion.py` and identifies fixes needed for proper alias expansion in PSH.

## Summary

8 tests are marked as xfail, representing various alias expansion issues:

## 1. Alias Precedence Issues (3 tests)

### Current Behavior
PSH allows aliases to override builtins, which is incorrect according to POSIX/bash semantics.

### Tests Affected
- `test_alias_vs_builtin` - Aliases override builtins (should NOT)
- `test_alias_vs_function` - Need to verify function precedence
- `test_bypass_alias_with_command_builtin` - `command` builtin has execution errors

### Root Cause
Alias expansion happens at tokenization time before the shell knows whether a command is a builtin, function, or external command.

### Correct Precedence Order (bash)
1. Functions
2. Builtins
3. Aliases
4. External commands in PATH

### Fix Required
The alias expansion logic needs to be aware of:
- Builtin commands (should not expand aliases for builtin names)
- Functions (should not expand aliases for function names)
- The `command` builtin needs to temporarily disable alias expansion

## 2. Alias Expansion Timing (1 test)

### Test: `test_alias_expansion_timing`
Tests that alias expansion happens before variable expansion.

### Expected Behavior
```bash
alias test="echo expanded"
VAR=test
$VAR  # Should NOT expand the alias (outputs "test: command not found")
```

### Current Status
Need to verify PSH's expansion order.

## 3. Special Character Handling (1 test)

### Test: `test_alias_with_special_characters`
Tests aliases with quotes and escape sequences.

### Example
```bash
alias special="echo \"quoted\" and \$escaped"
special  # Should output: quoted and $escaped
```

### Issue
Likely related to quote/escape handling during alias definition or expansion.

## 4. Context-Specific Expansion (2 tests)

### Tests Affected
- `test_alias_in_function` - Aliases inside function definitions
- `test_alias_with_case_statement` - Aliases in case statements

### Expected Behavior
Aliases should expand in most contexts, including:
- Inside function bodies
- In case statement commands
- In subshells
- In loops

### Current Status
Need to verify if aliases are being expanded in all appropriate contexts.

## 5. Advanced Features (1 test)

### Test: `test_alias_with_array_syntax`
Tests aliases that reference array elements like `${ARR[0]}`.

### Dependency
This depends on full array support in PSH.

## Recommended Fix Priority

1. **High Priority**: Fix alias vs builtin precedence
   - Most important for POSIX compliance
   - Affects basic shell usage
   - Required for scripts that depend on builtin behavior

2. **Medium Priority**: Fix expansion timing and contexts
   - Important for complex scripts
   - Affects advanced usage patterns

3. **Low Priority**: Special characters and array support
   - Edge cases that can be worked around
   - Array support is a separate feature

## Implementation Approach

### Option 1: Delayed Expansion (Complex)
- Defer alias expansion until command execution time
- Check builtin/function registries before expanding
- Requires significant architectural changes

### Option 2: Builtin/Function Awareness (Moderate)
- Pass builtin and function lists to alias manager
- Skip expansion for known builtins/functions
- Add special handling for `command` builtin

### Option 3: Expansion Flags (Simple)
- Add flag to temporarily disable alias expansion
- Use for `command` builtin implementation
- Document that aliases can override builtins as a known limitation

## Testing Notes

The test infrastructure uses subprocess for proper isolation, which is good for testing alias behavior across different execution contexts.

## Related Files

- `/Users/pwilson/src/psh/psh/aliases.py` - Alias manager implementation
- `/Users/pwilson/src/psh/psh/shell.py` - Alias expansion call site
- `/Users/pwilson/src/psh/psh/builtins/positional.py` - Command builtin implementation