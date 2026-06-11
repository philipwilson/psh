# Parser Combinator Implementation: A Programmer's Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Core Concepts](#core-concepts)
3. [Architecture Overview](#architecture-overview)
4. [Basic Parser Combinators](#basic-parser-combinators)
5. [Building Complex Parsers](#building-complex-parsers)
6. [Shell-Specific Parsers](#shell-specific-parsers)
7. [AST Construction](#ast-construction)
8. [Error Handling](#error-handling)
9. [Advanced Techniques](#advanced-techniques)
10. [Testing Parser Combinators](#testing-parser-combinators)
11. [Performance Considerations](#performance-considerations)
12. [Extending the Parser](#extending-the-parser)

## Introduction

The PSH parser combinator implementation demonstrates how to build a complete shell parser using functional programming techniques. Unlike traditional recursive descent parsers that use imperative control flow, parser combinators compose small, reusable parsing functions into larger ones.

### Why Parser Combinators?

Parser combinators offer several advantages:
- **Composability**: Complex parsers are built from simple, reusable components
- **Type Safety**: Strong typing ensures parsers compose correctly
- **Readability**: Grammar rules map directly to code
- **Testability**: Individual parsers can be tested in isolation
- **Backtracking**: Natural support for trying alternatives

## Core Concepts

### Parser Type

At the heart of the implementation is the `Parser[T]` type:

```python
class Parser(Generic[T]):
    """A parser combinator that produces values of type T."""
    
    def __init__(self, parse_fn: Callable[[List[Token], int], ParseResult[T]]):
        """Initialize with a parsing function."""
        self.parse_fn = parse_fn
    
    def parse(self, tokens: List[Token], position: int = 0) -> ParseResult[T]:
        """Execute the parser."""
        return self.parse_fn(tokens, position)
```

A parser is simply a function that:
- Takes a list of tokens and a position
- Returns a `ParseResult` containing success/failure, the parsed value, and the new position

### Parse Result

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

This structure allows parsers to communicate:
- Whether parsing succeeded
- The parsed value (if successful)
- The position after parsing
- Error information (if failed)

## Architecture Overview

The parser combinator implementation follows a layered architecture:

```
┌─────────────────────────────────────┐
│         Shell Grammar Rules         │  (Control structures, commands)
├─────────────────────────────────────┤
│      Complex Parser Builders        │  (Statements, pipelines)
├─────────────────────────────────────┤
│      Parser Combinators             │  (sequence, many, optional)
├─────────────────────────────────────┤
│      Basic Token Parsers            │  (token, keyword, literal)
├─────────────────────────────────────┤
│         Token Stream                │  (From lexer)
└─────────────────────────────────────┘
```

## Basic Parser Combinators

### Token Parser

The fundamental building block parses a specific token type:

```python
def token(token_type: str) -> Parser[Token]:
    """Parse a specific token type."""
    def parse_token(tokens: List[Token], pos: int) -> ParseResult[Token]:
        if pos < len(tokens) and tokens[pos].type.name == token_type:
            return ParseResult(
                success=True,
                value=tokens[pos],
                position=pos + 1
            )
        error = f"Expected {token_type}"
        if pos < len(tokens):
            error += f", got {tokens[pos].type.name}"
        else:
            error += ", but reached end of input"
        return ParseResult(success=False, error=error, position=pos)
    
    return Parser(parse_token)
```

Usage:
```python
word_parser = token('WORD')
pipe_parser = token('PIPE')
```

### Sequence Combinator

Parses multiple parsers in sequence:

```python
def sequence(*parsers: Parser) -> Parser[tuple]:
    """Parse a sequence of parsers."""
    def parse_sequence(tokens: List[Token], pos: int) -> ParseResult[tuple]:
        results = []
        current_pos = pos
        
        for parser in parsers:
            result = parser.parse(tokens, current_pos)
            if not result.success:
                return ParseResult(success=False, error=result.error, position=pos)
            results.append(result.value)
            current_pos = result.position
        
        return ParseResult(
            success=True,
            value=tuple(results),
            position=current_pos
        )
    
    return Parser(parse_sequence)
```

### Many Combinator

Parses zero or more occurrences:

```python
def many(parser: Parser[T]) -> Parser[List[T]]:
    """Parse zero or more occurrences."""
    def parse_many(tokens: List[Token], pos: int) -> ParseResult[List[T]]:
        results = []
        current_pos = pos
        
        while True:
            result = parser.parse(tokens, current_pos)
            if not result.success:
                break
            results.append(result.value)
            current_pos = result.position
        
        return ParseResult(
            success=True,
            value=results,
            position=current_pos
        )
    
    return Parser(parse_many)
```

### Or-Else Combinator

Tries alternatives:

```python
def or_else(self, alternative: 'Parser[T]') -> 'Parser[T]':
    """Try this parser, or alternative if it fails."""
    def choice_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
        result = self.parse(tokens, pos)
        if result.success:
            return result
        return alternative.parse(tokens, pos)
    
    return Parser(choice_parse)
```

### Map Combinator

Transforms parse results:

```python
def map(self, fn: Callable[[T], U]) -> 'Parser[U]':
    """Transform the result of this parser."""
    def mapped_parse(tokens: List[Token], pos: int) -> ParseResult[U]:
        result = self.parse(tokens, pos)
        if result.success:
            return ParseResult(
                success=True,
                value=fn(result.value),
                remaining=result.remaining,
                position=result.position
            )
        return ParseResult(success=False, error=result.error, position=pos)
    
    return Parser(mapped_parse)
```

## Building Complex Parsers

### Simple Command Parser

Here's how we build a parser for simple shell commands:

```python
# First, define token parsers
self.word = token('WORD')
self.string = token('STRING')
self.variable = token('VARIABLE')

# Combine them into word-like tokens
self.word_like = (
    self.word
    .or_else(self.string)
    .or_else(self.variable)
)

# Parse redirections
self.redirection = Parser(parse_redirection)

# Build simple command parser
self.simple_command = sequence(
    many1(self.word_like),      # Command and arguments
    many(self.redirection),      # Optional redirections
    optional(self.ampersand)     # Optional background
).map(lambda triple: self._build_simple_command(
    triple[0], triple[1], background=triple[2] is not None
))
```

### Pipeline Parser

Pipelines are commands separated by pipes:

```python
def build_pipeline(commands):
    """Build pipeline AST, avoiding unnecessary wrapping."""
    if len(commands) == 1:
        # Single command - check if it's a control structure
        cmd = commands[0]
        if isinstance(cmd, (IfConditional, WhileLoop, ForLoop)):
            # Don't wrap control structures
            return cmd
    # Multiple commands - wrap in Pipeline
    return Pipeline(commands=commands) if commands else None

self.pipeline = separated_by(
    self.command,
    self.pipe
).map(build_pipeline)
```

### Control Structure Parsers

Control structures require more complex parsing:

```python
def _build_if_statement(self) -> Parser[IfConditional]:
    """Build parser for if/then/elif/else/fi statements."""
    def parse_if_statement(tokens: List[Token], pos: int) -> ParseResult[IfConditional]:
        # Check for 'if' keyword
        if pos >= len(tokens) or tokens[pos].value != 'if':
            return ParseResult(success=False, error="Expected 'if'", position=pos)
        
        pos += 1  # Skip 'if'
        
        # Parse condition (until 'then')
        condition_tokens = []
        while pos < len(tokens) and tokens[pos].value != 'then':
            condition_tokens.append(tokens[pos])
            pos += 1
        
        # Parse the condition
        condition_result = self.statement_list.parse(condition_tokens, 0)
        if not condition_result.success:
            return ParseResult(success=False, error="Failed to parse condition", position=pos)
        
        # Continue parsing then-part, elif-parts, else-part...
        # ... (implementation details)
        
        return ParseResult(
            success=True,
            value=IfConditional(
                condition=condition,
                then_part=then_part,
                elif_parts=elif_parts,
                else_part=else_part
            ),
            position=pos
        )
    
    return Parser(parse_if_statement)
```

## Shell-Specific Parsers

### Here Document Parser

Here documents require special handling:

```python
# Handle heredoc operators
if op_token.type.name in ['HEREDOC', 'HEREDOC_STRIP']:
    # Parse delimiter
    delimiter_result = self.word_like.parse(tokens, pos)
    if not delimiter_result.success:
        return ParseResult(
            success=False,
            error=f"Expected heredoc delimiter after {op_token.value}",
            position=pos
        )
    
    delimiter = delimiter_result.value.value
    
    # Check if delimiter is quoted (affects variable expansion)
    heredoc_quoted = delimiter.startswith(("'", '"'))
    
    # Create redirect with heredoc metadata
    redirect = Redirect(
        type=op_token.value,
        target=delimiter.strip("'\""),
        heredoc_quoted=heredoc_quoted
    )
```

### Array Assignment Parser

Arrays have complex syntax patterns:

```python
def _detect_array_pattern(self, tokens: List[Token], pos: int) -> str:
    """Detect what type of array pattern we have."""
    if pos >= len(tokens) or tokens[pos].type.name != 'WORD':
        return 'none'
    
    word_token = tokens[pos]
    
    # Check for array element assignment: arr[index]=value
    if '[' in word_token.value and ']' in word_token.value:
        if '=' in word_token.value:
            return 'element_assignment'
    
    # Check for array initialization: arr=(elements)
    if word_token.value.endswith('='):
        if pos + 1 < len(tokens) and tokens[pos + 1].type.name == 'LPAREN':
            return 'initialization'
    
    return 'none'
```

### Select Loop Parser

Select loops demonstrate comprehensive token handling:

```python
def _build_select_loop(self) -> Parser[SelectLoop]:
    """Build parser for select/do/done loops."""
    def parse_select_loop(tokens: List[Token], pos: int) -> ParseResult[SelectLoop]:
        # Parse 'select' keyword
        if tokens[pos].value != 'select':
            return ParseResult(success=False, error="Expected 'select'", position=pos)
        
        pos += 1
        
        # Parse variable name
        var_name = tokens[pos].value
        pos += 1
        
        # Parse items (supporting various token types)
        items = []
        while pos < len(tokens):
            token = tokens[pos]
            if token.value == 'do':
                break
            
            # Handle different token types
            if token.type.name == 'VARIABLE':
                items.append(f'${token.value}')
            else:
                items.append(token.value)
            pos += 1
        
        # Parse body...
        # Return SelectLoop AST node
```

## AST Construction

### Word Building

Words in shell can contain multiple parts:

```python
def _build_word_from_token(self, token: Token) -> Word:
    """Build a Word AST node from a token."""
    if token.type.name == 'STRING':
        # String token - check for quote type
        quote_type = getattr(token, 'quote_type', None)
        return Word(parts=[LiteralPart(token.value)], quote_type=quote_type)
    
    elif token.type.name == 'VARIABLE':
        # Variable expansion
        expansion = VariableExpansion(token.value)
        return Word(parts=[ExpansionPart(expansion)])
    
    elif token.type.name == 'COMMAND_SUB':
        # Command substitution $(...)
        cmd = token.value[2:-1]  # Remove $( and )
        expansion = CommandSubstitution(cmd, backtick_style=False)
        return Word(parts=[ExpansionPart(expansion)])
    
    else:
        # Regular word token
        return Word(parts=[LiteralPart(token.value)])
```

### AST Unwrapping

Avoid unnecessary wrapper nodes:

```python
def build_pipeline(commands):
    """Build pipeline, but don't wrap single control structures."""
    if len(commands) == 1:
        cmd = commands[0]
        # Check if it's a control structure
        if isinstance(cmd, (IfConditional, WhileLoop, ForLoop)):
            # Return directly without Pipeline wrapper
            return cmd
    # Multiple commands need Pipeline wrapper
    return Pipeline(commands=commands)
```

## Error Handling

### Error Context

Add context to errors for better debugging:

```python
def with_error_context(parser: Parser[T], context: str) -> Parser[T]:
    """Add context to parser errors for better debugging."""
    def contextualized_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
        result = parser.parse(tokens, pos)
        if not result.success and result.error:
            result.error = f"{context}: {result.error}"
        return result
    
    return Parser(contextualized_parse)

# Usage
self.if_statement = with_error_context(
    self._build_if_statement(),
    "In if statement"
)
```

### Error Recovery

Parser combinators naturally support backtracking:

```python
# Try multiple alternatives
self.control_structure = (
    self.if_statement
    .or_else(self.while_loop)
    .or_else(self.for_loop)
    .or_else(self.case_statement)
    .or_else(self.select_loop)
)
```

## Advanced Techniques

### Lazy Evaluation

Handle recursive grammars with lazy evaluation:

```python
def lazy(parser_factory: Callable[[], Parser[T]]) -> Parser[T]:
    """Lazy evaluation for recursive grammars."""
    cache = [None]  # Use list for mutability
    
    def parse_lazy(tokens: List[Token], pos: int) -> ParseResult[T]:
        if cache[0] is None:
            cache[0] = parser_factory()
        return cache[0].parse(tokens, pos)
    
    return Parser(parse_lazy)

# Usage for recursive structures
self.statement_list = lazy(lambda: self._build_statement_list())
```

### Forward Declarations

Handle circular dependencies:

```python
def _setup_forward_declarations(self):
    """Setup forward declarations for recursive grammar rules."""
    self.statement_list_forward = ForwardParser[CommandList]()
    self.command_forward = ForwardParser[Union[SimpleCommand, UnifiedControlStructure]]()

def _build_grammar(self):
    """Build the grammar and define forward references."""
    # ... build parsers ...
    
    # Define forward references
    self.statement_list_forward.define(statement_list_parser)
    self.command_forward.define(self.command)
```

### Two-Pass Parsing

Handle stateful features like here documents:

```python
def parse_with_heredocs(self, tokens: List[Token], 
                       heredoc_contents: Dict[str, str]) -> Union[TopLevel, CommandList]:
    """Parse tokens with heredoc content support.
    
    This is a two-pass approach:
    1. Parse the token stream to build AST
    2. Populate heredoc content in AST nodes
    """
    # Store heredoc contents in parser context
    self.heredoc_contents = heredoc_contents
    
    # First pass: parse normally
    ast = self.parse(tokens)
    
    # Second pass: populate heredoc content
    if heredoc_contents:
        self._populate_heredoc_content(ast, heredoc_contents)
    
    return ast
```

## Testing Parser Combinators

### Unit Testing Individual Parsers

Test parsers in isolation:

```python
def test_word_parser():
    """Test basic word parsing."""
    parser = token('WORD')
    tokens = [Token(type=TokenType.WORD, value='hello', pos=0)]
    
    result = parser.parse(tokens, 0)
    assert result.success
    assert result.value.value == 'hello'
    assert result.position == 1
```

### Integration Testing

Test complex parser combinations:

```python
def test_pipeline_parsing():
    """Test pipeline parsing."""
    parser = ParserCombinatorShellParser()
    tokens = tokenize("echo hello | grep world")
    
    result = parser.parse(tokens)
    assert isinstance(result, CommandList)
    assert len(result.statements) == 1
    
    pipeline = result.statements[0].pipelines[0]
    assert isinstance(pipeline, Pipeline)
    assert len(pipeline.commands) == 2
```

### Property-Based Testing

Use property-based testing for robustness:

```python
from hypothesis import given, strategies as st

@given(st.lists(st.sampled_from(['echo', 'grep', 'cat', 'sort'])))
def test_pipeline_with_any_commands(commands):
    """Test pipeline parsing with arbitrary commands."""
    if not commands:
        return
    
    cmd_str = " | ".join(commands)
    tokens = tokenize(cmd_str)
    parser = ParserCombinatorShellParser()
    
    result = parser.parse(tokens)
    # Should parse successfully
    assert isinstance(result, CommandList)
```

## Performance Considerations

### Memoization

Cache parse results for performance:

```python
def memoize(parser: Parser[T]) -> Parser[T]:
    """Memoize parser results."""
    cache = {}
    
    def memoized_parse(tokens: List[Token], pos: int) -> ParseResult[T]:
        # Create cache key from position and next few tokens
        key = (pos, tuple(tokens[pos:pos+3]))
        
        if key in cache:
            return cache[key]
        
        result = parser.parse(tokens, pos)
        cache[key] = result
        return result
    
    return Parser(memoized_parse)
```

### Avoiding Excessive Backtracking

Order alternatives from most specific to least:

```python
# Good: Try specific patterns first
self.control_structure = (
    self.if_statement        # Most specific
    .or_else(self.while_loop)
    .or_else(self.for_loop)
    .or_else(self.simple_command)  # Least specific
)

# Bad: Generic patterns first cause unnecessary backtracking
self.control_structure = (
    self.simple_command      # Too generic
    .or_else(self.if_statement)
    .or_else(self.while_loop)
)
```

## Extending the Parser

### Adding New Token Types

1. Add token type to lexer
2. Create token parser:
```python
self.new_token = token('NEW_TOKEN')
```

3. Integrate into grammar:
```python
self.word_like = (
    self.word
    .or_else(self.string)
    .or_else(self.new_token)  # Add here
)
```

### Adding New Control Structures

1. Define AST node:
```python
@dataclass
class NewStructure(ASTNode):
    condition: CommandList
    body: CommandList
```

2. Create parser:
```python
def _build_new_structure(self) -> Parser[NewStructure]:
    def parse_new_structure(tokens: List[Token], pos: int) -> ParseResult[NewStructure]:
        # Implementation
        pass
    return Parser(parse_new_structure)
```

3. Add to control structure chain:
```python
self.control_structure = (
    self.if_statement
    .or_else(self.new_structure)  # Add here
    .or_else(self.while_loop)
)
```

### Best Practices for Extensions

1. **Start with Tests**: Write tests for the new syntax first
2. **Follow Patterns**: Use existing parsers as templates
3. **Add Error Context**: Use `with_error_context` for debugging
4. **Update Documentation**: Document new syntax and examples
5. **Consider Edge Cases**: Test with malformed input

## Conclusion

Parser combinators provide an elegant, functional approach to parsing complex languages like shell syntax. The key advantages are:

- **Composability**: Build complex parsers from simple ones
- **Maintainability**: Grammar rules map directly to code
- **Testability**: Test parsers in isolation
- **Extensibility**: Easy to add new syntax

The PSH parser combinator implementation demonstrates that this approach can handle production-level complexity while maintaining clarity and educational value. By understanding these patterns and techniques, you can extend the parser or apply similar approaches to other language parsing challenges.