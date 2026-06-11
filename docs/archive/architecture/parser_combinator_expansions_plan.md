# Parser Combinator Expansions Implementation Plan

## Overview

This document outlines the plan for implementing three critical shell features in the PSH parser combinator:
1. Command Substitution (`$(...)` and `` `...` ``)
2. Here Documents (`<<EOF` and `<<-EOF`)
3. Parameter Expansion (`${var}` and its variants)

These features are essential for shell script compatibility and represent some of the most complex parsing challenges in shell implementation.

## Current State Analysis

### Lexer Support
The lexer already tokenizes some of these constructs:
- `VARIABLE` tokens for `$var`
- `ARITH_EXPANSION` for `$((...))`
- String tokens with embedded variables

### AST Nodes
Some AST support exists:
- `Redirect` node has `heredoc_content` and `heredoc_quoted` fields
- No specific nodes for command substitution or parameter expansion

### Parser Status
- Basic variable references (`$var`) are handled as VARIABLE tokens
- No support for command substitution
- No support for here documents
- No support for complex parameter expansion

## Implementation Plan

### Phase 1: Command Substitution

Command substitution allows capturing command output: `$(command)` or `` `command` ``

#### 1.1 Lexer Modifications

The lexer needs to recognize command substitution as a special token type:

```python
# New token types needed
COMMAND_SUBSTITUTION = "COMMAND_SUBSTITUTION"  # $(...)
BACKTICK_SUBSTITUTION = "BACKTICK_SUBSTITUTION"  # `...`
```

#### 1.2 AST Node Design

```python
@dataclass
class CommandSubstitution(ASTNode):
    """Represents command substitution $(cmd) or `cmd`."""
    command: Union[str, StatementList]  # Raw string or parsed AST
    style: str  # "modern" for $(), "backtick" for ``
    is_nested: bool = False  # True if inside another substitution
```

#### 1.3 Parser Implementation

```python
def _build_command_substitution(self) -> Parser[CommandSubstitution]:
    """Parse command substitution $(...) or `...`."""
    def parse_command_sub(tokens: List[Token], pos: int) -> ParseResult[CommandSubstitution]:
        if pos >= len(tokens):
            return ParseResult(success=False, error="Expected command substitution", position=pos)
        
        token = tokens[pos]
        if token.type.name == 'COMMAND_SUBSTITUTION':
            # Extract command from $(...) - need to parse the content
            content = token.value[2:-1]  # Remove $( and )
            # Parse content as a statement list
            sub_tokens = tokenize(content)
            sub_result = self.statement_list.parse(sub_tokens, 0)
            
            if sub_result.success:
                return ParseResult(
                    success=True,
                    value=CommandSubstitution(
                        command=sub_result.value,
                        style="modern"
                    ),
                    position=pos + 1
                )
        elif token.type.name == 'BACKTICK_SUBSTITUTION':
            # Similar for backticks
            content = token.value[1:-1]  # Remove backticks
            # ...
    
    return Parser(parse_command_sub)
```

#### 1.4 Integration Points

- Add to `word_like` tokens for use in commands
- Handle nested substitutions (e.g., `$(echo $(date))`)
- Integrate with string parsing for embedded substitutions

### Phase 2: Here Documents

Here documents provide multi-line string input: `command <<EOF`

#### 2.1 Lexer Modifications

Here documents require special lexer handling:
- Recognize `<<` and `<<-` operators
- Track delimiter word
- Collect lines until delimiter is found
- Handle quoted vs unquoted delimiters

```python
# Token types
HEREDOC_START = "HEREDOC_START"  # <<
HEREDOC_STRIP = "HEREDOC_STRIP"  # <<-
HEREDOC_CONTENT = "HEREDOC_CONTENT"  # The actual content
```

#### 2.2 Parser Implementation

```python
def _build_heredoc_redirect(self) -> Parser[Redirect]:
    """Parse here document redirections."""
    def parse_heredoc(tokens: List[Token], pos: int) -> ParseResult[Redirect]:
        # Check for << or <<-
        if pos >= len(tokens):
            return ParseResult(success=False, error="Expected heredoc", position=pos)
        
        token = tokens[pos]
        if token.type.name not in ['HEREDOC_START', 'HEREDOC_STRIP']:
            return ParseResult(success=False, error="Not a heredoc", position=pos)
        
        strip_tabs = token.type.name == 'HEREDOC_STRIP'
        pos += 1
        
        # Get delimiter
        if pos >= len(tokens):
            return ParseResult(success=False, error="Expected heredoc delimiter", position=pos)
        
        delimiter_token = tokens[pos]
        delimiter = delimiter_token.value
        quoted = delimiter_token.type.name == 'STRING'
        pos += 1
        
        # Find heredoc content token
        # This is complex - the lexer needs to provide the content
        # For now, assume lexer provides HEREDOC_CONTENT token
        
        return ParseResult(
            success=True,
            value=Redirect(
                type='<<' if not strip_tabs else '<<-',
                target=delimiter,
                heredoc_quoted=quoted,
                heredoc_content=content  # From lexer
            ),
            position=pos
        )
    
    return Parser(parse_heredoc)
```

#### 2.3 Challenges

1. **Lexer Coordination**: Here documents break normal tokenization flow
2. **Deferred Content**: Content appears after the command line
3. **Multiple Here Docs**: `cmd <<EOF1 <<EOF2`
4. **Nested Structures**: Here docs in functions, loops, etc.

### Phase 3: Parameter Expansion

Parameter expansion provides advanced variable manipulation: `${var:-default}`, `${#var}`, etc.

#### 3.1 Token Recognition

```python
# Token types
PARAM_EXPANSION = "PARAM_EXPANSION"  # ${...} constructs
```

#### 3.2 AST Node Design

```python
@dataclass
class ParameterExpansion(ASTNode):
    """Represents parameter expansion ${...}."""
    variable: str
    operator: Optional[str] = None  # :-, :=, :?, :+, #, ##, %, %%, /, //, etc.
    value: Optional[str] = None  # Default/alternate/pattern
    
class ExpansionOperator(Enum):
    DEFAULT = ":-"          # ${var:-default}
    ASSIGN_DEFAULT = ":="   # ${var:=default}
    ERROR_IF_UNSET = ":?"   # ${var:?error}
    ALTERNATE = ":+"        # ${var:+alternate}
    LENGTH = "#"            # ${#var}
    PREFIX_REMOVE = "#"     # ${var#pattern}
    PREFIX_REMOVE_LONG = "##"
    SUFFIX_REMOVE = "%"
    SUFFIX_REMOVE_LONG = "%%"
    REPLACE = "/"           # ${var/search/replace}
    REPLACE_ALL = "//"
```

#### 3.3 Parser Implementation

```python
def _build_parameter_expansion(self) -> Parser[ParameterExpansion]:
    """Parse parameter expansion ${...}."""
    def parse_param_expansion(tokens: List[Token], pos: int) -> ParseResult[ParameterExpansion]:
        if pos >= len(tokens):
            return ParseResult(success=False, error="Expected parameter expansion", position=pos)
        
        token = tokens[pos]
        if token.type.name != 'PARAM_EXPANSION':
            return ParseResult(success=False, error="Not a parameter expansion", position=pos)
        
        # Parse the content of ${...}
        content = token.value[2:-1]  # Remove ${ and }
        
        # This is complex - need to parse various forms:
        # ${var}
        # ${var:-default}
        # ${var:=default}
        # ${var:?error}
        # ${var:+alternate}
        # ${#var}
        # ${var#pattern}
        # ${var%pattern}
        # ${var/search/replace}
        
        # Simple implementation for basic case
        if ':' not in content and '#' not in content and '%' not in content and '/' not in content:
            # Simple ${var}
            return ParseResult(
                success=True,
                value=ParameterExpansion(variable=content),
                position=pos + 1
            )
        
        # Complex parsing logic here...
        
    return Parser(parse_param_expansion)
```

#### 3.4 Expansion Types to Support

1. **Basic**: `${var}`
2. **Default Values**: `${var:-default}`, `${var:=default}`
3. **Error Handling**: `${var:?error message}`
4. **Alternate Value**: `${var:+alternate}`
5. **String Length**: `${#var}`
6. **Pattern Removal**: `${var#pattern}`, `${var##pattern}`, `${var%pattern}`, `${var%%pattern}`
7. **String Replacement**: `${var/search/replace}`, `${var//search/replace}`
8. **Case Modification**: `${var^}`, `${var^^}`, `${var,}`, `${var,,}` (bash 4+)
9. **Array Operations**: `${array[@]}`, `${#array[@]}`

## Implementation Strategy

### Week 1-2: Command Substitution
- [ ] Day 1-2: Lexer modifications for `$(...)` and backticks
- [ ] Day 3-4: AST node and basic parser
- [ ] Day 5-6: Nested substitution support
- [ ] Day 7-8: Integration with command parsing
- [ ] Day 9-10: Comprehensive testing

### Week 3-4: Here Documents
- [ ] Day 1-2: Lexer strategy for here docs
- [ ] Day 3-4: Parser implementation
- [ ] Day 5-6: Multiple here doc support
- [ ] Day 7-8: Integration with redirections
- [ ] Day 9-10: Testing with real scripts

### Week 5-6: Basic Parameter Expansion
- [ ] Day 1-2: Lexer recognition of `${...}`
- [ ] Day 3-4: Parser for simple expansions
- [ ] Day 5-6: Default/alternate value operators
- [ ] Day 7-8: Length and pattern operators
- [ ] Day 9-10: Testing and edge cases

### Week 7-8: Advanced Parameter Expansion
- [ ] Day 1-2: String replacement operators
- [ ] Day 3-4: Case modification (if needed)
- [ ] Day 5-6: Array expansion support
- [ ] Day 7-8: Integration testing
- [ ] Day 9-10: Performance optimization

## Technical Challenges

### 1. Lexer-Parser Coordination
- Command substitution needs recursive parsing
- Here documents need deferred content collection
- Parameter expansion needs complex pattern matching

### 2. Nested Constructs
- `$(echo $(date))` - nested command substitution
- `${var:-$(command)}` - command substitution in parameter expansion
- Here docs with embedded expansions

### 3. Quote Handling
- Expansions behave differently in quotes
- Here doc delimiters can be quoted
- Nested quote handling in substitutions

### 4. Performance
- Recursive parsing for substitutions
- Large here documents
- Complex parameter expansions

## Testing Strategy

### Unit Tests
```python
# Command substitution
assert parse("echo $(date)").args[1] == CommandSubstitution(...)
assert parse("echo `date`").args[1] == CommandSubstitution(...)

# Here documents
assert parse("cat <<EOF\nline1\nline2\nEOF").redirects[0].heredoc_content == "line1\nline2\n"

# Parameter expansion
assert parse("echo ${USER}").args[1] == ParameterExpansion(variable="USER")
assert parse("echo ${var:-default}").args[1] == ParameterExpansion(
    variable="var", operator=":-", value="default"
)
```

### Integration Tests
- Functions using command substitution
- Pipelines with here documents
- Complex scripts with all three features

### Conformance Tests
- Compare with bash behavior
- POSIX compliance testing
- Edge case compatibility

## Success Criteria

1. **Command Substitution**
   - Both `$()` and backtick syntax work
   - Nested substitutions supported
   - Proper integration with strings

2. **Here Documents**
   - Basic `<<EOF` syntax works
   - Tab stripping with `<<-`
   - Multiple here docs per command
   - Quoted vs unquoted delimiters

3. **Parameter Expansion**
   - All POSIX-required forms work
   - Common bash extensions supported
   - Proper error handling

4. **Integration**
   - All features work together
   - No performance regression
   - Clean, maintainable code

## Future Enhancements

After basic implementation:
1. Process substitution `<(command)`
2. Arithmetic expansion improvements
3. Extended glob patterns
4. Brace expansion `{a,b,c}`
5. Tilde expansion `~user`

## Example Implementation

```bash
#!/bin/bash

# Command substitution
current_date=$(date +%Y-%m-%d)
file_count=`ls -1 | wc -l`

# Here document with parameter expansion
cat <<EOF
Date: $current_date
Files: $file_count
User: ${USER:-unknown}
EOF

# Complex parameter expansion
path="/usr/local/bin/program"
echo "Directory: ${path%/*}"      # /usr/local/bin
echo "Program: ${path##*/}"       # program
echo "Backup: ${path/program/program.bak}"  # /usr/local/bin/program.bak

# Nested constructs
result=${output:-$(calculate_default)}
```

This implementation will significantly enhance the parser combinator's capability to handle real-world shell scripts.