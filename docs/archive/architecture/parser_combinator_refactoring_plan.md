# Parser Combinator Refactoring Plan

## Overview

This document outlines a detailed plan to refactor the monolithic `parser_combinator_example.py` (2,779 lines) into a modular, maintainable structure while preserving compatibility with the parser experimentation framework.

## Current State

- **File**: `psh/parser/implementations/parser_combinator_example.py`
- **Size**: 2,779 lines
- **Issues**:
  - Difficult to navigate and maintain
  - Hard to test individual components
  - No clear separation of concerns
  - All parsing logic in a single file

## Target Architecture

```
psh/parser/combinators/
├── __init__.py              # Package exports
├── core.py                  # Core combinator framework (~350 lines)
├── tokens.py                # Token-level parsers (~200 lines)
├── expansions.py            # Word and expansion parsers (~300 lines)
├── commands.py              # Command and pipeline parsers (~400 lines)
├── control_structures.py    # Control flow parsers (~800 lines)
├── special_commands.py      # Special syntax parsers (~300 lines)
├── heredoc_processor.py     # Heredoc content population (~200 lines)
└── parser.py                # Main parser class (~230 lines)
```

## Refactoring Phases

### Phase 1: Create Module Structure and Core Framework (Week 1)

**Objective**: Establish the modular structure and extract core combinator framework.

**Tasks**:
1. Create `psh/parser/combinators/` directory structure
2. Extract core parser combinator framework to `core.py`:
   - `ParseResult` class
   - `Parser` class with core methods (map, then, or_else)
   - Basic combinators: `token`, `many`, `many1`, `optional`, `sequence`, `separated_by`
   - Advanced combinators: `lazy`, `between`, `skip`, `fail_with`, `try_parse`
   - `ForwardParser` for recursive grammars
   - `with_error_context` for better error messages

3. Create comprehensive tests for core combinators:
   ```python
   # tests/unit/parser/combinators/test_core.py
   def test_token_parser():
       parser = token('WORD')
       result = parser.parse([Token(TokenType.WORD, 'hello')], 0)
       assert result.success
       assert result.value.value == 'hello'
   ```

4. Update imports in existing code to use new module structure

**Deliverables**:
- `combinators/core.py` with all core combinator logic
- Comprehensive test suite for core combinators
- Working imports from new module structure

### Phase 2: Extract Token and Basic Parsers (Week 1-2)

**Objective**: Separate token-level parsing logic.

**Tasks**:
1. Extract to `tokens.py`:
   - `keyword()` and `literal()` functions
   - All specific token parsers (SEMICOLON, NEWLINE, PIPE, etc.)
   - Operator token parsers (redirect operators, logical operators)
   - Separator and delimiter parsers

2. Create token parser factory pattern:
   ```python
   class TokenParsers:
       """Factory for commonly used token parsers."""
       
       @staticmethod
       def create_separator_parser():
           """Create parser for command separators."""
           return token('SEMICOLON').or_else(token('NEWLINE'))
       
       @staticmethod
       def create_redirect_operator_parser():
           """Create parser for redirect operators."""
           return (token('REDIRECT_OUT')
                  .or_else(token('REDIRECT_APPEND'))
                  .or_else(token('REDIRECT_IN')))
   ```

3. Update existing code to import from `tokens.py`

**Deliverables**:
- `combinators/tokens.py` with all token parsing logic
- Token parser factory for common patterns
- Updated imports in main parser

### Phase 3: Extract Expansion Parsers (Week 2)

**Objective**: Modularize word building and expansion parsing.

**Tasks**:
1. Extract to `expansions.py`:
   - Variable expansion parser (`_build_variable_expansion`)
   - Command substitution parser (`_build_command_substitution`)
   - Parameter expansion parser (`_build_parameter_expansion`)
   - Arithmetic expansion parser (`_build_arithmetic_expansion`)
   - Process substitution parser (`_build_process_substitution`)
   - Word building logic (`_build_word`, `_build_word_from_token`)

2. Create expansion parser interface:
   ```python
   class ExpansionParsers:
       """Parsers for shell expansions."""
       
       def __init__(self, config: ParserConfig):
           self.config = config
           self.word_builder = WordBuilder(config)
       
       def create_expansion_parser(self) -> Parser[Word]:
           """Create combined expansion parser."""
           return (self.variable_expansion()
                  .or_else(self.command_substitution())
                  .or_else(self.parameter_expansion())
                  .or_else(self.arithmetic_expansion())
                  .or_else(self.process_substitution()))
   ```

3. Add proper dependency injection for word builder

**Deliverables**:
- `combinators/expansions.py` with all expansion parsing logic
- Clean interface for expansion parsing
- Integration with word builder

### Phase 4: Extract Command Parsers (Week 2-3)

**Objective**: Separate core command and pipeline parsing.

**Tasks**:
1. Extract to `commands.py`:
   - Simple command parser
   - Pipeline parser and builder
   - And-or list parser
   - Statement list parser
   - Redirection parser
   - Assignment parser

2. Create command parser hierarchy:
   ```python
   class CommandParsers:
       """Parsers for shell commands."""
       
       def __init__(self, expansion_parsers: ExpansionParsers):
           self.expansions = expansion_parsers
       
       def simple_command(self) -> Parser[SimpleCommand]:
           """Parse a simple command."""
           # Implementation
       
       def pipeline(self) -> Parser[Pipeline]:
           """Parse a pipeline of commands."""
           # Implementation
   ```

3. Implement clean interfaces between command levels

**Deliverables**:
- `combinators/commands.py` with command parsing logic
- Clear hierarchy from simple commands to statement lists
- Proper composition of parsers

### Phase 5: Extract Control Structure Parsers (Week 3-4)

**Objective**: Modularize control flow parsing.

**Tasks**:
1. Extract to `control_structures.py`:
   - If/elif/else conditional parser
   - While loop parser
   - For loop parser (traditional)
   - C-style for loop parser
   - Case statement parser
   - Select loop parser
   - Function definition parsers (all variants)

2. Create control structure factory:
   ```python
   class ControlStructureParsers:
       """Parsers for shell control structures."""
       
       def __init__(self, command_parsers: CommandParsers):
           self.commands = command_parsers
       
       def create_control_parser(self) -> Parser[UnifiedControlStructure]:
           """Create combined control structure parser."""
           return (self.if_statement()
                  .or_else(self.while_loop())
                  .or_else(self.for_loop())
                  .or_else(self.case_statement())
                  .or_else(self.function_def()))
   ```

3. Handle proper nesting and recursion

**Deliverables**:
- `combinators/control_structures.py` with all control flow parsers
- Unified interface for control structures
- Proper handling of nested structures

### Phase 6: Extract Special Command Parsers (Week 4)

**Objective**: Separate specialized command syntax.

**Tasks**:
1. Extract to `special_commands.py`:
   - Arithmetic command parser `((...))`
   - Enhanced test expression parser `[[ ... ]]`
   - Array assignment parsers
   - Subshell group parser `(...)`
   - Brace group parser `{...}`
   - Break/continue statement parsers

2. Create special command interface:
   ```python
   class SpecialCommandParsers:
       """Parsers for special shell syntax."""
       
       def __init__(self, command_parsers: CommandParsers):
           self.commands = command_parsers
       
       def arithmetic_command(self) -> Parser[ArithmeticEvaluation]:
           """Parse arithmetic command ((expression))."""
           # Implementation
   ```

**Deliverables**:
- `combinators/special_commands.py` with special syntax parsers
- Clean integration with command parsers
- Proper AST node creation

### Phase 7: Extract Heredoc Processing (Week 5)

**Objective**: Modularize heredoc content population.

**Tasks**:
1. Extract to `heredoc_processor.py`:
   - `_populate_heredoc_content` method
   - All heredoc traversal logic
   - Heredoc content mapping

2. Create heredoc processor class:
   ```python
   class HeredocProcessor:
       """Processes heredoc content in parsed AST."""
       
       def populate_heredocs(self, ast: ASTNode, 
                           heredoc_contents: Dict[str, Dict]) -> None:
           """Populate heredoc content in AST nodes."""
           # Implementation
   ```

3. Add proper visitor pattern for AST traversal

**Deliverables**:
- `combinators/heredoc_processor.py` with heredoc logic
- Clean separation from parsing logic
- Reusable heredoc processing

### Phase 8: Create Main Parser Integration (Week 5-6)

**Objective**: Integrate all modules in the main parser class.

**Tasks**:
1. Create new `parser.py` with `ParserCombinatorShellParser`:
   ```python
   from ..abstract_parser import AbstractShellParser
   from .core import Parser
   from .tokens import TokenParsers
   from .expansions import ExpansionParsers
   from .commands import CommandParsers
   from .control_structures import ControlStructureParsers
   from .special_commands import SpecialCommandParsers
   from .heredoc_processor import HeredocProcessor
   
   class ParserCombinatorShellParser(AbstractShellParser):
       """Modular parser combinator implementation."""
       
       def __init__(self, config: Optional[ParserConfig] = None):
           self.config = config or ParserConfig()
           
           # Initialize parser modules
           self.tokens = TokenParsers()
           self.expansions = ExpansionParsers(self.config)
           self.commands = CommandParsers(self.expansions)
           self.control = ControlStructureParsers(self.commands)
           self.special = SpecialCommandParsers(self.commands)
           self.heredoc_processor = HeredocProcessor()
           
           # Build top-level parser
           self._build_parser()
   ```

2. Maintain compatibility with parser registry
3. Ensure all existing tests pass

**Deliverables**:
- `combinators/parser.py` with integrated parser
- Full compatibility with existing framework
- All tests passing

### Phase 9: Migration and Testing (Week 6)

**Objective**: Complete migration and ensure quality.

**Tasks**:
1. Update parser registry to use new modular parser:
   ```python
   # In parser_registry.py
   from psh.parser.combinators.parser import ParserCombinatorShellParser
   
   ParserRegistry.register("parser_combinator", 
                          ParserCombinatorShellParser)
   ```

2. Create integration tests for modular parser
3. Performance testing and optimization
4. Update documentation

**Deliverables**:
- Updated parser registry
- Comprehensive test coverage
- Performance benchmarks
- Updated documentation

## Testing Strategy

### Unit Tests
Each module will have comprehensive unit tests:
- `test_core.py` - Test individual combinators
- `test_tokens.py` - Test token parsers
- `test_expansions.py` - Test expansion parsing
- `test_commands.py` - Test command parsing
- `test_control_structures.py` - Test control flow
- `test_special_commands.py` - Test special syntax
- `test_heredoc_processor.py` - Test heredoc processing

### Integration Tests
- Test complete parsing scenarios
- Ensure AST compatibility
- Test parser switching functionality
- Verify all existing tests pass

### Performance Tests
- Benchmark parsing speed before/after refactoring
- Memory usage comparison
- Startup time impact

## Risk Mitigation

### Backwards Compatibility
- Keep original file during refactoring
- Run parallel testing
- Gradual migration approach
- Maintain parser registry compatibility

### Testing Coverage
- Write tests before extracting each module
- Maintain 100% test coverage
- Use property-based testing for combinators

### Performance
- Profile before and after each phase
- Optimize critical paths
- Consider lazy imports for faster startup

## Success Metrics

1. **Code Organization**:
   - No module exceeds 800 lines
   - Clear separation of concerns
   - High cohesion within modules

2. **Maintainability**:
   - Easier to locate specific parsing logic
   - Simpler to add new features
   - Better code reuse

3. **Quality**:
   - All existing tests pass
   - No performance regression
   - Improved test coverage

4. **Compatibility**:
   - Parser switching still works
   - Same AST output
   - No breaking changes

## Timeline Summary

- **Week 1**: Core framework and module structure
- **Week 2**: Token parsers and expansions
- **Week 3**: Command parsers
- **Week 4**: Control structures and special commands
- **Week 5**: Heredoc processing and integration
- **Week 6**: Migration, testing, and documentation

Total estimated time: 6 weeks

## Benefits

1. **Improved Maintainability**: Each module has a focused purpose
2. **Better Testability**: Components can be tested in isolation
3. **Enhanced Readability**: Easier to understand and navigate
4. **Increased Reusability**: Combinators can be used for other parsing tasks
5. **Simplified Debugging**: Issues can be isolated to specific modules
6. **Team Collaboration**: Multiple developers can work on different modules
7. **Documentation**: Each module can have focused documentation
8. **Performance**: Potential for optimization through lazy loading

## Conclusion

This refactoring will transform a monolithic 2,779-line file into a well-organized, modular parser implementation. The phased approach ensures continuous functionality while improving code quality. The result will be a more maintainable, testable, and understandable parser that preserves all existing functionality and compatibility with the parser experimentation framework.