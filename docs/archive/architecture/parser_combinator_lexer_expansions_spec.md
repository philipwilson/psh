# Lexer Modifications for Expansions - Technical Specification

## Overview

This document specifies the lexer modifications required to support command substitution, here documents, and parameter expansion in the parser combinator implementation.

## Token Type Additions

### New Token Types Required

```python
# In token_types.py
class TokenType(Enum):
    # ... existing types ...
    
    # Command Substitution
    COMMAND_SUBSTITUTION = auto()    # $(command)
    BACKTICK_SUBSTITUTION = auto()   # `command`
    
    # Here Documents
    HEREDOC_START = auto()           # <<
    HEREDOC_STRIP_START = auto()     # <<-
    HEREDOC_DELIMITER = auto()       # The delimiter word
    HEREDOC_CONTENT = auto()         # The content block
    
    # Parameter Expansion
    PARAM_EXPANSION = auto()         # ${...} constructs
    
    # Supporting tokens
    EXPANSION_START = auto()         # ${ or $(
    EXPANSION_END = auto()           # } or )
```

## Lexer State Machine

### State Definitions

```python
class LexerState(Enum):
    NORMAL = "normal"
    IN_COMMAND_SUB = "in_command_sub"
    IN_PARAM_EXPANSION = "in_param_expansion"
    AFTER_HEREDOC_START = "after_heredoc_start"
    COLLECTING_HEREDOC = "collecting_heredoc"
    IN_BACKTICKS = "in_backticks"
```

### State Transitions

```
NORMAL:
  - See "$(" → IN_COMMAND_SUB, emit EXPANSION_START
  - See "${" → IN_PARAM_EXPANSION, emit EXPANSION_START
  - See "`" → IN_BACKTICKS
  - See "<<" → AFTER_HEREDOC_START, emit HEREDOC_START
  - See "<<-" → AFTER_HEREDOC_START, emit HEREDOC_STRIP_START

IN_COMMAND_SUB:
  - Track nesting level for nested $()
  - See ")" with level 0 → NORMAL, emit COMMAND_SUBSTITUTION
  - See "$(" → increment nesting level

IN_PARAM_EXPANSION:
  - See "}" → NORMAL, emit PARAM_EXPANSION
  - Track ${} nesting for complex expansions

AFTER_HEREDOC_START:
  - Next word → delimiter, then COLLECTING_HEREDOC
  - Track if delimiter is quoted

COLLECTING_HEREDOC:
  - Collect lines until delimiter found
  - Emit HEREDOC_CONTENT when complete
```

## Implementation Details

### 1. Command Substitution Lexing

```python
def lex_command_substitution(self, start_pos: int) -> Token:
    """Lex $(...) command substitution."""
    # Skip $(
    pos = start_pos + 2
    content_start = pos
    nesting_level = 1
    
    while pos < len(self.input) and nesting_level > 0:
        if self.input[pos:pos+2] == '$((':
            # Arithmetic expansion - skip entirely
            pos = self._skip_arithmetic_expansion(pos)
        elif self.input[pos:pos+2] == '$(':
            nesting_level += 1
            pos += 2
        elif self.input[pos] == ')':
            nesting_level -= 1
            pos += 1
        elif self.input[pos] == '"':
            pos = self._skip_quoted_string(pos, '"')
        elif self.input[pos] == "'":
            pos = self._skip_quoted_string(pos, "'")
        elif self.input[pos] == '\\' and pos + 1 < len(self.input):
            pos += 2  # Skip escaped character
        else:
            pos += 1
    
    if nesting_level > 0:
        raise LexerError("Unclosed command substitution")
    
    content = self.input[content_start:pos-1]
    return Token(
        type=TokenType.COMMAND_SUBSTITUTION,
        value=f"$({content})",
        position=start_pos,
        end_position=pos
    )
```

### 2. Here Document Lexing

```python
class HeredocContext:
    """Track here document state."""
    delimiter: str
    strip_tabs: bool
    quoted: bool
    start_line: int
    content_lines: List[str] = field(default_factory=list)

def lex_heredoc_operator(self, pos: int) -> Tuple[Token, LexerState]:
    """Lex << or <<- operator."""
    if self.input[pos:pos+3] == '<<-':
        token = Token(
            type=TokenType.HEREDOC_STRIP_START,
            value='<<-',
            position=pos,
            end_position=pos + 3
        )
        return token, LexerState.AFTER_HEREDOC_START
    elif self.input[pos:pos+2] == '<<':
        token = Token(
            type=TokenType.HEREDOC_START,
            value='<<',
            position=pos,
            end_position=pos + 2
        )
        return token, LexerState.AFTER_HEREDOC_START
```

### 3. Parameter Expansion Lexing

```python
def lex_parameter_expansion(self, start_pos: int) -> Token:
    """Lex ${...} parameter expansion."""
    # Skip ${
    pos = start_pos + 2
    content_start = pos
    brace_level = 1
    
    while pos < len(self.input) and brace_level > 0:
        char = self.input[pos]
        
        if char == '{':
            brace_level += 1
        elif char == '}':
            brace_level -= 1
        elif char == '\\' and pos + 1 < len(self.input):
            pos += 1  # Skip next character
        
        pos += 1
    
    if brace_level > 0:
        raise LexerError("Unclosed parameter expansion")
    
    content = self.input[content_start:pos-1]
    
    # Create rich token with parsed content
    return Token(
        type=TokenType.PARAM_EXPANSION,
        value=f"${{{content}}}",
        position=start_pos,
        end_position=pos,
        metadata=TokenMetadata(
            contexts={'expansion'},
            expansion_content=content
        )
    )
```

## Complex Scenarios

### 1. Nested Expansions

```bash
# Command substitution in parameter expansion
${var:-$(default_cmd)}

# Tokens:
1. PARAM_EXPANSION: "${var:-$(default_cmd)}"
   - metadata.expansion_content: "var:-$(default_cmd)"
   - metadata.nested_tokens: [COMMAND_SUBSTITUTION: "$(default_cmd)"]
```

### 2. Multiple Here Documents

```bash
cat <<EOF1 <<EOF2
content1
EOF1
content2
EOF2

# Lexing approach:
1. Queue multiple heredoc contexts
2. Process in order after command line
3. Match delimiters sequentially
```

### 3. Quoted vs Unquoted

```bash
# Quoted delimiter - no expansion
cat <<'EOF'
$USER stays literal
EOF

# Unquoted delimiter - expansions active
cat <<EOF
$USER expands
EOF

# Lexer tracks quote state of delimiter
```

## Integration with Existing Lexer

### ModularLexer Extension Points

```python
class ExpansionMixin:
    """Mixin for expansion-related lexing."""
    
    def check_expansion_start(self, pos: int) -> Optional[Token]:
        """Check for start of any expansion."""
        if self.input[pos] == '$':
            next_char = self.input[pos+1] if pos+1 < len(self.input) else None
            if next_char == '(':
                return self.lex_command_substitution(pos)
            elif next_char == '{':
                return self.lex_parameter_expansion(pos)
    
    def handle_heredoc_collection(self):
        """Process any pending here documents."""
        for context in self.pending_heredocs:
            self.collect_heredoc_content(context)
```

### Token Enhancement

```python
@dataclass
class ExpansionToken(Token):
    """Enhanced token for expansions."""
    # For nested content
    nested_tokens: Optional[List[Token]] = None
    
    # For parameter expansion
    param_name: Optional[str] = None
    param_operator: Optional[str] = None
    param_value: Optional[str] = None
    
    # For here documents
    heredoc_delimiter: Optional[str] = None
    heredoc_quoted: bool = False
    heredoc_strip_tabs: bool = False
```

## Error Handling

### Lexer Errors

```python
class ExpansionLexerError(LexerError):
    """Errors specific to expansion lexing."""
    pass

class UnclosedExpansionError(ExpansionLexerError):
    """Unclosed expansion construct."""
    def __init__(self, expansion_type: str, start_pos: int):
        self.expansion_type = expansion_type
        self.start_pos = start_pos
        super().__init__(f"Unclosed {expansion_type} starting at position {start_pos}")

class InvalidExpansionError(ExpansionLexerError):
    """Invalid expansion syntax."""
    pass

class HeredocError(ExpansionLexerError):
    """Here document processing error."""
    pass
```

### Recovery Strategies

1. **Unclosed Expansions**: Treat as literal text after error
2. **Missing Heredoc**: Provide empty content with error
3. **Invalid Syntax**: Skip to next valid token

## Performance Optimizations

### 1. Lookahead Caching

```python
class LookaheadCache:
    """Cache lookahead results."""
    def __init__(self, size: int = 4):
        self.cache = {}
        self.size = size
    
    def get(self, pos: int, length: int) -> Optional[str]:
        key = (pos, length)
        return self.cache.get(key)
    
    def set(self, pos: int, length: int, value: str):
        if len(self.cache) >= self.size:
            # LRU eviction
            oldest = min(self.cache.keys())
            del self.cache[oldest]
        self.cache[(pos, length)] = value
```

### 2. State Stack for Nesting

```python
@dataclass
class LexerStateStack:
    """Manage nested lexer states."""
    states: List[LexerState] = field(default_factory=list)
    contexts: List[Any] = field(default_factory=list)
    
    def push(self, state: LexerState, context=None):
        self.states.append(state)
        self.contexts.append(context)
    
    def pop(self) -> Tuple[LexerState, Any]:
        return self.states.pop(), self.contexts.pop()
    
    @property
    def current(self) -> LexerState:
        return self.states[-1] if self.states else LexerState.NORMAL
```

## Testing Requirements

### Lexer Unit Tests

```python
def test_command_substitution():
    tokens = tokenize("echo $(date)")
    assert tokens[1].type == TokenType.COMMAND_SUBSTITUTION
    assert tokens[1].value == "$(date)"

def test_nested_command_substitution():
    tokens = tokenize("echo $(echo $(date))")
    assert tokens[1].type == TokenType.COMMAND_SUBSTITUTION
    assert "$(date)" in tokens[1].value

def test_parameter_expansion():
    tokens = tokenize("echo ${USER:-nobody}")
    assert tokens[1].type == TokenType.PARAM_EXPANSION
    assert tokens[1].metadata.expansion_content == "USER:-nobody"

def test_heredoc():
    tokens = tokenize("cat <<EOF\nline1\nline2\nEOF\n")
    # Should have WORD, HEREDOC_START, HEREDOC_DELIMITER, NEWLINE, HEREDOC_CONTENT
```

### Edge Cases

1. Expansions at EOF
2. Expansions with Unicode
3. Very large here documents
4. Deeply nested expansions
5. Mixed quote contexts

## Migration Path

### Phase 1: Basic Support
- Simple command substitution
- Basic parameter expansion
- Single here documents

### Phase 2: Nesting
- Nested command substitution
- Complex parameter operators
- Multiple here documents

### Phase 3: Full Integration
- All expansion types
- Quote interaction
- Performance optimization

This specification provides the foundation for implementing comprehensive expansion support in the PSH lexer.