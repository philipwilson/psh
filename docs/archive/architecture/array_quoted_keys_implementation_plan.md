# Implementation Plan: Quoted Keys in Array Assignments

## Problem Statement

PSH currently fails to handle quoted keys in array element assignments, causing associative arrays to fail when keys contain spaces or special characters. This is a critical gap in bash compatibility.

### Current Behavior
```bash
# Works
arr[key]="value"           # Tokenized as: WORD("arr[key]=") STRING("value")

# Fails  
arr["key"]="value"         # Tokenized as: WORD("arr[") STRING("key") WORD("]=") STRING("value")
arr['key']="value"         # Same issue with single quotes
```

### Required Behavior
Both quoted and unquoted keys should be recognized as array element assignments, matching bash behavior.

## Technical Analysis

### 1. Lexer Architecture Review

The PSH lexer currently recognizes patterns during tokenization:
- `VAR=value` → `ASSIGNMENT_WORD` token
- `arr[index]=value` → `WORD` token (parsed as array assignment later)
- `arr["key"]=value` → Multiple tokens (broken pattern)

### 2. Pattern Recognition Challenge

The lexer needs to recognize these patterns as single assignment units:
- `arr[unquoted]=value`
- `arr["double quoted"]=value`
- `arr['single quoted']=value`
- `arr[$var]=value`
- `arr[${var}]=value`
- `arr[$(command)]=value`
- `arr[$((arithmetic))]=value`

### 3. Tokenization States

Current lexer states when processing `arr["key"]=value`:
1. Reading `arr[` → Recognizes as WORD
2. Encounters `"` → Switches to quoted string mode
3. Reads `key` → Creates STRING token
4. Encounters `"` → Exits quoted mode
5. Reads `]=` → Creates new WORD token
6. Result: Broken tokenization

## Implementation Strategy

### Phase 1: Enhanced Pattern Detection

#### 1.1 Lookahead Implementation
Add lookahead logic to detect array assignment patterns:

```python
def is_array_assignment_pattern(self, text, pos):
    """
    Check if we're at the start of an array assignment pattern.
    Patterns: NAME[...]=... where [...] can contain quoted strings
    """
    # Check for NAME[
    if not self._is_valid_identifier_start(text, pos):
        return False
    
    # Find the opening bracket
    bracket_pos = pos
    while bracket_pos < len(text) and (text[bracket_pos].isalnum() or text[bracket_pos] == '_'):
        bracket_pos += 1
    
    if bracket_pos >= len(text) or text[bracket_pos] != '[':
        return False
    
    # Find matching closing bracket and equals
    closing_bracket = self._find_closing_bracket(text, bracket_pos)
    if closing_bracket == -1:
        return False
    
    # Check for = or += after ]
    if closing_bracket + 1 < len(text):
        if text[closing_bracket + 1] == '=':
            return True
        if closing_bracket + 2 < len(text) and text[closing_bracket + 1:closing_bracket + 3] == '+=':
            return True
    
    return False
```

#### 1.2 Bracket Matching with Quote Awareness
```python
def _find_closing_bracket(self, text, start_pos):
    """
    Find the closing bracket, handling quoted strings and nested elements.
    """
    pos = start_pos + 1  # Skip opening [
    depth = 1
    in_single_quote = False
    in_double_quote = False
    
    while pos < len(text) and depth > 0:
        char = text[pos]
        
        # Handle quotes
        if char == "'" and not in_double_quote and (pos == 0 or text[pos-1] != '\\'):
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and (pos == 0 or text[pos-1] != '\\'):
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote:
            # Only count brackets outside quotes
            if char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
                if depth == 0:
                    return pos
        
        pos += 1
    
    return -1  # No matching bracket found
```

### Phase 2: Token Generation

#### 2.1 New Token Type
Consider adding a specific token type for array assignments:
```python
class TokenType(Enum):
    # ... existing tokens ...
    ARRAY_ASSIGNMENT_WORD = auto()  # arr[key]=value pattern
```

#### 2.2 Composite Token Creation
```python
def create_array_assignment_token(self, text, start, end):
    """
    Create a token for array element assignment.
    Preserves the full pattern including quotes for the parser.
    """
    full_text = text[start:end]
    
    # Parse components for metadata
    name_end = full_text.index('[')
    name = full_text[:name_end]
    
    # Find the key (everything between [ and ])
    key_start = name_end + 1
    key_end = self._find_closing_bracket(full_text, name_end)
    key_with_quotes = full_text[key_start:key_end]
    
    # Determine if it's += or =
    is_append = full_text[key_end + 1:key_end + 3] == '+='
    
    return Token(
        type=TokenType.ARRAY_ASSIGNMENT_WORD,
        value=full_text,
        position=start,
        end_position=end,
        metadata={
            'array_name': name,
            'key_raw': key_with_quotes,  # Preserves quotes
            'is_append': is_append
        }
    )
```

### Phase 3: Parser Updates

#### 3.1 Parser Recognition
Update the parser to handle the new token type:

```python
def parse_array_element_assignment(self, token):
    """
    Parse ARRAY_ASSIGNMENT_WORD token into ArrayElementAssignment AST node.
    """
    metadata = token.metadata
    
    # Extract and process the key
    key_raw = metadata['key_raw']
    key_processed = self.process_array_key(key_raw)
    
    # Extract the value (everything after = or +=)
    equals_pos = token.value.index(']=') + 2
    if metadata['is_append']:
        equals_pos += 1  # Account for +=
    
    value = token.value[equals_pos:] if equals_pos < len(token.value) else ''
    
    return ArrayElementAssignment(
        name=metadata['array_name'],
        index=key_processed,
        value=value,
        is_append=metadata['is_append']
    )
```

#### 3.2 Key Processing
```python
def process_array_key(self, key_raw):
    """
    Process the raw key, handling quotes and expansions.
    """
    # Remove quotes if present
    if (key_raw.startswith('"') and key_raw.endswith('"')) or \
       (key_raw.startswith("'") and key_raw.endswith("'")):
        return key_raw[1:-1]
    
    # Handle expansions (future enhancement)
    # This would need to mark the key for runtime expansion
    
    return key_raw
```

### Phase 4: Executor Updates

#### 4.1 Runtime Key Evaluation
The executor needs to handle quoted keys properly:

```python
def execute_array_element_assignment(self, node):
    """
    Execute array element assignment with proper key handling.
    """
    # Get the array
    array = self.state.get_variable(node.name)
    
    # Process the key
    if isinstance(array, AssociativeArray):
        # Associative array - key is a string
        key = self.expand_string(node.index)
    else:
        # Indexed array - key should be numeric
        key = self.evaluate_arithmetic_expression(node.index)
    
    # Expand the value
    value = self.expand_string(node.value)
    
    # Perform assignment
    if node.is_append:
        array.append(key, value)
    else:
        array.set(key, value)
    
    return 0
```

### Phase 5: Testing Strategy

#### 5.1 Unit Tests for Lexer
```python
def test_array_assignment_tokenization():
    """Test that array assignments are tokenized correctly."""
    test_cases = [
        ('arr[key]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr["key"]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr["key with spaces"]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr[\'single quoted\']=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr[$var]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr[${var}]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr[$(echo key)]=value', 'ARRAY_ASSIGNMENT_WORD'),
        ('arr[$((1+1))]=value', 'ARRAY_ASSIGNMENT_WORD'),
    ]
    
    for input_text, expected_type in test_cases:
        tokens = tokenize(input_text)
        assert len(tokens) == 2  # assignment token + EOF
        assert tokens[0].type.name == expected_type
```

#### 5.2 Integration Tests
```python
def test_associative_array_quoted_keys():
    """Test associative arrays with quoted keys."""
    shell = Shell()
    
    # Test basic quoted key
    shell.run_command('declare -A arr')
    shell.run_command('arr["key1"]="value1"')
    assert shell.state.get_variable('arr')['key1'] == 'value1'
    
    # Test key with spaces
    shell.run_command('arr["key with spaces"]="value2"')
    assert shell.state.get_variable('arr')['key with spaces'] == 'value2'
    
    # Test special characters
    shell.run_command('arr["key-with-dashes"]="value3"')
    shell.run_command('arr["key.with.dots"]="value4"')
    shell.run_command('arr["key@symbol"]="value5"')
```

#### 5.3 Conformance Tests
Run the existing conformance tests to ensure compatibility:
```bash
python3 run_conformance_tests.py --category arrays --bash-compare
```

## Alternative Approach: Multi-Token Reconstruction

If modifying the lexer proves too complex, an alternative approach is to handle this in the parser:

### Parser-Level Pattern Matching
```python
def try_parse_array_assignment(self, tokens, pos):
    """
    Try to parse array assignment from multiple tokens.
    Pattern: WORD[...] + STRING + WORD(]=) + value
    """
    if pos >= len(tokens):
        return None, pos
    
    # Check for WORD ending with [
    if tokens[pos].type != TokenType.WORD or not tokens[pos].value.endswith('['):
        return None, pos
    
    array_name = tokens[pos].value[:-1]  # Remove [
    pos += 1
    
    # Collect tokens until we find ]=
    key_tokens = []
    while pos < len(tokens):
        if tokens[pos].type == TokenType.WORD and tokens[pos].value.startswith(']'):
            break
        key_tokens.append(tokens[pos])
        pos += 1
    
    if pos >= len(tokens):
        return None, pos
    
    # Check for ]= or ]+=
    if not (tokens[pos].value.startswith(']=') or tokens[pos].value.startswith(']+='))
        return None, pos
    
    is_append = tokens[pos].value.startswith(']+')
    
    # Reconstruct the key
    key = self.reconstruct_key(key_tokens)
    
    # Get the value
    value_start = 2 if is_append else 1
    value = tokens[pos].value[value_start:]
    
    return ArrayElementAssignment(
        name=array_name,
        index=key,
        value=value,
        is_append=is_append
    ), pos + 1
```

## Risk Mitigation

### Potential Issues and Solutions

1. **Backward Compatibility**
   - Risk: Changes might break existing array handling
   - Mitigation: Extensive regression testing, feature flag for new behavior

2. **Performance Impact**
   - Risk: Lookahead might slow down lexing
   - Mitigation: Cache lookahead results, optimize pattern detection

3. **Complex Keys**
   - Risk: Keys with nested expansions might not parse correctly
   - Mitigation: Incremental implementation, start with simple quoted keys

4. **Parser Complexity**
   - Risk: Adding more logic to already complex parser
   - Mitigation: Well-documented code, comprehensive unit tests

## Implementation Timeline

### Week 1: Research and Design
- Study bash source code for array handling
- Finalize design decisions
- Create comprehensive test suite

### Week 2: Lexer Implementation
- Implement lookahead logic
- Add quote-aware bracket matching
- Create array assignment tokens

### Week 3: Parser Updates
- Update parser to handle new tokens
- Implement key processing
- Add AST node creation

### Week 4: Executor and Testing
- Update executor for quoted keys
- Run comprehensive tests
- Fix edge cases

### Week 5: Integration and Polish
- Run full conformance suite
- Update documentation
- Performance optimization

## Success Criteria

1. All array conformance tests pass
2. No regression in existing functionality
3. Performance impact < 5% on typical scripts
4. Clear documentation and examples
5. Handles all bash array key patterns:
   - Simple unquoted keys
   - Double-quoted keys with spaces
   - Single-quoted keys
   - Keys with variable expansion
   - Keys with command substitution
   - Keys with arithmetic expansion

## Conclusion

This implementation plan provides a comprehensive approach to adding quoted key support to PSH's array handling. The preferred approach is to enhance the lexer to recognize array assignment patterns as single tokens, maintaining clean separation between lexing and parsing. The alternative parser-level approach provides a fallback if lexer modifications prove too complex.

The implementation should be done incrementally, starting with simple quoted keys and gradually adding support for more complex patterns. Comprehensive testing at each stage will ensure backward compatibility and correctness.