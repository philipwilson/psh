# Phase 2: Expansion AST Nodes Implementation

## Overview
This document describes the implementation of AST nodes for representing shell expansions (command substitution, parameter expansion, etc.) in the parse tree.

## Implemented AST Nodes

### 1. Expansion Base Class
```python
class Expansion(ASTNode):
    """Base class for all types of expansions."""
```

### 2. Variable Expansion
```python
@dataclass
class VariableExpansion(Expansion):
    """Represents simple variable expansion $var."""
    name: str  # Variable name without $
```
- Examples: `$USER`, `$HOME`, `$PATH`

### 3. Command Substitution
```python
@dataclass
class CommandSubstitution(Expansion):
    """Represents command substitution $(...) or `...`."""
    command: str  # The command to execute
    backtick_style: bool = False  # True for `...`, False for $(...)
```
- Examples: `$(date)`, `$(echo hello)`, `` `hostname` ``

### 4. Parameter Expansion
```python
@dataclass
class ParameterExpansion(Expansion):
    """Represents parameter expansion ${...}."""
    parameter: str  # Variable name
    operator: Optional[str] = None  # :-, :=, :?, :+, #, ##, %, %%, /, // etc.
    word: Optional[str] = None  # The word part for operators like ${var:-word}
```
- Examples: `${USER:-nobody}`, `${PATH##*/}`, `${#VAR}`

### 5. Arithmetic Expansion
```python
@dataclass
class ArithmeticExpansion(Expansion):
    """Represents arithmetic expansion $((...))."""
    expression: str  # The arithmetic expression
```
- Examples: `$((2 + 2))`, `$((i++))`, `$((x * 10))`

## Word AST Nodes

### Word Structure
```python
@dataclass
class Word(ASTNode):
    """A word that may contain expansions."""
    parts: List[WordPart] = field(default_factory=list)
    quote_type: Optional[str] = None  # None (unquoted), '"' (double), "'" (single)
```

A Word consists of parts, where each part is either:
- `LiteralPart`: Literal text
- `ExpansionPart`: An expansion (variable, command substitution, etc.)

### Examples
- `"hello"` → `[LiteralPart("hello")]`
- `"$USER"` → `[ExpansionPart(VariableExpansion("USER"))]`
- `"Hello $USER!"` → `[LiteralPart("Hello "), ExpansionPart(VariableExpansion("USER")), LiteralPart("!")]`

## Parser Integration

### SimpleCommand Enhancement
```python
@dataclass
class SimpleCommand(Command):
    # ... existing fields ...
    
    # New field for storing Word objects
    words: Optional[List[Word]] = None
```

The `words` field is optional for backward compatibility. When enabled via parser configuration, it contains Word objects representing arguments with proper expansion information.

### Parser Configuration
```python
# In ParserConfig
build_word_ast_nodes: bool = False  # Build Word AST nodes with expansion info
```

### Word Builder Utility
The `WordBuilder` class provides utilities for:
- Parsing expansion tokens into Expansion AST nodes
- Building Word objects from tokens
- Handling composite words with mixed literal/expansion content

## Usage Example

```python
# Enable Word AST creation
config = ParserConfig(build_word_ast_nodes=True)
parser = RecursiveDescentAdapter()
parser.config = config

# Parse command with expansions
tokens = tokenize("echo $USER $(date) ${HOME:-/tmp}")
ast = parser.parse(tokens)

# Access Word objects
cmd = ast.statements[0].pipelines[0].commands[0]
for word in cmd.words:
    print(f"Word: {word}")
    for part in word.parts:
        if isinstance(part, ExpansionPart):
            print(f"  Expansion: {type(part.expansion).__name__}")
```

## Benefits

1. **Proper AST Representation**: Expansions are now properly represented in the AST instead of being flattened to strings
2. **Type Safety**: Each expansion type has its own class with appropriate fields
3. **Evaluation Ready**: The structured AST makes it easier to implement expansion evaluation
4. **Backward Compatible**: The feature is opt-in via configuration
5. **Parser Agnostic**: The AST nodes can be used by any parser implementation

## Parser Combinator Support (Completed)

The parser combinator now also supports creating Word AST nodes when configured:

```python
# Enable Word AST creation
parser = ParserCombinatorShellParser()
parser.config = ParserConfig(build_word_ast_nodes=True)

# Parse command with expansions
tokens = tokenize("echo $USER $(date)")
ast = parser.parse(tokens)

# Access Word objects
cmd = ast.statements[0].pipelines[0].commands[0]
for word in cmd.words:
    print(f"Word: {word}")
    for part in word.parts:
        if isinstance(part, ExpansionPart):
            print(f"  Expansion: {type(part.expansion).__name__}")
```

### Implementation Details

1. **Token to Word Mapping**: The `_build_word_from_token` method converts tokens to Word AST nodes
2. **Expansion Parsing**: Each expansion type is properly parsed and wrapped in ExpansionPart
3. **Backward Compatibility**: The feature remains opt-in via configuration
4. **Full Parity**: Both parsers now support identical Word AST creation

## Next Steps

1. **Expansion Evaluation**: Implement the actual evaluation of expansions in the executor
2. **Quoted String Parsing**: Handle expansions within quoted strings  
3. **Composite Word Support**: Better support for words with mixed literal/expansion content
4. **Here Document Support**: Add lexer and AST support for here documents