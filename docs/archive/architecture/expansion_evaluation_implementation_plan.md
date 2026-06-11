# Expansion Evaluation Implementation Plan

## Overview

This document provides a detailed plan for implementing expansion evaluation in the executor, leveraging the Word AST nodes we've created. This will enable actual parameter expansion functionality in PSH.

## Current State

### Completed
- ✅ Expansion AST nodes (VariableExpansion, CommandSubstitution, ParameterExpansion, ArithmeticExpansion)
- ✅ Word AST nodes with LiteralPart and ExpansionPart
- ✅ WordBuilder utility for constructing Word nodes
- ✅ Parser support in both implementations
- ✅ Lexer support with PARAM_EXPANSION token

### Existing Infrastructure
- `ExpansionManager` orchestrates expansions but works with strings
- `VariableExpander` handles variable expansion with string manipulation
- `ParameterExpansion` class handles complex parameter expansions
- Expansion happens in `expand_arguments()` method

## Implementation Strategy

### Phase 1: Add Word AST Support to Expansion System

#### 1.1 Update ExpansionManager
```python
# In expansion/manager.py
def expand_arguments(self, command: SimpleCommand) -> List[str]:
    """Expand arguments, handling both string and Word AST approaches."""
    
    # Check if command has Word AST nodes
    if hasattr(command, 'words') and command.words:
        return self._expand_word_ast_arguments(command)
    else:
        # Fall back to existing string-based expansion
        return self._expand_string_arguments(command)

def _expand_word_ast_arguments(self, command: SimpleCommand) -> List[str]:
    """Expand arguments using Word AST nodes."""
    args = []
    
    for word in command.words:
        expanded = self._expand_word(word)
        if isinstance(expanded, list):
            args.extend(expanded)
        else:
            args.append(expanded)
    
    return args
```

#### 1.2 Create Word Expansion Methods
```python
def _expand_word(self, word: Word) -> Union[str, List[str]]:
    """Expand a Word AST node."""
    if word.quote_type == "'":
        # Single quotes: no expansion
        return self._word_to_string(word)
    
    # Process each part
    result_parts = []
    for part in word.parts:
        if isinstance(part, LiteralPart):
            result_parts.append(part.text)
        elif isinstance(part, ExpansionPart):
            expanded = self._expand_expansion(part.expansion)
            result_parts.append(expanded)
    
    # Join parts and handle word splitting if unquoted
    result = ''.join(result_parts)
    
    if word.quote_type is None:
        # Unquoted: perform word splitting
        return self._split_words(result)
    else:
        # Quoted: return as single word
        return result
```

### Phase 2: Implement Expansion Evaluation

#### 2.1 Create Expansion Evaluator
```python
# New file: expansion/evaluator.py
class ExpansionEvaluator:
    """Evaluates expansion AST nodes to produce strings."""
    
    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
    
    def evaluate(self, expansion: Expansion) -> str:
        """Evaluate any expansion type."""
        if isinstance(expansion, VariableExpansion):
            return self._evaluate_variable(expansion)
        elif isinstance(expansion, CommandSubstitution):
            return self._evaluate_command_sub(expansion)
        elif isinstance(expansion, ParameterExpansion):
            return self._evaluate_parameter(expansion)
        elif isinstance(expansion, ArithmeticExpansion):
            return self._evaluate_arithmetic(expansion)
        else:
            raise ValueError(f"Unknown expansion type: {type(expansion)}")
```

#### 2.2 Implement Variable Expansion
```python
def _evaluate_variable(self, expansion: VariableExpansion) -> str:
    """Evaluate simple variable expansion."""
    name = expansion.name
    
    # Handle special variables
    if name in self.SPECIAL_VARS:
        return self._get_special_var(name)
    
    # Handle positional parameters
    if name.isdigit():
        params = self.state.positional_params
        index = int(name) - 1
        return params[index] if 0 <= index < len(params) else ''
    
    # Regular variables
    value = self.state.scope_manager.get_variable(name)
    return str(value) if value is not None else ''
```

#### 2.3 Implement Parameter Expansion
```python
def _evaluate_parameter(self, expansion: ParameterExpansion) -> str:
    """Evaluate parameter expansion with operators."""
    param = expansion.parameter
    operator = expansion.operator
    word = expansion.word
    
    # Get current value
    value = self.state.scope_manager.get_variable(param)
    
    # Apply operator
    if operator == ':-':
        # Use default if unset or null
        return str(value) if value else word
    elif operator == ':=':
        # Assign default if unset or null
        if not value:
            self.state.scope_manager.set_variable(param, word)
            return word
        return str(value)
    elif operator == ':?':
        # Error if unset or null
        if not value:
            raise ExpansionError(word or f"{param}: parameter null or not set")
        return str(value)
    elif operator == ':+':
        # Use alternate if set
        return word if value else ''
    elif operator == '#':
        # Length (special case when word is None)
        if word is None:
            return str(len(str(value))) if value else '0'
        # Remove shortest prefix
        return self._remove_prefix(str(value), word, shortest=True)
    elif operator == '##':
        # Remove longest prefix
        return self._remove_prefix(str(value), word, shortest=False)
    elif operator == '%':
        # Remove shortest suffix
        return self._remove_suffix(str(value), word, shortest=True)
    elif operator == '%%':
        # Remove longest suffix
        return self._remove_suffix(str(value), word, shortest=False)
    elif operator == '/':
        # Replace first occurrence
        return self._replace_pattern(str(value), word, first_only=True)
    elif operator == '//':
        # Replace all occurrences
        return self._replace_pattern(str(value), word, first_only=False)
    else:
        raise ValueError(f"Unknown parameter expansion operator: {operator}")
```

### Phase 3: Integration with Executor

#### 3.1 Update Parser Configuration
```python
# When executing, enable Word AST creation
def execute_ast(self, ast: ASTNode) -> int:
    # Temporarily enable Word AST creation for expansion
    old_config = self.parser.config.build_word_ast_nodes
    self.parser.config.build_word_ast_nodes = True
    
    try:
        return self.executor.visit(ast)
    finally:
        self.parser.config.build_word_ast_nodes = old_config
```

#### 3.2 Update Command Executor
```python
# In executor/command.py
def execute_simple_command(self, command: SimpleCommand) -> int:
    # Expand arguments using new system
    expanded_args = self.shell.expansion_manager.expand_arguments(command)
    
    # Rest of execution remains the same
    ...
```

### Phase 4: Handle Special Cases

#### 4.1 Quoted String Expansions
- Handle expansions within double quotes
- Preserve quote information through expansion
- Implement proper quote removal

#### 4.2 Composite Words
- Handle words with mixed literal/expansion content
- Proper concatenation of parts
- Word splitting rules for composite words

#### 4.3 Array Expansions
- Handle ${array[@]} and ${array[*]}
- Implement proper quoting behavior
- Support array element expansions

## Testing Strategy

### Unit Tests
1. Test each expansion type individually
2. Test parameter expansion operators
3. Test quote handling
4. Test word splitting

### Integration Tests
1. Test complex expansion combinations
2. Test with real shell scripts
3. Compare behavior with bash

### Test Files
- `tests/unit/expansion/test_expansion_evaluator.py`
- `tests/unit/expansion/test_word_expansion.py`
- `tests/integration/expansion/test_expansion_execution.py`

## Implementation Order

1. **Week 1**: Basic infrastructure
   - ExpansionEvaluator class
   - Word AST integration in ExpansionManager
   - Simple variable expansion

2. **Week 2**: Parameter expansion
   - All parameter expansion operators
   - Pattern matching operations
   - Error handling

3. **Week 3**: Advanced features
   - Array expansions
   - Quoted string handling
   - Composite words

4. **Week 4**: Testing and refinement
   - Comprehensive test suite
   - Performance optimization
   - Documentation

## Benefits

1. **Correctness**: Proper handling of all expansion forms
2. **Maintainability**: Clean separation of parsing and evaluation
3. **Extensibility**: Easy to add new expansion types
4. **Performance**: Avoid reparsing during expansion

## Example Usage

```python
# Parser creates Word AST
tokens = tokenize('echo ${USER:-nobody} $(date)')
ast = parser.parse(tokens)  # Creates Word nodes

# Executor evaluates expansions
result = shell.execute_ast(ast)
# Output: "alice Mon Jan 17 10:30:00 PST 2025"
```

## Success Metrics

- All parameter expansion tests pass
- Integration tests show correct behavior
- Performance comparable to string-based approach
- Clean, maintainable code structure

## Conclusion

This implementation plan provides a clear path to adding expansion evaluation using the Word AST infrastructure. By following this plan, we'll have a robust, maintainable expansion system that properly handles all shell expansion types.