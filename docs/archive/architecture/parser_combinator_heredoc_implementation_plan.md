# Parser Combinator Here Document Implementation Plan

## Executive Summary

This document outlines a comprehensive plan for implementing Here Document support in the PSH parser combinator. Here Documents are a critical missing feature that blocks full shell script compatibility. The implementation requires careful coordination between the lexer and parser due to the non-linear nature of heredoc content.

## Background

### What are Here Documents?

Here Documents (heredocs) allow multi-line string input in shell scripts:

```bash
cat <<EOF
This is line 1
This is line 2
EOF

# With tab stripping
cat <<-EOF
	This line has tabs stripped
	So does this one
EOF

# With quoted delimiter (no expansion)
cat <<'EOF'
$HOME is not expanded
Neither is $(date)
EOF
```

### Current State

**Lexer**: ✅ Fully supports heredocs with:
- Token recognition (`HEREDOC`, `HEREDOC_STRIP`)
- Multi-line content collection
- Delimiter tracking
- Integration with main tokenizer

**Recursive Descent Parser**: ✅ Fully supports heredocs with:
- Two-pass parsing approach
- AST population after parsing
- Variable expansion control

**Parser Combinator**: ❌ No heredoc support:
- Missing heredoc operator recognition
- No multi-line content handling
- No integration with lexer's heredoc collection

## Implementation Challenges

### 1. Non-Linear Token Stream
Heredocs break the linear token model:
```bash
cat <<EOF && echo done
heredoc content appears here
not inline with the command
EOF
```

The content appears after the command line but must be associated with the redirect token.

### 2. Functional Purity
Parser combinators are pure functions that transform token streams. Heredocs require:
- Access to external state (heredoc content map)
- Coordination with the lexer
- Possible backtracking or lookahead

### 3. Multiple Heredocs
Commands can have multiple heredocs:
```bash
cat <<EOF1 <<EOF2
content for first heredoc
EOF1
content for second heredoc
EOF2
```

### 4. Nested Structures
Heredocs can appear in nested structures:
```bash
if true; then
    cat <<EOF
    heredoc in if statement
EOF
fi
```

## Proposed Solution

### Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                  │     │                 │
│  Tokenization   │────▶│ Heredoc Content  │────▶│ Parser Combinator│
│  with Heredocs  │     │   Collection     │     │  with Context   │
│                 │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                         │
        │                        │                         │
        ▼                        ▼                         ▼
   Token Stream           Heredoc Map               AST with Heredocs
```

### Phase 1: Parser Context Enhancement

Add heredoc support to the parser context:

```python
@dataclass
class ParserContext:
    """Extended parser context with heredoc support."""
    tokens: List[Token]
    position: int = 0
    heredoc_contents: Dict[str, str] = field(default_factory=dict)
    
class ParserCombinatorShellParser(AbstractShellParser):
    def __init__(self, heredoc_contents: Optional[Dict[str, str]] = None):
        super().__init__()
        self.heredoc_contents = heredoc_contents or {}
```

### Phase 2: Heredoc Token Recognition

Update the grammar to recognize heredoc operators:

```python
def _build_grammar(self):
    # ... existing code ...
    
    # Heredoc operators
    self.heredoc = token('HEREDOC')           # <<
    self.heredoc_strip = token('HEREDOC_STRIP')  # <<-
    self.here_string = token('HERE_STRING')   # <<<
    
    # Update redirect operator to include heredocs
    self.redirect_operator = (
        self.redirect_out
        .or_else(self.redirect_in)
        .or_else(self.redirect_append)
        .or_else(self.redirect_err)
        .or_else(self.redirect_err_append)
        .or_else(self.redirect_dup)
        .or_else(self.heredoc)
        .or_else(self.heredoc_strip)
        .or_else(self.here_string)
    )
```

### Phase 3: Heredoc Parsing Logic

Implement heredoc-aware redirection parsing:

```python
def parse_redirection(tokens: List[Token], pos: int) -> ParseResult[Redirect]:
    # First try normal redirection
    op_result = self.redirect_operator.parse(tokens, pos)
    if not op_result.success:
        return ParseResult(success=False, error=op_result.error, position=pos)
    
    op_token = op_result.value
    pos = op_result.position
    
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
        
        delimiter_token = delimiter_result.value
        delimiter = delimiter_token.value
        
        # Check if delimiter is quoted
        heredoc_quoted = (delimiter_token.type.name == 'STRING' or 
                         delimiter.startswith("'") or 
                         delimiter.startswith('"'))
        
        # Remove quotes from delimiter if present
        if heredoc_quoted:
            delimiter = delimiter.strip("'\"")
        
        # Get heredoc key from token if available
        heredoc_key = getattr(op_token, 'heredoc_key', None)
        
        # Create redirect with heredoc metadata
        redirect = Redirect(
            type=op_token.value,
            target=delimiter,
            heredoc_quoted=heredoc_quoted
        )
        
        # Store heredoc key for later content population
        if heredoc_key:
            redirect.heredoc_key = heredoc_key
        
        return ParseResult(
            success=True,
            value=redirect,
            position=delimiter_result.position
        )
    
    # ... handle other redirections ...
```

### Phase 4: Two-Pass Parsing Approach

Implement a two-pass parsing method similar to the recursive descent parser:

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

def _populate_heredoc_content(self, node: ASTNode, 
                             heredoc_contents: Dict[str, str]) -> None:
    """Recursively populate heredoc content in AST nodes."""
    if isinstance(node, SimpleCommand):
        for redirect in node.redirects:
            if hasattr(redirect, 'heredoc_key') and redirect.heredoc_key:
                if redirect.heredoc_key in heredoc_contents:
                    redirect.heredoc_content = heredoc_contents[redirect.heredoc_key]
    
    # Recursively handle nested structures
    elif isinstance(node, (IfConditional, WhileLoop, ForLoop)):
        # ... traverse nested AST nodes ...
```

### Phase 5: Here String Support

Here strings are simpler as they're inline:

```python
# Handle here strings (<<<)
elif op_token.type.name == 'HERE_STRING':
    # Parse the string content
    content_result = self.word_like.parse(tokens, pos)
    if not content_result.success:
        return ParseResult(
            success=False,
            error="Expected content after <<<",
            position=pos
        )
    
    # Here strings are always treated as single-quoted
    return ParseResult(
        success=True,
        value=Redirect(
            type=op_token.value,
            target=content_result.value.value,
            heredoc_content=content_result.value.value,
            heredoc_quoted=True  # No expansion in here strings
        ),
        position=content_result.position
    )
```

### Phase 6: Integration Points

#### 1. Parser Factory Update

```python
def create_parser_combinator(tokens: List[Token], 
                           heredoc_contents: Optional[Dict[str, str]] = None):
    """Create parser combinator with optional heredoc support."""
    parser = ParserCombinatorShellParser(heredoc_contents)
    return parser
```

#### 2. Shell Integration

Update the shell to use heredoc-aware parsing:

```python
# In shell.py
if any('<<<<' in cmd or '<<<' in cmd or '<<' in cmd):
    # Use heredoc-aware tokenization
    tokens, heredoc_contents = tokenize_with_heredocs(cmd)
    
    # Use appropriate parser
    if self.parser_type == 'combinator':
        parser = ParserCombinatorShellParser(heredoc_contents)
        ast = parser.parse_with_heredocs(tokens, heredoc_contents)
    else:
        # ... existing recursive descent approach ...
```

## Testing Strategy

### 1. Unit Tests

```python
# tests/unit/parser/test_parser_combinator_heredocs.py

def test_simple_heredoc():
    """Test basic heredoc parsing."""
    tokens = tokenize("cat <<EOF")
    heredoc_contents = {"heredoc_0_EOF": "line1\nline2\n"}
    
    parser = ParserCombinatorShellParser(heredoc_contents)
    ast = parser.parse_with_heredocs(tokens, heredoc_contents)
    
    assert isinstance(ast.statements[0], SimpleCommand)
    redirect = ast.statements[0].redirects[0]
    assert redirect.type == "<<"
    assert redirect.target == "EOF"
    assert redirect.heredoc_content == "line1\nline2\n"

def test_heredoc_strip_tabs():
    """Test <<- tab stripping."""
    # ... test tab stripping behavior ...

def test_quoted_delimiter():
    """Test quoted delimiter disables expansion."""
    # ... test quoted vs unquoted delimiters ...

def test_multiple_heredocs():
    """Test multiple heredocs in one command."""
    # ... test multiple heredoc handling ...
```

### 2. Integration Tests

```python
# tests/integration/test_parser_combinator_heredoc_integration.py

def test_heredoc_in_if_statement():
    """Test heredoc in control structure."""
    # ... test nested heredocs ...

def test_heredoc_with_pipeline():
    """Test heredoc with pipelines."""
    # ... test complex command structures ...
```

### 3. Conformance Tests

Ensure parser combinator matches recursive descent behavior:

```python
def test_parser_parity_heredoc():
    """Both parsers should produce identical ASTs."""
    # ... compare AST outputs ...
```

## Implementation Timeline

### Week 1: Foundation
- [ ] Add heredoc support to parser context
- [ ] Update token recognition
- [ ] Implement basic heredoc parsing

### Week 2: Integration
- [ ] Implement two-pass parsing
- [ ] Add AST population logic
- [ ] Integrate with shell

### Week 3: Testing
- [ ] Write comprehensive unit tests
- [ ] Add integration tests
- [ ] Ensure parser parity

### Week 4: Polish
- [ ] Handle edge cases
- [ ] Performance optimization
- [ ] Documentation updates

## Risk Mitigation

### 1. Parser Combinator Purity
**Risk**: Heredocs require external state, breaking functional purity.
**Mitigation**: Use a context object pattern to maintain functional style while allowing state access.

### 2. Backward Compatibility
**Risk**: Changes might break existing functionality.
**Mitigation**: Extensive test coverage and gradual rollout.

### 3. Performance Impact
**Risk**: Two-pass parsing might slow down the parser.
**Mitigation**: Only use two-pass when heredocs are detected.

## Success Criteria

1. **Functional Completeness**:
   - [ ] Basic heredocs (<<EOF) working
   - [ ] Tab-stripping heredocs (<<-EOF) working
   - [ ] Quoted delimiters disable expansion
   - [ ] Here strings (<<<) working
   - [ ] Multiple heredocs supported
   - [ ] Nested heredocs in control structures

2. **Test Coverage**:
   - [ ] All heredoc tests pass
   - [ ] Integration tests verify end-to-end flow
   - [ ] Parser parity with recursive descent

3. **Performance**:
   - [ ] No significant performance regression
   - [ ] Efficient handling of large heredocs

## Conclusion

Implementing Here Documents in the parser combinator requires careful design to maintain functional programming principles while handling the inherently stateful nature of multi-line content collection. The proposed two-pass approach with context objects provides a clean solution that integrates well with the existing architecture.

This implementation would complete the last major missing feature in the parser combinator, making it truly production-ready for real-world shell scripts.