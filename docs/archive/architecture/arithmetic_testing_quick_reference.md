# Arithmetic Expansion Testing - Quick Reference

## Testing Overview

### ✅ Already Tested (Existing Coverage)
- **Parser**: 43 tests for syntax parsing
- **Basic Operations**: +, -, *, /, %, **
- **Comparisons**: <, >, <=, >=, ==, !=
- **Logical**: &&, ||, !
- **Bitwise**: &, |, ^, ~, <<, >>
- **Assignment**: =, +=, -=, *=, /=, %=
- **Increment/Decrement**: ++, --
- **Ternary**: ? :
- **Comma**: ,
- **Variables**: Basic variable expansion
- **Precedence**: Operator precedence rules
- **Parentheses**: Grouping expressions

### ⚠️ Needs Testing (Gaps to Fill)

#### 1. Number Formats
```bash
# Base notation
$((2#101010))      # Binary
$((8#755))         # Octal  
$((16#DEADBEEF))   # Hexadecimal
$((36#HELLO))      # Base 36

# Edge cases
$((037))           # Leading zero = octal
$((0x1F))          # Hex prefix
```

#### 2. Special Variables
```bash
# Positional parameters
$(($1 + $2))       # With set -- 10 20

# Special parameters
$(($# * 2))        # Argument count
$(($? + 1))        # Exit status
$(($$))            # Process ID

# Arrays
$((${arr[0]} + ${arr[1]}))
$((${#arr[@]}))    # Array length
```

#### 3. Complex Integration
```bash
# In parameter expansion
${str:$((pos)):$((len))}

# Nested in command substitution  
$(($(get_value) * 2))

# In control structures
if (( x > 5 )); then
for ((i=0; i<10; i++)); do
```

#### 4. Error Handling
```bash
# Division by zero
$((10 / 0))

# Overflow
$((2147483647 + 1))

# Syntax errors
$((5 +))
$(())
```

#### 5. Bash Compatibility
```bash
# Negative modulo
$((-7 % 3))        # Bash: -1

# Right shift negative
$((-1 >> 1))       # Bash: -1

# Large numbers
$((9999999999999)) # 64-bit handling
```

## Test Implementation Schedule

| Phase | Focus | Duration | Priority |
|-------|-------|----------|----------|
| 1 | Number Formats | 2 days | HIGH |
| 2 | Special Variables | 1 day | HIGH |
| 3 | Complex Integration | 2 days | MEDIUM |
| 4 | Error Handling | 1 day | MEDIUM |
| 5 | Bash Compatibility | 1 day | LOW |

## Key Test Files

### Existing Tests
- `tests/unit/parser/test_parser_combinator_arithmetic_expansion.py` - Parser tests
- `tests/unit/expansion/test_arithmetic_comprehensive.py` - Evaluation tests
- `tests/unit/expansion/test_arithmetic_expansion.py` - Basic expansion

### New Test Files (To Create)
- `test_arithmetic_number_formats.py` - All number format variations
- `test_arithmetic_special_variables.py` - Special params and arrays
- `test_arithmetic_integration.py` - Complex shell integration
- `test_arithmetic_edge_cases.py` - Error and edge cases
- `test_arithmetic_bash_compatibility.py` - Bash comparison

## Testing Checklist

### Number Formats
- [ ] Binary notation (2#)
- [ ] Octal notation (8#)
- [ ] Hex notation (16#)
- [ ] Arbitrary base (2-36)
- [ ] Leading zero octal
- [ ] 0x hex prefix
- [ ] Case sensitivity
- [ ] Invalid digits
- [ ] Base out of range

### Special Variables
- [ ] $1-$9 positional
- [ ] ${10} and beyond
- [ ] $# argument count
- [ ] $? exit status
- [ ] $$ process ID
- [ ] $! last background PID
- [ ] Array elements
- [ ] Array length
- [ ] Undefined variables

### Integration Points
- [ ] ${param:offset:length}
- [ ] Array subscripts
- [ ] Command substitution
- [ ] If conditions
- [ ] While conditions
- [ ] For loop expressions
- [ ] Case patterns
- [ ] Function returns
- [ ] Redirections

### Error Cases
- [ ] Division by zero
- [ ] Modulo by zero
- [ ] Integer overflow
- [ ] Integer underflow
- [ ] Syntax errors
- [ ] Empty expressions
- [ ] Invalid operators
- [ ] Unclosed parentheses
- [ ] Invalid variables

### Bash Compatibility
- [ ] Negative modulo
- [ ] Signed right shift
- [ ] Overflow behavior
- [ ] String to number
- [ ] Base notation limits
- [ ] Operator precedence
- [ ] Short-circuit eval
- [ ] Side effects order
- [ ] Error messages

## Quick Test Examples

```bash
# Run a quick test
python -m pytest tests/unit/expansion/test_arithmetic* -v

# Test specific feature
python -m pytest -k "test_base_notation" -v

# Compare with bash
bash -c 'echo $((2#1010))'  # Should output: 10
python -m psh -c 'echo $((2#1010))'  # Should match

# Check evaluation
python -m psh -c 'x=5; echo $((x * 2 + 3))'  # Should output: 13
```

## Success Criteria

1. **Parsing**: All arithmetic syntax parses correctly
2. **Evaluation**: All operations produce correct results
3. **Compatibility**: Matches bash for standard cases
4. **Errors**: Graceful handling of all error conditions
5. **Performance**: Fast evaluation of complex expressions
6. **Integration**: Works in all shell contexts

## Notes

- Focus on POSIX compliance first, bash extensions second
- Document any intentional differences from bash
- Ensure no regressions in existing tests
- Add examples to user documentation
- Update feature roadmap after completion