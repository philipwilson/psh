# PSH Parser Architecture

## Overview

The Python Shell (PSH) parser is a hand-written recursive descent parser designed for educational clarity while handling the full complexity of shell syntax. This document describes the parser's architecture, design decisions, and implementation patterns.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Organization](#module-organization)
3. [Core Components](#core-components)
4. [Parsing Strategy](#parsing-strategy)
5. [AST Construction](#ast-construction)
6. [Shell-Specific Features](#shell-specific-features)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)
9. [Lexer-Parser Interface](#lexer-parser-interface)
10. [Design Patterns](#design-patterns)
11. [Future Directions](#future-directions)

## Architecture Overview

The PSH parser follows a modular, context-based architecture with these key characteristics:

- **Recursive Descent**: Hand-written parser using recursive descent techniques
- **Modular Design**: Separated into specialized sub-parsers for different language constructs
- **Context Management**: Centralized context object maintains parsing state
- **Strong Typing**: Extensive use of type hints and dataclasses
- **Educational Focus**: Clear, readable code prioritized over performance optimizations

```
┌─────────────────────────────────────────────────────────┐
│                    Token Stream                         │
│                  (from Lexer)                          │
└─────────────────────────────┬───────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    Main Parser                          │
│                 (Orchestrator)                          │
├─────────────────────────────────────────────────────────┤
│ • Token Management (position, lookahead)                │
│ • Context Creation and Management                       │
│ • Delegation to Specialized Parsers                     │
│ • Top-level Parse Entry Point                          │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┬────────────┬─────────────┐
        ▼                         ▼            ▼             ▼
┌───────────────┐       ┌────────────────┐ ┌─────────┐ ┌──────────┐
│  Statement    │       │    Command     │ │Control  │ │Function  │
│   Parser      │       │    Parser      │ │Structure│ │ Parser   │
├───────────────┤       ├────────────────┤ │ Parser  │ ├──────────┤
│• StatementList│       │• SimpleCommand │ ├─────────┤ │• Function│
│• AndOrList    │       │• Pipeline      │ │• If/Then│ │  Defs    │
│• Operators    │       │• Redirections  │ │• Loops  │ │• Body    │
└───────────────┘       └────────────────┘ │• Case   │ └──────────┘
                                           └─────────┘
                              ▼
                    ┌─────────────────────┐
                    │   AST Nodes         │
                    │  (ast_nodes.py)     │
                    └─────────────────────┘
```

## Module Organization

The parser is organized into specialized modules under `psh/parser/`:

### Core Modules

- **`main.py`**: Main parser orchestrator
  - Token stream management
  - Context initialization
  - Top-level parsing logic
  - Delegation to sub-parsers

- **`base.py`**: Base classes and utilities
  - `BaseParser`: Common parsing utilities
  - `ContextBaseParser`: Context-aware base class
  - Token matching and consumption methods

- **`context.py`**: Parser context management
  - `ParserContext`: Centralized parsing state
  - Position tracking
  - Error collection
  - Configuration management

### Specialized Parsers

- **`statements.py`**: Statement and command list parsing
  - `StatementList` (sequences of statements)
  - `AndOrList` (commands with && and || operators)
  - Statement-level constructs

- **`commands.py`**: Command and pipeline parsing
  - `SimpleCommand` (basic commands with arguments)
  - `Pipeline` (command sequences with pipes)
  - Command-level redirections
  - Array assignments

- **`control_structures.py`**: Control flow parsing
  - `if`/`then`/`elif`/`else`/`fi`
  - `while`/`do`/`done`
  - `for`/`do`/`done` (both styles)
  - `case`/`esac`
  - `select` loops
  - Unified control structure nodes

- **`arithmetic.py`**: Arithmetic expression parsing
  - `$((...))` arithmetic expansion
  - Operator precedence handling
  - Expression evaluation context

- **`functions.py`**: Function definition parsing
  - Function declarations
  - Function body parsing
  - Name validation

- **`redirections.py`**: I/O redirection parsing
  - File redirections (`>`, `>>`, `<`)
  - File descriptor operations
  - Heredoc processing
  - Process substitution

- **`arrays.py`**: Array operation parsing
  - Array initialization: `arr=(a b c)`
  - Array element assignment: `arr[0]=value`
  - Append operations: `arr+=(d e)`

- **`tests.py`**: Test expression parsing
  - `[[ ]]` conditional expressions
  - Binary and unary operators
  - Pattern matching support

### Support Modules

- **`error_handler.py`**: Error handling and recovery
  - Error context creation
  - Recovery strategies
  - Error formatting

- **`validation.py`**: Semantic validation
  - Name validation
  - Context-sensitive checks
  - Warning generation

## Core Components

### Parser Context

The `ParserContext` serves as the central state manager:

```python
@dataclass
class ParserContext:
    tokens: List[Token]
    position: int = 0
    errors: List[ParseError] = field(default_factory=list)
    config: ParserConfig = field(default_factory=ParserConfig)
    profiler: Optional[ParserProfiler] = None
    heredocs: List[HeredocInfo] = field(default_factory=list)
    in_function_body: bool = False
    in_arithmetic_context: bool = False
    # ... other state fields
```

Key responsibilities:
- **Token Management**: Current position, lookahead support
- **Error Collection**: Accumulate errors for batch reporting
- **State Tracking**: Parsing context (function body, arithmetic, etc.)
- **Performance Profiling**: Optional performance metrics
- **Heredoc Management**: Two-phase heredoc processing

### Base Parser Classes

#### BaseParser
Provides fundamental parsing operations:

```python
class BaseParser:
    def match(self, *token_types: str) -> bool:
        """Check if current token matches any of the given types."""
        
    def expect(self, token_type: str, error_msg: Optional[str] = None) -> Token:
        """Consume token of expected type or raise error."""
        
    def advance(self) -> Token:
        """Consume and return current token."""
        
    def peek(self, offset: int = 0) -> Optional[Token]:
        """Look at token without consuming."""
```

#### ContextBaseParser
Extends BaseParser with context awareness:

```python
class ContextBaseParser(BaseParser):
    def __init__(self, context: ParserContext):
        self.context = context
        
    def with_profiling(self, rule_name: str):
        """Decorator for profiling parse rules."""
        
    def save_position(self) -> int:
        """Save current parsing position for backtracking."""
        
    def restore_position(self, position: int):
        """Restore to saved position."""
```

## Parsing Strategy

### Recursive Descent

The parser uses recursive descent with these characteristics:

1. **Top-Down Parsing**: Start from the highest-level constructs and recursively parse sub-components
2. **Predictive Parsing**: Use lookahead to determine which production to apply
3. **Backtracking**: Limited backtracking for ambiguous constructs
4. **Left-to-Right**: Single pass through the token stream

Example parsing flow:

```python
def parse_pipeline(self) -> Pipeline:
    """Parse a pipeline: command1 | command2 | command3"""
    commands = [self.parse_command()]
    
    while self.match('PIPE'):
        self.advance()  # consume '|'
        commands.append(self.parse_command())
    
    return Pipeline(commands=commands)
```

### Grammar Implementation

The parser implements a shell grammar with these precedence levels:

1. **Top Level**: Function definitions and command lists
2. **Statement Level**: Control structures and command lists  
3. **List Level**: AND-OR lists with `&&` and `||` operators
4. **Pipeline Level**: Commands connected with pipes
5. **Command Level**: Simple commands, compound commands, subshells
6. **Word Level**: Arguments, expansions, redirections

### Token Consumption Pattern

Standard pattern for parsing constructs:

```python
def parse_construct(self):
    # 1. Check preconditions
    if not self.match('EXPECTED_TOKEN'):
        return None
        
    # 2. Consume opening token
    self.advance()
    
    # 3. Parse internal structure
    result = self.parse_subcomponent()
    
    # 4. Expect closing token
    self.expect('CLOSING_TOKEN', "Expected closing token")
    
    # 5. Build and return AST node
    return ASTNode(result)
```

## AST Construction

### Node Hierarchy

The AST uses a strongly-typed hierarchy with dataclasses:

```
ASTNode (abstract base)
├── TopLevel
│   └── items: List[Union[FunctionDef, Statement]]
├── Statement (abstract)
│   ├── AndOrList
│   ├── FunctionDef
│   └── UnifiedControlStructure (abstract)
│       ├── IfConditional
│       ├── WhileLoop
│       ├── ForLoop
│       └── CaseConditional
├── Command (abstract)
│   ├── SimpleCommand
│   └── CompoundCommand (abstract)
│       ├── SubshellGroup
│       ├── BraceGroup
│       └── UnifiedControlStructure
└── Supporting Nodes
    ├── Pipeline
    ├── Redirect
    ├── ArrayAssignment
    └── TestExpression
```

### Unified Control Structures

Control structures implement both `Statement` and `CompoundCommand` interfaces:

```python
@dataclass
class IfConditional(UnifiedControlStructure):
    condition: StatementList
    then_part: StatementList
    elif_parts: List[Tuple[StatementList, StatementList]]
    else_part: Optional[StatementList]
    redirects: List[Redirect]
    execution_context: ExecutionContext
    background: bool = False
```

This allows control structures to appear in pipelines:
```bash
if test -f file; then cat file; fi | grep pattern
```

### Metadata Preservation

The parser preserves rich metadata:

```python
@dataclass
class SimpleCommand(Command):
    args: List[str]                    # Argument values
    arg_types: List[str]              # Token types (WORD, STRING, etc.)
    quote_types: List[Optional[str]]  # Quote characters used
    redirects: List[Redirect]         # I/O redirections
    background: bool                  # Background execution flag
    array_assignments: List[ArrayAssignment]  # Prefix assignments
```

## Shell-Specific Features

### Pipeline Support

The parser handles complex pipeline constructs:

1. **Simple Pipelines**: `cmd1 | cmd2 | cmd3`
2. **Negated Pipelines**: `! pipeline`
3. **Control Structures in Pipelines**: `if ...; then ...; fi | grep`
4. **Subshells in Pipelines**: `(cd dir && ls) | sort`

### Heredoc Processing

Two-phase heredoc parsing:

```python
# Phase 1: Parse command and collect heredoc marker
cmd = self.parse_simple_command()
if has_heredoc_redirect(cmd):
    self.context.heredocs.append(HeredocInfo(delimiter, ...))

# Phase 2: After newline, process heredoc content
if self.context.heredocs:
    for heredoc in self.context.heredocs:
        content = self.parse_heredoc_content(heredoc)
        attach_to_redirect(heredoc, content)
```

### Composite Token Handling

Special parsing for composite constructs:

1. **Variable Assignment**: `VAR=value` as single token
2. **Array Initialization**: `arr=(a b c)`
3. **File Descriptor Operations**: `2>&1`
4. **Process Substitution**: `<(command)` and `>(command)`

### Context-Sensitive Parsing

Different rules in different contexts:

```python
def parse_word(self):
    if self.context.in_arithmetic_context:
        # Different tokenization rules
        return self.parse_arithmetic_term()
    elif self.context.in_case_pattern:
        # Allow glob patterns
        return self.parse_pattern()
    else:
        # Standard word parsing
        return self.parse_regular_word()
```

## Error Handling

### Error Types

1. **Syntax Errors**: Unexpected tokens, missing delimiters
2. **Semantic Errors**: Invalid names, context violations
3. **Warnings**: Deprecated syntax, portability issues

### Error Context

Rich error information:

```python
@dataclass
class ParseError:
    message: str
    token: Optional[Token]
    position: Position
    severity: ErrorSeverity
    suggestions: List[str]
    context_lines: List[str]
```

### Recovery Strategies

1. **Panic Mode**: Skip tokens until synchronization point
2. **Statement Level**: Recover at statement boundaries
3. **Keyword Recovery**: Synchronize on shell keywords
4. **Missing Token Insertion**: Insert likely missing tokens

Example recovery:

```python
def parse_if_statement(self):
    try:
        # Normal parsing
        condition = self.parse_command_list()
        self.expect('THEN')
        then_part = self.parse_command_list()
    except ParseError as e:
        # Recovery: skip to 'then', 'else', or 'fi'
        self.recover_to_keywords(['THEN', 'ELSE', 'FI'])
        # Continue parsing from recovery point
```

### Error Collection Mode

Support for IDE integration:

```python
# Collect multiple errors
parser = Parser(tokens, collect_errors=True)
ast = parser.parse()
if parser.errors:
    for error in parser.errors:
        display_error(error)
```

## Performance Considerations

### Built-in Profiling

Optional performance profiling:

```python
profiler = ParserProfiler()
parser = Parser(tokens, profiler=profiler)
ast = parser.parse()

# Get performance metrics
stats = profiler.get_stats()
print(f"Total parse time: {stats.total_time}")
print(f"Slowest rules: {stats.slowest_rules}")
print(f"Most frequent: {stats.most_frequent}")
```

### Optimization Strategies

1. **Token Caching**: Avoid repeated token access
2. **Minimal Backtracking**: Use lookahead to avoid backtracking
3. **Early Termination**: Fail fast on obvious errors
4. **Lazy Evaluation**: Defer expensive operations

### Memory Efficiency

- **Streaming**: Process tokens as stream when possible
- **Node Pooling**: Reuse common AST node types
- **Position Sharing**: Share position objects between tokens

## Lexer-Parser Interface

### Basic Interface

Simple token list interface:

```python
tokens = lexer.tokenize(input_string)
parser = Parser(tokens)
ast = parser.parse()
```

### Enhanced Interface

Advanced features via `LexerParserContract`:

```python
# Get enhanced tokens with metadata
contract = lexer.create_parser_contract(input_string)
tokens = contract.get_tokens()  # Tokens with semantic info
validation = contract.get_validation_results()
parser = Parser(tokens, contract=contract)
```

### Token Enhancement

Enhanced tokens provide:
- **Semantic Type**: `BUILTIN`, `KEYWORD`, `OPERATOR`
- **Context Info**: Command position, arithmetic context
- **Assignment Metadata**: Variable name, array index
- **Validation State**: Pre-validated by lexer

## Design Patterns

### 1. Visitor Pattern (AST Processing)

While the parser builds the AST, processing uses visitors:

```python
class ASTVisitor:
    def visit_SimpleCommand(self, node): ...
    def visit_Pipeline(self, node): ...
    def visit_IfConditional(self, node): ...
```

### 2. Strategy Pattern (Error Recovery)

Pluggable error recovery strategies:

```python
class ErrorRecoveryStrategy:
    def recover(self, parser, error): ...

class PanicModeRecovery(ErrorRecoveryStrategy):
    def recover(self, parser, error):
        parser.skip_until_keywords([...])
```

### 3. Template Method (Parse Rules)

Common parsing pattern:

```python
def parse_rule(self):
    self.enter_rule("rule_name")
    try:
        # Rule-specific parsing
        result = self._parse_rule_content()
        return result
    finally:
        self.exit_rule("rule_name")
```

### 4. Builder Pattern (AST Construction)

Complex nodes built incrementally:

```python
builder = IfConditionalBuilder()
builder.set_condition(condition)
builder.add_then_part(then_part)
for elif_cond, elif_body in elifs:
    builder.add_elif_part(elif_cond, elif_body)
builder.set_else_part(else_part)
return builder.build()
```

## Future Directions

### Parser Combinator Implementation

As documented in the Parser Combinator design document, future versions may implement a combinator-based parser for:
- Better composability
- Clearer grammar specification
- Easier testing
- Potential performance improvements

### Enhanced Error Recovery

- Machine learning-based error correction
- Context-aware suggestions
- Multi-language error messages

### Incremental Parsing

Support for IDE scenarios:
- Parse only changed regions
- Maintain parse tree between edits
- Real-time syntax checking

### Grammar Extensions

- Bash 5.x compatibility features
- Zsh-style extensions (optional)
- Custom shell syntax extensions

## Conclusion

The PSH parser demonstrates that educational clarity and production quality can coexist. Its modular architecture, strong typing, and comprehensive error handling make it an excellent example of modern parser design while remaining accessible for learning.

The hand-written recursive descent approach provides transparency into the parsing process, while the sophisticated context management and error recovery ensure a robust user experience. This architecture serves as both a functional shell parser and a teaching tool for compiler construction concepts.