# Parser Combinator Architecture Documentation

## Overview

The PSH parser combinator implementation demonstrates functional parsing techniques by building complex parsers from simple, composable primitives. This architecture provides an elegant alternative to the traditional recursive descent parser, emphasizing modularity, type safety, and functional composition.

## Core Architecture

### 1. Foundation Types

#### ParseResult
```python
@dataclass
class ParseResult(Generic[T]):
    """Result of a parse operation."""
    success: bool
    value: Optional[T] = None
    remaining: List[Token] = None
    position: int = 0
    error: Optional[str] = None
```

The `ParseResult` type encapsulates:
- Success/failure status
- Parsed value (generic type T)
- Remaining tokens (for partial parsing)
- Current position in token stream
- Error message for failures

#### Parser
```python
class Parser(Generic[T]):
    """A parser combinator that produces values of type T."""
    
    def __init__(self, parse_fn: Callable[[List[Token], int], ParseResult[T]]):
        self.parse_fn = parse_fn
    
    def parse(self, tokens: List[Token], position: int = 0) -> ParseResult[T]:
        return self.parse_fn(tokens, position)
```

The `Parser` class wraps a parsing function and provides combinator methods.

### 2. Basic Combinators

#### Primitive Parsers
- `token(type: str)` - Matches a specific token type
- `keyword(kw: str)` - Matches a specific keyword
- `literal(lit: str)` - Matches a literal value

#### Combinator Methods
- `map(fn)` - Transform parse results
- `then(next)` - Sequential composition
- `or_else(alt)` - Alternative composition

#### Higher-Order Combinators
- `many(p)` - Zero or more occurrences
- `many1(p)` - One or more occurrences
- `optional(p)` - Zero or one occurrence
- `separated_by(p, sep)` - Parse separated lists
- `between(open, close, p)` - Parse between delimiters

### 3. Advanced Features

#### Forward Declarations
```python
class ForwardParser(Parser[T], Generic[T]):
    """Parser that can be defined later for handling circular references."""
```

Enables recursive grammars by deferring parser definition.

#### Error Context
```python
def with_error_context(parser: Parser[T], context: str) -> Parser[T]:
    """Add context to parser errors for better debugging."""
```

Enhances error messages with contextual information.

#### Lazy Evaluation
```python
def lazy(parser_factory: Callable[[], Parser[T]]) -> Parser[T]:
    """Lazy evaluation for recursive grammars."""
```

Defers parser construction until first use.

## Grammar Structure

### 1. Token Level
```python
# Basic tokens
self.word = token('WORD')
self.string = token('STRING')
self.pipe = token('PIPE')
self.semicolon = token('SEMICOLON')
```

### 2. Command Level
```python
# Simple command
self.simple_command = sequence(
    many1(self.word_like),
    many(self.redirection)
).map(lambda pair: SimpleCommand(
    args=[t.value for t in pair[0]],
    redirects=pair[1]
))
```

### 3. Control Structures
Each control structure has a dedicated builder method:
- `_build_if_statement()` - If/then/elif/else/fi
- `_build_while_loop()` - While/do/done
- `_build_for_loops()` - Traditional and C-style for loops
- `_build_case_statement()` - Case/esac with patterns

### 4. Statement Composition
```python
# Pipeline
self.pipeline = separated_by(self.command, self.pipe)

# And-or list
self.and_or_list = sequence(
    self.pipeline,
    many(sequence(self.and_or_operator, self.pipeline))
)

# Statement list
self.statement_list = separated_by(
    self.and_or_list,
    self.separator
)
```

## Design Patterns

### 1. Builder Pattern
Each complex parser is built using a dedicated method:
```python
def _build_if_statement(self) -> Parser[IfConditional]:
    """Build parser for if/then/elif/else/fi statements."""
```

### 2. Composition Pattern
Complex parsers are composed from simpler ones:
```python
self.control_structure = (
    self.if_statement
    .or_else(self.while_loop)
    .or_else(self.for_loop)
    .or_else(self.case_statement)
)
```

### 3. Transformation Pattern
Parse results are transformed into AST nodes:
```python
.map(lambda parts: IfConditional(
    condition=parts[0],
    then_part=parts[1],
    elif_parts=parts[2],
    else_part=parts[3]
))
```

## Control Flow

### 1. Parser Initialization
```python
def __init__(self):
    super().__init__()
    self._setup_forward_declarations()
    self._build_grammar()
    self._complete_forward_declarations()
```

### 2. Parse Execution
1. Tokenization (external)
2. Token filtering (remove EOF)
3. Grammar application
4. Result validation
5. AST construction

### 3. Error Handling
- Early failure with descriptive messages
- Position tracking for error location
- Context wrapping for better diagnostics

## Performance Characteristics

### Time Complexity
- **Token matching**: O(1)
- **Sequence parsing**: O(n) where n is sequence length
- **Alternative parsing**: O(k) where k is number of alternatives
- **Backtracking**: Limited, mostly for alternatives

### Space Complexity
- **Parser construction**: O(g) where g is grammar size
- **Parse execution**: O(t) where t is token count
- **AST construction**: O(n) where n is node count

## Missing Features

### 1. Core Shell Features

#### Command Substitution
```bash
echo $(date)
echo `date`
```
- Requires recursive parsing
- Needs integration with shell execution

#### Arithmetic Expansion
```bash
echo $((2 + 2))
echo $[2 + 2]
```
- Requires arithmetic expression parser
- Integer and floating-point support

#### Process Substitution
```bash
diff <(sort file1) <(sort file2)
```
- Already has AST node
- Needs parser implementation

#### Here Documents
```bash
cat <<EOF
multi-line
text
EOF
```
- Complex tokenization requirements
- Delimiter tracking

### 2. Advanced Control Structures

#### Select Loops
```bash
select item in option1 option2; do
    echo "You selected $item"
done
```
- Similar to for loops
- Interactive menu support

#### Coproc
```bash
coproc MY_COPROC {
    command
}
```
- Bidirectional pipe support
- Named coprocesses

#### Function Definitions
```bash
function name() {
    commands
}
```
- Plan already created
- Three syntax variants

### 3. Expansion Features

#### Brace Expansion
```bash
echo {a,b,c}
echo {1..10}
```
- Complex parsing rules
- Nested brace support

#### Tilde Expansion
```bash
cd ~
cd ~user
```
- Home directory resolution
- User lookup

#### Parameter Expansion
```bash
${var:-default}
${var#pattern}
${var//search/replace}
```
- Complex syntax variations
- Pattern matching

### 4. Redirections

#### Advanced Redirections
```bash
exec 3< file
command <&3
command >&2
```
- File descriptor manipulation
- Duplication operators

#### Here Strings
```bash
command <<< "string"
```
- Single-line here documents
- Quote handling

### 5. Job Control

#### Background/Foreground
```bash
command &
fg %1
bg %2
```
- Job tracking
- Process group management

### 6. Advanced Features

#### Aliases
```bash
alias ll='ls -l'
```
- Preprocessing phase
- Recursive expansion

#### Arrays
```bash
arr=(a b c)
echo ${arr[0]}
```
- Array literals
- Subscript parsing

#### Associative Arrays
```bash
declare -A hash
hash[key]=value
```
- Key-value pairs
- Declaration tracking

#### Compound Commands
```bash
{ command1; command2; }
(command1; command2)
```
- Command grouping
- Subshell execution

### 7. Parser Enhancements

#### Memoization
```python
def memoize(parser: Parser[T]) -> Parser[T]:
    """Cache parser results by position."""
```
- Performance optimization
- Memory trade-off

#### Error Recovery
```python
def recover(parser: Parser[T], recovery: Parser[T]) -> Parser[T]:
    """Continue parsing after errors."""
```
- Partial parse results
- IDE integration

#### Incremental Parsing
```python
def incremental(parser: Parser[T]) -> IncrementalParser[T]:
    """Support incremental updates."""
```
- Efficient reparsing
- Editor integration

#### Streaming Support
```python
def stream(parser: Parser[T]) -> StreamParser[T]:
    """Parse token streams lazily."""
```
- Large file support
- Memory efficiency

## Implementation Priorities

### High Priority
1. **Function Definitions** - Core shell feature
2. **Command Substitution** - Very common usage
3. **Here Documents** - Script compatibility
4. **Advanced Redirections** - I/O flexibility

### Medium Priority
1. **Arithmetic Expansion** - Mathematical operations
2. **Parameter Expansion** - Variable manipulation
3. **Process Substitution** - Advanced I/O
4. **Arrays** - Data structures

### Low Priority
1. **Select Loops** - Interactive features
2. **Coproc** - Advanced process control
3. **Associative Arrays** - Advanced data structures
4. **Job Control** - Interactive shell features

## Testing Considerations

### Parser Testing
- Unit tests for each combinator
- Integration tests for feature combinations
- Property-based testing for parser properties
- Fuzzing for robustness

### Comparison Testing
- AST equivalence with recursive descent
- Performance benchmarking
- Memory usage profiling
- Error message quality

## Conclusion

The parser combinator architecture provides a clean, functional approach to shell parsing. While missing some advanced features, it successfully demonstrates:

1. **Modularity** - Small, focused parsers
2. **Composability** - Building complex from simple
3. **Type Safety** - Generic types throughout
4. **Maintainability** - Clear separation of concerns
5. **Extensibility** - Easy to add new features

The architecture serves as an excellent educational tool for understanding both functional programming and parsing techniques, while providing a solid foundation for future enhancements.