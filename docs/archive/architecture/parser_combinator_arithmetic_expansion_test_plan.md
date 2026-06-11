# Parser Combinator Arithmetic Expansion Testing Plan

## Overview

This document outlines a comprehensive plan for testing arithmetic expansion functionality in the parser combinator implementation. While basic parsing is confirmed working, we need to ensure complete coverage of all arithmetic features and edge cases.

## Current State

### What's Already Implemented
- ✅ ArithmeticExpansion AST node
- ✅ ARITH_EXPANSION token type
- ✅ Parser support for `$((...))` syntax
- ✅ Integration with Word AST and ExpansionEvaluator
- ✅ Basic parsing tests (43 tests) covering syntax

### What Needs Testing
- ⚠️ Execution and evaluation of arithmetic expressions
- ⚠️ Integration with shell variables and state
- ⚠️ Error handling and edge cases
- ⚠️ Performance with complex expressions
- ⚠️ Conformance with POSIX/bash behavior

## Testing Categories

### 1. Basic Operations Testing
Verify correct evaluation of fundamental arithmetic operations.

#### Tests to Implement:
```bash
# Addition
echo $((5 + 3))        # Expected: 8
echo $((100 + 200))    # Expected: 300
echo $((-5 + 3))       # Expected: -2

# Subtraction
echo $((10 - 3))       # Expected: 7
echo $((3 - 10))       # Expected: -7
echo $((0 - 5))        # Expected: -5

# Multiplication
echo $((4 * 5))        # Expected: 20
echo $((-3 * 4))       # Expected: -12
echo $((0 * 100))      # Expected: 0

# Division
echo $((20 / 4))       # Expected: 5
echo $((22 / 7))       # Expected: 3 (integer division)
echo $((-20 / 4))      # Expected: -5

# Modulo
echo $((20 % 6))       # Expected: 2
echo $((7 % 3))        # Expected: 1
echo $((-7 % 3))       # Expected: -1 (bash behavior)

# Power (if supported)
echo $((2 ** 3))       # Expected: 8
echo $((5 ** 2))       # Expected: 25
```

### 2. Variable Integration Testing
Test arithmetic with shell variables and special parameters.

#### Tests to Implement:
```bash
# Simple variables
x=10; echo $((x + 5))           # Expected: 15
y=3; echo $((x * y))            # Expected: 30

# Undefined variables (should evaluate to 0)
unset z; echo $((z + 5))        # Expected: 5

# String variables (should evaluate to 0)
str="hello"; echo $((str + 5))  # Expected: 5

# Numeric strings
num="42"; echo $((num / 2))     # Expected: 21

# Special variables
echo $(($ + 0))                 # $$ = PID
set -- 10 20 30
echo $(($1 + $2))               # Expected: 30
echo $(($# * 2))                # Expected: 6

# Array elements
arr=(5 10 15)
echo $((${arr[0]} + ${arr[1]})) # Expected: 15
```

### 3. Operator Precedence Testing
Verify correct operator precedence and associativity.

#### Tests to Implement:
```bash
# Multiplication before addition
echo $((2 + 3 * 4))             # Expected: 14, not 20

# Left-to-right for same precedence
echo $((20 / 4 / 2))            # Expected: 2, not 10
echo $((20 - 10 - 3))           # Expected: 7, not 13

# Parentheses override precedence
echo $(((2 + 3) * 4))           # Expected: 20
echo $((2 * (3 + 4)))           # Expected: 14

# Complex precedence
echo $((2 + 3 * 4 - 5))         # Expected: 9
echo $((10 / 2 + 3 * 4))        # Expected: 17
```

### 4. Bitwise Operations Testing
Test all bitwise operators with various values.

#### Tests to Implement:
```bash
# AND
echo $((5 & 3))                 # Expected: 1 (101 & 011 = 001)
echo $((12 & 10))               # Expected: 8 (1100 & 1010 = 1000)

# OR
echo $((5 | 3))                 # Expected: 7 (101 | 011 = 111)
echo $((12 | 10))               # Expected: 14 (1100 | 1010 = 1110)

# XOR
echo $((5 ^ 3))                 # Expected: 6 (101 ^ 011 = 110)
echo $((12 ^ 10))               # Expected: 6 (1100 ^ 1010 = 0110)

# NOT (32-bit two's complement)
echo $((~5))                    # Expected: -6
echo $((~0))                    # Expected: -1
echo $((~-1))                   # Expected: 0

# Shifts
echo $((1 << 3))                # Expected: 8
echo $((16 >> 2))               # Expected: 4
echo $((5 << 2))                # Expected: 20
echo $((-1 >> 1))               # Expected: -1 (arithmetic shift)
```

### 5. Comparison Operations Testing
Test all comparison operators.

#### Tests to Implement:
```bash
# Less than
echo $((5 < 10))                # Expected: 1 (true)
echo $((10 < 5))                # Expected: 0 (false)
echo $((5 < 5))                 # Expected: 0 (false)

# Greater than
echo $((10 > 5))                # Expected: 1 (true)
echo $((5 > 10))                # Expected: 0 (false)

# Less than or equal
echo $((5 <= 10))               # Expected: 1
echo $((5 <= 5))                # Expected: 1
echo $((10 <= 5))               # Expected: 0

# Greater than or equal
echo $((10 >= 5))               # Expected: 1
echo $((5 >= 5))                # Expected: 1
echo $((5 >= 10))               # Expected: 0

# Equality
echo $((5 == 5))                # Expected: 1
echo $((5 == 6))                # Expected: 0

# Inequality
echo $((5 != 6))                # Expected: 1
echo $((5 != 5))                # Expected: 0
```

### 6. Logical Operations Testing
Test logical operators with various truthy/falsy values.

#### Tests to Implement:
```bash
# Logical AND
echo $((1 && 1))                # Expected: 1
echo $((1 && 0))                # Expected: 0
echo $((0 && 1))                # Expected: 0
echo $((5 && 3))                # Expected: 1 (non-zero is true)

# Logical OR
echo $((1 || 0))                # Expected: 1
echo $((0 || 0))                # Expected: 0
echo $((0 || 5))                # Expected: 1

# Logical NOT
echo $((!0))                    # Expected: 1
echo $((!1))                    # Expected: 0
echo $((!5))                    # Expected: 0

# Short-circuit evaluation
x=0; echo $((0 && (x=1))); echo $x  # x should remain 0
x=0; echo $((1 || (x=1))); echo $x  # x should remain 0
```

### 7. Assignment Operations Testing
Test assignment and compound assignment operators.

#### Tests to Implement:
```bash
# Simple assignment
echo $((x = 10))                # Expected: 10, x set to 10
echo $x                         # Expected: 10

# Compound assignments
x=10; echo $((x += 5))          # Expected: 15
x=10; echo $((x -= 3))          # Expected: 7
x=10; echo $((x *= 2))          # Expected: 20
x=10; echo $((x /= 2))          # Expected: 5
x=10; echo $((x %= 3))          # Expected: 1

# Bitwise compound assignments
x=5; echo $((x &= 3))           # Expected: 1
x=5; echo $((x |= 3))           # Expected: 7
x=5; echo $((x ^= 3))           # Expected: 6
x=4; echo $((x <<= 2))          # Expected: 16
x=16; echo $((x >>= 2))         # Expected: 4

# Multiple assignments
echo $((x = y = z = 5))         # All set to 5
```

### 8. Increment/Decrement Testing
Test pre and post increment/decrement operators.

#### Tests to Implement:
```bash
# Pre-increment
x=5; echo $((++x))              # Expected: 6, x is 6
x=5; echo $((++x + 2))          # Expected: 8

# Post-increment
x=5; echo $((x++))              # Expected: 5, x becomes 6
x=5; echo $((x++ + 2))          # Expected: 7, x becomes 6

# Pre-decrement
x=5; echo $((--x))              # Expected: 4, x is 4
x=5; echo $((--x + 2))          # Expected: 6

# Post-decrement
x=5; echo $((x--))              # Expected: 5, x becomes 4
x=5; echo $((x-- + 2))          # Expected: 7, x becomes 4

# Complex cases
x=5; echo $((x++ + ++x))        # Expected: 12 (5 + 7)
```

### 9. Ternary Operator Testing
Test conditional expressions.

#### Tests to Implement:
```bash
# Basic ternary
echo $((1 ? 10 : 20))           # Expected: 10
echo $((0 ? 10 : 20))           # Expected: 20

# With comparisons
echo $((5 > 3 ? 100 : 200))     # Expected: 100
echo $((2 == 3 ? 10 : 20))      # Expected: 20

# Nested ternary
echo $((1 ? (2 ? 30 : 40) : 50)) # Expected: 30

# With side effects
x=5; echo $((x > 3 ? x++ : x--)) # Expected: 5, x becomes 6
```

### 10. Comma Operator Testing
Test comma operator for sequential evaluation.

#### Tests to Implement:
```bash
# Basic comma
echo $((5, 10))                 # Expected: 10 (last value)
echo $((1, 2, 3, 4, 5))         # Expected: 5

# With side effects
x=0; echo $((x=5, x+2))         # Expected: 7, x is 5
x=0; echo $((x++, x++, x))      # Expected: 2

# In other contexts
echo $((x = (1, 2, 3)))         # x set to 3
```

### 11. Number Format Testing
Test various number formats.

#### Tests to Implement:
```bash
# Decimal
echo $((42))                    # Expected: 42

# Octal (leading 0)
echo $((010))                   # Expected: 8
echo $((077))                   # Expected: 63

# Hexadecimal
echo $((0x10))                  # Expected: 16
echo $((0xff))                  # Expected: 255
echo $((0xFF))                  # Expected: 255

# With bases (bash extension)
echo $((2#1010))                # Expected: 10 (binary)
echo $((8#77))                  # Expected: 63 (octal)
echo $((16#FF))                 # Expected: 255 (hex)

# Large numbers
echo $((2147483647))            # Max 32-bit signed
echo $((-2147483648))           # Min 32-bit signed
```

### 12. Error Handling Testing
Test error conditions and recovery.

#### Tests to Implement:
```bash
# Division by zero
echo $((10 / 0))                # Should error or return specific value

# Syntax errors
echo $((5 +))                   # Missing operand
echo $((+ 5))                   # Valid unary plus
echo $(())                      # Empty expression (usually 0)

# Invalid numbers
echo $((10x))                   # Should error
echo $((0xGG))                  # Invalid hex

# Overflow (if applicable)
echo $((2147483647 + 1))        # Overflow behavior
echo $((-2147483648 - 1))       # Underflow behavior
```

### 13. Complex Expression Testing
Test realistic complex expressions.

#### Tests to Implement:
```bash
# Mathematical formulas
echo $((3 * (4 + 5) - 2))       # Expected: 25
echo $(((10 + 5) * 2 / 3))      # Expected: 10

# Mixed operations
x=5; y=3
echo $(((x > y) ? x * 2 : y * 3)) # Expected: 10

# Bit manipulation patterns
echo $(((5 & ~1) | 2))          # Clear bit 0, set bit 1

# Real-world calculations
bytes=1024
echo $((bytes * 1024 * 1024))   # Convert to GB

# Loop counters
i=0; echo $((i++, i*2))         # Expected: 2
```

### 14. Integration Testing
Test arithmetic expansion with other shell features.

#### Tests to Implement:
```bash
# In command substitution
result=$(echo $((5 + 3)))
echo $result                    # Expected: 8

# In parameter expansion
x=10
echo ${x:$((x/2)):3}           # Substring from position 5

# In array indices
arr=(0 10 20 30 40 50)
i=2
echo ${arr[$((i * 2))]}        # Expected: 40

# Multiple expansions
echo $((5 + 3)) $((10 - 2))    # Expected: 8 8

# In redirections
exec 3>&$((1 + 1))             # Redirect to fd 2
```

## Implementation Strategy

### Phase 1: Parser Testing (Already Complete)
- ✅ Basic syntax parsing
- ✅ All operators recognized
- ✅ Proper AST construction
- ✅ Word AST integration

### Phase 2: Evaluation Testing (Priority 1)
1. Create test file: `test_arithmetic_expansion_evaluation.py`
2. Test basic operations with known values
3. Verify operator precedence
4. Check variable integration
5. Validate special variables

### Phase 3: Advanced Features (Priority 2)
1. Test assignment operations
2. Verify increment/decrement behavior
3. Check ternary operator
4. Validate comma operator
5. Test number formats

### Phase 4: Error Handling (Priority 3)
1. Test division by zero
2. Check overflow/underflow
3. Verify syntax error handling
4. Test invalid expressions

### Phase 5: Integration Testing (Priority 4)
1. Test with other expansions
2. Verify in various contexts
3. Check performance
4. Validate bash compatibility

## Test File Structure

```python
# tests/unit/parser/test_arithmetic_expansion_evaluation.py
"""Test arithmetic expansion evaluation in parser combinator."""

class TestArithmeticEvaluation:
    """Test evaluation of arithmetic expressions."""
    
    def test_basic_addition(self, shell):
        """Test basic addition operations."""
        result = shell.run_command('echo $((5 + 3))')
        assert result == 0
        assert shell.captured_output() == "8\n"
    
    # ... more tests
```

## Success Criteria

1. **Functionality**: All arithmetic operations produce correct results
2. **Compatibility**: Behavior matches bash/POSIX specifications
3. **Reliability**: No crashes or unexpected errors
4. **Performance**: Complex expressions evaluate efficiently
5. **Integration**: Works seamlessly with other shell features

## Validation Approach

1. **Unit Tests**: Test each operator in isolation
2. **Integration Tests**: Test combinations and real-world usage
3. **Bash Comparison**: Compare results with bash for same expressions
4. **Edge Cases**: Test boundary conditions and error cases
5. **Performance Tests**: Measure evaluation time for complex expressions

## Documentation Requirements

1. Update feature roadmap with test completion status
2. Add examples to user guide if not already present
3. Document any PSH-specific behaviors or limitations
4. Create arithmetic expansion reference guide

## Timeline Estimate

- Phase 1: ✅ Complete (parser testing)
- Phase 2: 2-3 days (basic evaluation)
- Phase 3: 2-3 days (advanced features)
- Phase 4: 1-2 days (error handling)
- Phase 5: 1-2 days (integration)

Total: 6-10 days for complete arithmetic expansion testing

## Conclusion

This plan provides a systematic approach to achieving complete arithmetic expansion testing for the parser combinator. By following this plan, we can ensure that arithmetic expansion not only parses correctly but also evaluates properly in all contexts, matching bash behavior and providing a robust implementation for users.