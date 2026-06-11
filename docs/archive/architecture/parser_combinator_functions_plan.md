# Parser Combinator Shell Functions Implementation Plan

## Overview

This document outlines the plan for adding shell function support to the PSH parser combinator implementation. Shell functions are a fundamental feature that allows users to define reusable command sequences.

## Shell Function Syntax

Shell functions support two primary syntax forms:

```bash
# Traditional POSIX syntax
name() {
    commands
}

# Bash/ksh syntax with function keyword
function name {
    commands
}

# Bash/ksh with parentheses
function name() {
    commands
}
```

## Current State Analysis

### AST Node

The AST already has a `FunctionDef` node:
```python
@dataclass
class FunctionDef(Statement):
    """Function definition."""
    name: str
    body: StatementList
```

### Recursive Descent Parser

The recursive descent parser handles functions in:
- `functions.py`: Contains `parse_function_def()` method
- Checks for both `function` keyword and `name()` patterns
- Supports optional parentheses after function name

### Parser Combinator

Currently, the parser combinator does not support function definitions.

## Implementation Plan

### Phase 1: Basic Function Definition Parsing

#### 1.1 Token Recognition

First, ensure the lexer properly tokenizes:
- `function` keyword (may be `FUNCTION` or `WORD` token)
- Function names (WORD tokens)
- Parentheses `()` (LPAREN, RPAREN tokens)
- Braces `{}` (LBRACE, RBRACE tokens)

#### 1.2 Function Name Parser

```python
def _build_function_name() -> Parser[str]:
    """Parse a valid function name."""
    def parse_function_name(tokens: List[Token], pos: int) -> ParseResult[str]:
        if pos >= len(tokens):
            return ParseResult(success=False, error="Expected function name", position=pos)
        
        token = tokens[pos]
        if token.type.name != 'WORD':
            return ParseResult(success=False, error="Expected function name", position=pos)
        
        # Validate function name (alphanumeric and underscore)
        name = token.value
        if not name.replace('_', '').isalnum():
            return ParseResult(success=False, error=f"Invalid function name: {name}", position=pos)
        
        # Check it's not a reserved word
        reserved = {'if', 'then', 'else', 'elif', 'fi', 'while', 'do', 'done', 
                   'for', 'case', 'esac', 'function'}
        if name in reserved:
            return ParseResult(success=False, error=f"Reserved word cannot be function name: {name}", position=pos)
        
        return ParseResult(success=True, value=name, position=pos + 1)
    
    return Parser(parse_function_name)
```

#### 1.3 Function Definition Parsers

Three variants to support all syntax forms:

```python
def _build_function_def() -> Parser[FunctionDef]:
    """Build parser for function definitions."""
    # All three forms
    return (
        self._build_posix_function()
        .or_else(self._build_function_keyword_style())
        .or_else(self._build_function_keyword_with_parens())
    )

def _build_posix_function() -> Parser[FunctionDef]:
    """Parse POSIX-style function: name() { body }"""
    def parse_posix_function(tokens: List[Token], pos: int) -> ParseResult[FunctionDef]:
        # Parse name
        name_result = self.function_name.parse(tokens, pos)
        if not name_result.success:
            return ParseResult(success=False, error="Not a function definition", position=pos)
        
        name = name_result.value
        pos = name_result.position
        
        # Expect ()
        if pos + 1 >= len(tokens) or tokens[pos].value != '(' or tokens[pos + 1].value != ')':
            return ParseResult(success=False, error="Expected () after function name", position=pos)
        pos += 2
        
        # Skip optional whitespace/newlines
        while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE']:
            pos += 1
        
        # Parse body
        body_result = self._parse_function_body(tokens, pos)
        if not body_result.success:
            return ParseResult(success=False, error=body_result.error, position=pos)
        
        return ParseResult(
            success=True,
            value=FunctionDef(name=name, body=body_result.value),
            position=body_result.position
        )
    
    return Parser(parse_posix_function)
```

#### 1.4 Function Body Parser

```python
def _parse_function_body(self, tokens: List[Token], pos: int) -> ParseResult[StatementList]:
    """Parse function body between { }."""
    # Expect {
    if pos >= len(tokens) or tokens[pos].value != '{':
        return ParseResult(success=False, error="Expected '{' to start function body", position=pos)
    pos += 1
    
    # Skip optional newline after {
    if pos < len(tokens) and tokens[pos].type.name == 'NEWLINE':
        pos += 1
    
    # Collect tokens until }
    body_tokens = []
    brace_count = 1
    
    while pos < len(tokens) and brace_count > 0:
        token = tokens[pos]
        if token.value == '{':
            brace_count += 1
        elif token.value == '}':
            brace_count -= 1
            if brace_count == 0:
                break
        body_tokens.append(token)
        pos += 1
    
    if brace_count > 0:
        return ParseResult(success=False, error="Unclosed function body", position=pos)
    
    # Parse the body as a statement list
    body_result = self.statement_list.parse(body_tokens, 0)
    if not body_result.success:
        return ParseResult(success=False, error=f"Invalid function body: {body_result.error}", position=pos)
    
    pos += 1  # Skip closing }
    
    return ParseResult(
        success=True,
        value=body_result.value,
        position=pos
    )
```

### Phase 2: Integration with Grammar

#### 2.1 Update _build_grammar()

Add function definition to the main grammar:

```python
def _build_grammar(self):
    # ... existing code ...
    
    # Build function support
    self.function_name = self._build_function_name()
    self.function_def = with_error_context(
        self._build_function_def(),
        "In function definition"
    )
    
    # Update command to include functions
    self.command = (
        self.simple_command
        .or_else(self.control_structure)
        .or_else(self.function_def)
    )
```

#### 2.2 Handle Functions at Statement Level

Functions can appear at the top level, so update statement parsing:

```python
# In statement list, functions are statements
self.statement = (
    self.and_or_list
    .or_else(self.function_def)
)
```

### Phase 3: Advanced Features

#### 3.1 Local Variables and Return

While parsing handles the syntax, execution features include:
- Local variables with `local` builtin
- Return values with `return` builtin
- Function parameters as $1, $2, etc.

#### 3.2 Function Body Scoping

Functions create a new scope for:
- Local variables
- Positional parameters
- Return statements only valid inside functions

#### 3.3 Nested Functions

Shell functions can contain other function definitions:

```bash
outer() {
    inner() {
        echo "Inner function"
    }
    inner
}
```

### Phase 4: Testing Strategy

#### 4.1 Unit Tests

```python
def test_posix_function():
    """Test POSIX-style function definition."""
    ast = parse("greet() { echo Hello; }")
    assert isinstance(ast.statements[0], FunctionDef)
    assert ast.statements[0].name == "greet"

def test_function_keyword():
    """Test function keyword syntax."""
    ast = parse("function greet { echo Hello; }")
    assert isinstance(ast.statements[0], FunctionDef)

def test_function_with_complex_body():
    """Test function with control structures."""
    ast = parse("""
        process_files() {
            for f in *.txt; do
                if test -f "$f"; then
                    cat "$f"
                fi
            done
        }
    """)
    func = ast.statements[0]
    assert isinstance(func.body.statements[0], ForLoop)
```

#### 4.2 Integration Tests

- Functions with parameters
- Functions calling other functions
- Functions with local variables
- Functions in pipelines
- Recursive functions

#### 4.3 Error Cases

- Invalid function names
- Missing braces
- Unclosed function bodies
- Reserved words as names

### Phase 5: Implementation Timeline

#### Day 1: Basic Parsing
- [ ] Implement function name parser
- [ ] Implement POSIX-style function parser
- [ ] Implement function keyword parsers
- [ ] Add function body parser

#### Day 2: Grammar Integration
- [ ] Update main grammar
- [ ] Integrate with statement parsing
- [ ] Handle function definitions at top level
- [ ] Test basic function parsing

#### Day 3: Advanced Features & Testing
- [ ] Handle nested functions
- [ ] Create comprehensive test suite
- [ ] Test error cases
- [ ] Compare with recursive descent parser

## Success Criteria

1. **Syntax Support**: All three function definition forms parse correctly
2. **AST Generation**: Produces correct FunctionDef nodes
3. **Integration**: Functions work alongside other statements
4. **Error Handling**: Clear messages for syntax errors
5. **Test Coverage**: Comprehensive unit and integration tests

## Future Enhancements

After basic function support:
1. Function export (`export -f`)
2. Function listing (`declare -f`)
3. Anonymous functions
4. Function attributes
5. Debugging support (`set -x` in functions)

## Example Implementation

```python
# Complete function in a script
#!/bin/bash

# POSIX style
calculate() {
    local a=$1
    local b=$2
    echo $((a + b))
}

# Function keyword
function process_data {
    while read line; do
        calculate $line 10
    done
}

# Usage
echo "5" | process_data  # Output: 15
```

This implementation will make the parser combinator feature-complete for basic shell function support, demonstrating how complex language features can be elegantly handled with functional parsing techniques.