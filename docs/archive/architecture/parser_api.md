# PSH Parser Public API Reference

## Overview

The PSH parser provides a flexible, configurable system for parsing shell commands and scripts. It converts a stream of tokens into an Abstract Syntax Tree (AST) with support for multiple parsing modes, comprehensive error handling, and advanced shell features.

## Quick Start

```python
from psh.parser import parse
from psh.lexer import tokenize

# Basic parsing
tokens = tokenize("echo hello | grep world")
ast = parse(tokens)
```

## Module-Level Functions

### `parse(tokens, config=None)`

The main parsing function for simple use cases.

**Parameters:**
- `tokens` (List[Token]): List of tokens from the lexer
- `config` (Optional[ParserConfig]): Parser configuration (defaults to permissive mode)

**Returns:** 
- `Union[CommandList, TopLevel]`: The parsed AST

**Example:**
```python
ast = parse(tokens)
```

### `parse_with_heredocs(tokens, heredoc_map)`

Parse with heredoc content provided separately.

**Parameters:**
- `tokens` (List[Token]): List of tokens from the lexer
- `heredoc_map` (Dict[str, str]): Mapping of heredoc keys to content

**Returns:**
- `Union[CommandList, TopLevel]`: The parsed AST

**Example:**
```python
heredoc_map = {
    "heredoc_0_EOF": "This is\nheredoc content\n"
}
ast = parse_with_heredocs(tokens, heredoc_map)
```

### Mode-Specific Functions

#### `parse_strict_posix(tokens, source_text=None)`
Parse with strict POSIX compliance.

#### `parse_bash_compatible(tokens, source_text=None)`
Parse with bash compatibility extensions.

#### `parse_permissive(tokens, source_text=None)`
Parse with maximum compatibility (default mode).

**Parameters:**
- `tokens` (List[Token]): List of tokens from the lexer
- `source_text` (Optional[str]): Original source for better error messages

**Returns:**
- AST: The parsed abstract syntax tree

## Parser Class

### Constructor

```python
Parser(tokens: List[Token], 
       use_composite_processor: bool = False,
       source_text: Optional[str] = None, 
       collect_errors: bool = False,
       config: Optional[ParserConfig] = None,
       ctx: Optional[ParserContext] = None)
```

**Parameters:**
- `tokens`: List of tokens to parse
- `use_composite_processor`: Enable composite token processing (for enhanced lexer)
- `source_text`: Original source text for error context
- `collect_errors`: Enable error collection mode
- `config`: Parser configuration
- `ctx`: Pre-initialized parser context (advanced usage)

### Methods

#### `parse() -> Union[CommandList, TopLevel]`

Parse the token stream into an AST.

**Returns:** The root AST node

**Raises:** `ParseError` if parsing fails (unless in error collection mode)

#### `parse_with_heredocs(heredoc_map: dict) -> Union[CommandList, TopLevel]`

Parse with heredoc content provided in a map.

**Parameters:**
- `heredoc_map`: Dictionary mapping heredoc keys to content

**Returns:** The root AST node

#### `parse_with_error_collection() -> MultiErrorParseResult`

Parse and collect all errors instead of failing on first error.

**Returns:** `MultiErrorParseResult` containing AST and error list

**Example:**
```python
result = parser.parse_with_error_collection()
if result.errors:
    for error in result.errors:
        print(f"Error at line {error.error_context.line}: {error.message}")
if result.ast:
    # Process AST
```

#### `parse_and_validate() -> Tuple[Optional[AST], ValidationReport]`

Parse and perform semantic validation.

**Returns:** Tuple of (AST, ValidationReport)

## Configuration

### ParserConfig Class

Controls parser behavior and feature sets.

```python
@dataclass
class ParserConfig:
    # Parsing modes
    parsing_mode: ParsingMode = ParsingMode.PERMISSIVE
    
    # Error handling
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT
    max_errors: int = 10
    collect_errors: bool = False
    enable_error_recovery: bool = False
    
    # Feature toggles
    enable_aliases: bool = True
    enable_functions: bool = True
    enable_arithmetic: bool = True
    enable_arrays: bool = True
    enable_process_substitution: bool = True
    enable_extended_glob: bool = True
    enable_brace_expansion: bool = True
    enable_command_substitution: bool = True
    enable_parameter_expansion: bool = True
    
    # Parsing behavior
    allow_empty_commands: bool = False
    strict_word_splitting: bool = False
    posix_compliance: bool = False
    
    # Debugging
    trace_parsing: bool = False
    profile_parsing: bool = False
```

### ParsingMode Enum

```python
class ParsingMode(Enum):
    STRICT_POSIX = "strict_posix"      # POSIX.1-2017 compliance
    BASH_COMPAT = "bash_compat"        # Bash compatibility mode
    PERMISSIVE = "permissive"          # Maximum compatibility
    EDUCATIONAL = "educational"        # Extra validation for learning
```

### Factory Methods

```python
# Create configurations for common use cases
config = ParserConfig.strict_posix()
config = ParserConfig.bash_compatible()
config = ParserConfig.permissive()
config = ParserConfig.educational()
```

## Error Handling

### ParseError Class

```python
class ParseError(Exception):
    error_context: ErrorContext
    message: str
```

### ErrorContext Class

```python
@dataclass
class ErrorContext:
    token: Token                    # Token where error occurred
    expected: List[str]            # Expected token types
    message: str                   # Error message
    position: int                  # Character position
    line: Optional[int]            # Line number
    column: Optional[int]          # Column number
    source_line: Optional[str]     # Source line text
    suggestions: List[str]         # Suggested fixes
    error_code: str               # Machine-readable error code
    severity: str                 # "info", "warning", "error", "fatal"
```

### MultiErrorParseResult

```python
@dataclass
class MultiErrorParseResult:
    ast: Optional[AST]          # Partial AST if recovery succeeded
    errors: List[ParseError]    # All collected errors
```

## Input Types

### Token Class

```python
@dataclass
class Token:
    type: TokenType            # Token type (WORD, PIPE, etc.)
    value: str                # Token text
    position: int             # Character position in input
    line: Optional[int]       # Line number
    column: Optional[int]     # Column number
```

### TokenType

Common token types include:
- `WORD`: Command names and arguments
- `STRING`: Quoted strings
- `PIPE`: Pipe operator (`|`)
- `SEMICOLON`: Command separator (`;`)
- `AND_IF`: AND operator (`&&`)
- `OR_IF`: OR operator (`||`)
- `REDIRECT_*`: Various redirection operators
- Control keywords: `IF`, `THEN`, `ELSE`, `FI`, etc.

## Output Types (AST Nodes)

All AST nodes inherit from `ASTNode` and are defined in `psh.ast_nodes`.

### Core Node Types

- **TopLevel**: Root node for scripts with functions
- **StatementList** (alias: CommandList): Sequence of statements
- **AndOrList**: Commands with `&&` and `||` operators
- **Pipeline**: Commands connected by pipes
- **SimpleCommand**: Basic command with arguments
- **Redirect**: I/O redirection

### Control Structures

- **IfConditional**: if/then/elif/else/fi
- **WhileLoop**: while/do/done
- **ForLoop**: for/do/done
- **CaseConditional**: case/esac
- **SelectLoop**: select loops

### Special Constructs

- **FunctionDef**: Function definitions
- **SubshellGroup**: Subshell commands `(...)`
- **BraceGroup**: Brace groups `{...}`
- **ArithmeticEvaluation**: Arithmetic expressions `$((...))`
- **ArrayAssignment**: Array operations

## Advanced Usage

### Custom Parser Factory

```python
from psh.parser import ParserFactory

# Create parser with custom configuration
parser = ParserFactory.create_custom_parser(
    tokens,
    source_text=source,
    enable_functions=False,
    enable_arrays=True,
    error_handling=ErrorHandlingMode.RECOVER
)
```

### Parser Context Access

```python
# Access parser context for advanced use cases
parser = Parser(tokens)
context = parser.context

# Check parsing state
if context.in_function_body:
    # Special handling for function bodies
    pass

# Access collected errors
for error in context.errors:
    print(error)
```

### Performance Profiling

```python
config = ParserConfig(profile_parsing=True)
parser = Parser(tokens, config=config)
ast = parser.parse()

# Get profiling data
if parser.context.profiler:
    stats = parser.context.profiler.get_stats()
    print(f"Parse time: {stats.total_time}")
    print(f"Token count: {stats.token_count}")
```

## Common Patterns

### Error-Tolerant Parsing

```python
# Parse and continue on errors
config = ParserConfig(
    collect_errors=True,
    enable_error_recovery=True,
    max_errors=50
)
parser = Parser(tokens, config=config)
result = parser.parse_with_error_collection()

# Process results
if result.ast:
    process_ast(result.ast)
    
# Report errors
for error in result.errors:
    report_error(error)
```

### Strict POSIX Parsing

```python
# Enforce POSIX compliance
from psh.parser import parse_strict_posix

try:
    ast = parse_strict_posix(tokens)
except ParseError as e:
    print(f"Not POSIX compliant: {e.message}")
```

### Incremental Parsing (Future)

```python
# Parse partial input (planned feature)
parser = Parser(tokens, config=ParserConfig(allow_incomplete=True))
partial_ast = parser.parse_partial()
```

## Best Practices

1. **Choose the Right Mode**: Use strict modes for validation, permissive for compatibility
2. **Handle Errors Gracefully**: Use error collection for IDEs and tools
3. **Provide Source Text**: Include original source for better error messages
4. **Configure Features**: Disable unused features for better performance
5. **Validate AST**: Use `parse_and_validate()` for semantic checking

## Thread Safety

The parser is **not thread-safe**. Create separate parser instances for concurrent parsing.

## Performance Considerations

- Token list is processed sequentially
- No backtracking in most cases (except specific ambiguities)
- Memory usage proportional to AST size
- Use profiling to identify bottlenecks

## Version Compatibility

This API is stable as of PSH version 0.91.4. Future versions will maintain backward compatibility for the core API while potentially adding new features and configuration options.