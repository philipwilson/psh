# Architectural Changes for Command-Specific Variable Assignments

## Overview

This document outlines the architectural changes needed for PSH to support command-specific variable assignments in the form `VAR=value command`. This feature allows temporary variable assignments that only affect the execution of a specific command.

## Current State

### The Problem

PSH currently fails to handle commands like `TEST_VAR=hello echo $TEST_VAR` correctly because:

1. **Expansion Order Issue**: Variable expansion happens before assignments are applied
   - Line 78: `$TEST_VAR` is expanded (to empty/null)
   - Line 90: `TEST_VAR=hello` is applied
   - Result: `echo` receives an empty argument

2. **Architecture**: The current flow in `CommandExecutor.execute()`:
   ```
   1. Expand all arguments (including variables)
   2. Extract assignments from expanded arguments
   3. Apply assignments
   4. Execute command
   ```

### Current Implementation Details

- **SimpleCommand AST**: Contains args, arg_types, quote_types, redirects, but no dedicated assignments field
- **Assignment Detection**: Happens at runtime by scanning arguments for `VAR=value` patterns
- **Assignment Scope**: Temporary assignments are saved/restored around command execution
- **Environment**: External commands receive assignments through `shell.env`

## Proposed Changes

### 1. Two-Phase Expansion in CommandExecutor

The core fix is to delay variable expansion until after assignments are applied:

```python
def execute(self, node: 'SimpleCommand', context: ExecutionContext) -> int:
    """Execute a simple command with proper assignment handling."""
    try:
        # Phase 1: Extract raw assignments (before expansion)
        raw_assignments = self._extract_assignments_raw(node.args, node.arg_types)
        
        # Expand only the assignment values
        assignments = []
        for var, value in raw_assignments:
            expanded_value = self._expand_assignment_value(value)
            assignments.append((var, expanded_value))
        
        # Apply assignments to current environment
        saved_vars = self._apply_command_assignments(assignments)
        
        try:
            # Phase 2: Expand remaining arguments with assignments in effect
            command_start_index = len(raw_assignments)
            if command_start_index < len(node.args):
                # We have a command after assignments
                command_args = node.args[command_start_index:]
                command_arg_types = node.arg_types[command_start_index:]
                command_quote_types = node.quote_types[command_start_index:]
                
                # Create a sub-node for expansion
                command_node = SimpleCommand(
                    args=command_args,
                    arg_types=command_arg_types,
                    quote_types=command_quote_types,
                    redirects=node.redirects,
                    background=node.background
                )
                
                # Now expand with assignments in place
                expanded_args = self._expand_arguments(command_node)
                
                # Continue with normal execution flow
                # ... rest of execution logic ...
            else:
                # Pure assignments (no command)
                return self._handle_pure_assignments(node, assignments)
                
        finally:
            # Restore variables
            self._restore_command_assignments(saved_vars)
```

### 2. New Helper Methods

```python
def _extract_assignments_raw(self, args: List[str], arg_types: List[TokenType]) -> List[Tuple[str, str]]:
    """Extract assignments without expansion, respecting argument types."""
    assignments = []
    
    for i, (arg, arg_type) in enumerate(zip(args, arg_types)):
        # Only WORD and COMPOSITE types can be assignments
        if arg_type not in (TokenType.WORD, TokenType.COMPOSITE):
            break
            
        if '=' in arg and self._is_valid_assignment(arg):
            var, value = arg.split('=', 1)
            assignments.append((var, value))
        else:
            break
    
    return assignments

def _expand_assignment_value(self, value: str) -> str:
    """Expand the value part of an assignment."""
    # Use existing expansion logic but only for the value
    # This handles $VAR, $(cmd), arithmetic, etc. in assignment values
    return self.shell.expansion_manager.expand_string(value)
```

### 3. External Command Environment Enhancement

Ensure temporary assignments are properly exported to subprocesses:

```python
# In ExternalExecutionStrategy.execute()
def execute(self, args: List[str], shell: 'Shell', 
            background: bool = False, pipeline: bool = False) -> int:
    """Execute external command with proper environment."""
    
    # Get current environment including temporary assignments
    cmd_env = shell.env.copy()
    
    # Add any non-exported temporary assignments for this command
    # (This requires tracking which variables are temporary)
    if hasattr(shell.state, '_temp_assignments'):
        for var, value in shell.state._temp_assignments.items():
            cmd_env[var] = value
    
    # Fork and exec with the complete environment
    pid = os.fork()
    if pid == 0:
        # Child process
        try:
            os.execvpe(args[0], args, cmd_env)
        except OSError as e:
            # ... error handling ...
```

### 4. State Tracking for Temporary Assignments

Add tracking of temporary assignments in ShellState:

```python
class ShellState:
    def __init__(self):
        # ... existing init ...
        self._temp_assignments: Dict[str, str] = {}
    
    def set_temp_assignment(self, name: str, value: str):
        """Set a temporary assignment for current command."""
        self._temp_assignments[name] = value
        self.set_variable(name, value)
    
    def clear_temp_assignments(self):
        """Clear temporary assignments after command execution."""
        self._temp_assignments.clear()
```

### 5. AST Enhancement (Future Improvement)

For cleaner architecture, enhance the SimpleCommand AST node:

```python
@dataclass
class SimpleCommand(Command):
    """Simple command with optional variable assignments."""
    assignments: List[Tuple[str, str]] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    arg_types: List['TokenType'] = field(default_factory=list)
    quote_types: List[Optional[str]] = field(default_factory=list)
    redirects: List['Redirect'] = field(default_factory=list)
    background: bool = False
    array_assignments: List['ArrayAssignment'] = field(default_factory=list)
```

This would require parser changes to populate the assignments field during parsing.

## Implementation Strategy

### Phase 1: Minimal Fix (High Priority)
1. Implement two-phase expansion in `CommandExecutor`
2. Add `_extract_assignments_raw()` method
3. Modify execution flow to delay argument expansion
4. Update existing tests to verify functionality

### Phase 2: Environment Propagation (Medium Priority)
1. Ensure external commands receive temporary assignments
2. Add temporary assignment tracking in `ShellState`
3. Update `ExternalExecutionStrategy` to include temp assignments
4. Test with external commands that check environment

### Phase 3: AST Enhancement (Low Priority)
1. Add `assignments` field to `SimpleCommand`
2. Update parser to separate assignments during parsing
3. Simplify `CommandExecutor` to use pre-parsed assignments
4. Maintain backward compatibility

## Testing Requirements

### Basic Functionality
- `TEST_VAR=hello echo $TEST_VAR` → outputs "hello"
- `A=1 B=2 echo $A $B` → outputs "1 2"
- `VAR=value` → sets VAR permanently
- `VAR=temp cmd; echo $VAR` → VAR not set after command

### Advanced Cases
- Nested expansion: `A=hello B=$A echo $B` → outputs "hello"
- Command substitution: `A=$(echo test) echo $A` → outputs "test"
- External commands: `PATH=/custom/path which ls` → uses custom PATH
- Builtin commands: `IFS=: read a b c` → uses custom IFS
- Export behavior: `export A=1; B=2 sh -c 'echo $A $B'` → only A visible

### Error Cases
- Readonly variables: `readonly RO; RO=value echo test` → error
- Invalid names: `1VAR=bad echo test` → treats as command
- Assignment in string: `"VAR=value" echo test` → not an assignment

## Benefits

1. **POSIX Compliance**: Matches standard shell behavior
2. **Backward Compatible**: Existing functionality unchanged
3. **Clean Architecture**: Clear separation of parsing and execution
4. **Maintainable**: Easier to understand and modify
5. **Testable**: Each phase can be tested independently

## Risks and Mitigation

### Performance Impact
- **Risk**: Two-phase expansion might be slower
- **Mitigation**: Only affects commands with assignments (rare case)

### Complexity
- **Risk**: More complex execution flow
- **Mitigation**: Clear documentation and separation of concerns

### Edge Cases
- **Risk**: Unusual assignment patterns might break
- **Mitigation**: Comprehensive test suite based on bash behavior

## Timeline Estimate

- **Phase 1**: 2-3 hours (minimal fix)
- **Phase 2**: 1-2 hours (environment propagation)
- **Phase 3**: 3-4 hours (AST enhancement with parser changes)

Total: 6-9 hours for complete implementation

## References

- POSIX Shell Command Language: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_09_01
- Bash Manual - Simple Command Expansion: https://www.gnu.org/software/bash/manual/html_node/Simple-Command-Expansion.html
- Current PSH implementation: `psh/executor/command.py`