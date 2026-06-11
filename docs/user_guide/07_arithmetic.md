# Chapter 7: Arithmetic

PSH provides comprehensive arithmetic capabilities for mathematical operations in shell scripts. From simple calculations to complex expressions, PSH supports integer arithmetic with a rich set of operators and multiple ways to evaluate expressions.

## 7.1 Arithmetic Expansion $((expr))

Arithmetic expansion evaluates mathematical expressions and returns their result as a string that can be used in commands.

### Basic Syntax

```bash
# Simple calculation
psh$ echo $((2 + 2))
4

# Using variables
psh$ x=10
psh$ y=3
psh$ echo $((x + y))
13

# Spaces are optional
psh$ echo $((5+3*2))
11

# Variables don't need $ inside arithmetic
psh$ a=100
psh$ echo $((a / 10))
10

# But $ works too
psh$ echo $(($a / 10))
10

# Assignment within expansion
psh$ echo $((sum = 5 + 3))
8
psh$ echo $sum
8
```

### Number Formats

```bash
# Decimal (default)
psh$ echo $((42))
42

# Hexadecimal (0x prefix)
psh$ echo $((0xFF))
255

psh$ echo $((0x10 + 0x20))
48

# Octal (0 prefix)
psh$ echo $((010))
8

psh$ echo $((0755))
493

# Binary (2# prefix)
psh$ echo $((2#1010))
10

psh$ echo $((2#11111111))
255

# Any base (base#number)
psh$ echo $((16#FF))     # Hexadecimal
255

psh$ echo $((8#77))      # Octal
63

psh$ echo $((2#1101))    # Binary
13

psh$ echo $((36#Z))      # Base 36
35
```

## 7.2 Arithmetic Commands ((expr))

Arithmetic commands execute expressions for their side effects and return an exit status based on the result.

```bash
# Basic arithmetic command
psh$ ((x = 5))
psh$ echo $x
5

# Exit status: 0 for non-zero result, 1 for zero
psh$ ((1 + 1))
psh$ echo $?
0

psh$ ((5 - 5))
psh$ echo $?
1

# In conditionals
psh$ if ((x > 3)); then
>     echo "x is greater than 3"
> fi
x is greater than 3

# Multiple expressions with comma
psh$ ((a=1, b=2, c=a+b))
psh$ echo "$a $b $c"
1 2 3

# In loops
psh$ for ((i=0; i<5; i++)); do
>     echo "i = $i"
> done
i = 0
i = 1
i = 2
i = 3
i = 4
```

## 7.3 Arithmetic Operators

PSH supports a comprehensive set of arithmetic operators with C-like precedence.

### Basic Arithmetic Operators

```bash
# Addition
psh$ echo $((5 + 3))
8

# Subtraction
psh$ echo $((10 - 3))
7

# Multiplication
psh$ echo $((4 * 5))
20

# Division (integer)
psh$ echo $((20 / 3))
6

# Modulo (remainder)
psh$ echo $((20 % 3))
2

# Exponentiation
psh$ echo $((2 ** 8))
256

psh$ echo $((3 ** 3))
27

# Negation
psh$ x=5
psh$ echo $((-x))
-5

# Mixed operations
psh$ echo $((2 + 3 * 4))
14

# Parentheses for grouping
psh$ echo $(((2 + 3) * 4))
20
```

### Comparison Operators

Comparison operators return 1 for true, 0 for false:

```bash
# Less than
psh$ echo $((5 < 10))
1

psh$ echo $((10 < 5))
0

# Greater than
psh$ echo $((10 > 5))
1

# Less than or equal
psh$ echo $((5 <= 5))
1

psh$ echo $((6 <= 5))
0

# Greater than or equal
psh$ echo $((5 >= 5))
1

# Equal
psh$ echo $((5 == 5))
1

psh$ echo $((5 == 6))
0

# Not equal
psh$ echo $((5 != 6))
1

# Chained comparisons
psh$ x=5
psh$ echo $(((x > 0) && (x < 10)))
1
```

### Logical Operators

```bash
# AND (&&)
psh$ echo $((1 && 1))
1

psh$ echo $((1 && 0))
0

psh$ echo $((0 && 0))
0

# OR (||)
psh$ echo $((1 || 0))
1

psh$ echo $((0 || 0))
0

# NOT (!)
psh$ echo $((! 0))
1

psh$ echo $((! 1))
0

psh$ echo $((! 5))    # Any non-zero is true
0

# Complex logical expressions
psh$ age=25
psh$ echo $(((age >= 18) && (age <= 65)))
1

psh$ score=85
psh$ echo $(((score >= 90) || (score == 100)))
0
```

### Bitwise Operators

```bash
# AND (&)
psh$ echo $((5 & 3))    # 101 & 011 = 001
1

# OR (|)
psh$ echo $((5 | 3))    # 101 | 011 = 111
7

# XOR (^)
psh$ echo $((5 ^ 3))    # 101 ^ 011 = 110
6

# NOT (~) - Two's complement
psh$ echo $((~5))       # Inverts all bits
-6

# Left shift (<<)
psh$ echo $((5 << 2))   # 101 << 2 = 10100
20

# Right shift (>>)
psh$ echo $((20 >> 2))  # 10100 >> 2 = 101
5

# Practical bit manipulation
psh$ flags=0
psh$ READ=4 WRITE=2 EXEC=1
psh$ ((flags = flags | READ))    # Set READ bit
psh$ ((flags = flags | WRITE))   # Set WRITE bit
psh$ echo $flags
6

psh$ echo $(( (flags & READ) != 0 ))  # Check READ bit
1
```

### Assignment Operators

```bash
# Simple assignment
psh$ ((x = 10))
psh$ echo $x
10

# Addition assignment
psh$ ((x += 5))    # x = x + 5
psh$ echo $x
15

# Subtraction assignment
psh$ ((x -= 3))    # x = x - 3
psh$ echo $x
12

# Multiplication assignment
psh$ ((x *= 2))    # x = x * 2
psh$ echo $x
24

# Division assignment
psh$ ((x /= 4))    # x = x / 4
psh$ echo $x
6

# Modulo assignment
psh$ ((x %= 4))    # x = x % 4
psh$ echo $x
2

# Bitwise assignment
psh$ x=12
psh$ ((x &= 10))   # x = x & 10
psh$ echo $x
8
psh$ ((x <<= 2))   # x = x << 2
psh$ echo $x
32
```

The full set of compound assignment operators is supported: `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, and `>>=`.

### Increment and Decrement

```bash
# Post-increment (x++)
psh$ x=5
psh$ echo $((x++))    # Returns x, then increments
5
psh$ echo $x
6

# Pre-increment (++x)
psh$ x=5
psh$ echo $((++x))    # Increments, then returns x
6
psh$ echo $x
6

# Post-decrement (x--)
psh$ x=5
psh$ echo $((x--))    # Returns x, then decrements
5
psh$ echo $x
4

# Pre-decrement (--x)
psh$ x=5
psh$ echo $((--x))    # Decrements, then returns x
4
psh$ echo $x
4

# In loops
psh$ i=0
psh$ while ((i++ < 5)); do
>     echo "i is now $i"
> done
i is now 1
i is now 2
i is now 3
i is now 4
i is now 5
```

## 7.4 Ternary Operator

The ternary operator provides conditional expressions:

```bash
# Basic syntax: condition ? true_value : false_value
psh$ age=18
psh$ echo $((age >= 18 ? 1 : 0))
1

psh$ score=75
psh$ echo $((score >= 60 ? score : 0))
75

# Nested ternary
psh$ grade=85
psh$ echo $((grade >= 90 ? 4 : grade >= 80 ? 3 : grade >= 70 ? 2 : 1))
3

# With variables
psh$ x=10 y=20
psh$ max=$((x > y ? x : y))
psh$ echo "Maximum is $max"
Maximum is 20

# Complex conditions
psh$ temp=25
psh$ echo $((temp < 0 ? -1 : temp > 30 ? 1 : 0))
0
```

## 7.5 Comma Operator

The comma operator evaluates multiple expressions, returning the last:

```bash
# Basic comma operator
psh$ echo $((5, 10))
10

psh$ echo $((x=5, y=10, x+y))
15

# Multiple assignments
psh$ ((a=1, b=2, c=3))
psh$ echo "$a $b $c"
1 2 3

# In for loops
psh$ for ((i=0, j=10; i<5; i++, j--)); do
>     echo "i=$i, j=$j"
> done
i=0, j=10
i=1, j=9
i=2, j=8
i=3, j=7
i=4, j=6

# Complex initialization
psh$ ((
>     sum=0,
>     count=0,
>     avg=0
> ))

# Side effects in order
psh$ x=5
psh$ echo $((x++, x++, x))
7
```

## 7.6 Variables in Arithmetic

Variables are treated specially in arithmetic contexts:

```bash
# No $ needed for variables
psh$ x=10 y=3
psh$ echo $((x + y))
13

# But $ still works
psh$ echo $(($x + $y))
13

# Undefined variables are 0
psh$ unset z
psh$ echo $((x + z))
10

# Empty strings are 0
psh$ empty=""
psh$ echo $((5 + empty))
5

# Non-numeric strings are 0
psh$ text="hello"
psh$ echo $((text + 5))
5

# Leading whitespace ignored
psh$ num="  42  "
psh$ echo $((num * 2))
84

# Variable indirection (recursively resolved, like bash)
psh$ a=5
psh$ b=a
psh$ echo $((b))      # b -> a -> 5
5

# Expression-valued variables are evaluated recursively too
psh$ a="2*3"
psh$ echo $((a))
6

# Command substitution in arithmetic
psh$ echo $(( $(echo 5) + $(echo 3) ))
8
```

## Practical Examples

### Calculator Function

```bash
#!/usr/bin/env psh
# Simple calculator using arithmetic expressions

calc() {
    if [ $# -eq 0 ]; then
        echo "Usage: calc <expression>"
        echo "Examples:"
        echo "  calc '2 + 2'"
        echo "  calc '(5 + 3) * 2'"
        echo "  calc '2 ** 8'"
        return 1
    fi
    
    local expr="$*"
    local result
    
    # Try to evaluate
    if result=$(( $expr )) 2>/dev/null; then
        echo "$result"
        
        # Show additional formats for large numbers
        if ((result > 255)); then
            printf "Hex: 0x%X\n" $result
            printf "Octal: 0%o\n" $result
        fi
    else
        echo "Error: Invalid expression"
        return 1
    fi
}

# Temperature converter
temp_convert() {
    local from="$1"
    local value="$2"
    
    case "$from" in
        c|C)
            local f=$(( (value * 9 / 5) + 32 ))
            local k=$(( value + 273 ))
            echo "${value}°C = ${f}°F = ${k}K"
            ;;
        f|F)
            local c=$(( (value - 32) * 5 / 9 ))
            local k=$(( (value - 32) * 5 / 9 + 273 ))
            echo "${value}°F = ${c}°C = ${k}K"
            ;;
        k|K)
            local c=$(( value - 273 ))
            local f=$(( (value - 273) * 9 / 5 + 32 ))
            echo "${value}K = ${c}°C = ${f}°F"
            ;;
        *)
            echo "Usage: temp_convert <c|f|k> <value>"
            return 1
            ;;
    esac
}

# Examples
calc "2 + 2"
calc "(100 - 30) * 2"
calc "2 ** 16"

temp_convert c 100
temp_convert f 32
temp_convert k 273
```

### Statistics Calculator

```bash
#!/usr/bin/env psh
# Calculate statistics from numbers

stats() {
    local -a numbers=("$@")
    local count=${#numbers[@]}
    
    if ((count == 0)); then
        echo "No numbers provided"
        return 1
    fi
    
    local sum=0
    local min=${numbers[0]}
    local max=${numbers[0]}
    local i
    
    # Calculate sum, min, max
    for ((i = 0; i < count; i++)); do
        local n=${numbers[i]}
        ((sum += n))
        ((n < min)) && min=$n
        ((n > max)) && max=$n
    done
    
    # Calculate average
    local avg=$((sum / count))
    local remainder=$((sum % count))
    
    # Calculate variance and standard deviation
    local variance=0
    for ((i = 0; i < count; i++)); do
        local diff=$((numbers[i] - avg))
        ((variance += diff * diff))
    done
    ((variance /= count))
    
    # Display results
    echo "Count: $count"
    echo "Sum: $sum"
    echo "Average: $avg.$((remainder * 100 / count))"
    echo "Min: $min"
    echo "Max: $max"
    echo "Range: $((max - min))"
    echo "Variance: $variance"
}

# Fibonacci generator
fibonacci() {
    local n=${1:-10}
    local a=0 b=1 temp
    
    echo "Fibonacci sequence (first $n numbers):"
    for ((i = 0; i < n; i++)); do
        echo -n "$a "
        ((temp = a + b, a = b, b = temp))
    done
    echo
}

# Prime checker
is_prime() {
    local n=$1
    
    ((n < 2)) && return 1
    ((n == 2)) && return 0
    ((n % 2 == 0)) && return 1
    
    local sqrt=$(echo "sqrt($n)" | bc 2>/dev/null || echo $((n / 2)))
    local i
    
    for ((i = 3; i <= sqrt; i += 2)); do
        ((n % i == 0)) && return 1
    done
    
    return 0
}

# Find primes in range
find_primes() {
    local start=${1:-1}
    local end=${2:-100}
    local count=0
    
    echo "Prime numbers between $start and $end:"
    for ((n = start; n <= end; n++)); do
        if is_prime $n; then
            echo -n "$n "
            ((count++))
        fi
    done
    echo
    echo "Total: $count primes"
}

# Examples
stats 45 67 23 89 12 56 34 78 90 23
echo
fibonacci 15
echo
find_primes 1 50
```

### Bit Manipulation Utilities

```bash
#!/usr/bin/env psh
# Bit manipulation and display utilities

# Show number in different bases
show_bases() {
    local num=$1
    
    echo "Decimal: $num"
    printf "Hexadecimal: 0x%X\n" $num
    printf "Octal: 0%o\n" $num
    
    # Binary representation
    local binary=""
    local n=$num
    while ((n > 0)); do
        binary="$((n & 1))$binary"
        ((n = n >> 1))
    done
    echo "Binary: ${binary:-0}"
}

# Show bit flags
show_flags() {
    local value=$1
    shift
    local -a flag_names=("$@")

    echo "Value: $value"
    echo "Flags set:"

    local i bit=1
    for ((i = 0; i < ${#flag_names[@]}; i++)); do
        if ((value & bit)); then
            echo "  [x] ${flag_names[i]} (bit $i, value $bit)"
        else
            echo "  [ ] ${flag_names[i]} (bit $i, value $bit)"
        fi
        ((bit = bit << 1))
    done
}

# Octal permission display
show_perm_octal() {
    local p=$1
    local result=""
    ((p & 4)) && result="${result}r" || result="${result}-"
    ((p & 2)) && result="${result}w" || result="${result}-"
    ((p & 1)) && result="${result}x" || result="${result}-"
    echo "$result"
}

# Octal to symbolic permission converter
perm_to_symbolic() {
    local perms=$((8#$1))
    echo -n "Symbolic: "
    for ((i = 8; i >= 0; i--)); do
        local bit=$((1 << i))
        if ((perms & bit)); then
            case $((i % 3)) in
                2) echo -n "r" ;;
                1) echo -n "w" ;;
                0) echo -n "x" ;;
            esac
        else
            echo -n "-"
        fi
    done
    echo

    echo "Owner: $((perms >> 6 & 7)) ($(show_perm_octal $((perms >> 6 & 7))))"
    echo "Group: $((perms >> 3 & 7)) ($(show_perm_octal $((perms >> 3 & 7))))"
    echo "Other: $((perms & 7)) ($(show_perm_octal $((perms & 7))))"
}

# Examples
show_bases 255
echo

show_flags 13 "READ" "WRITE" "EXECUTE" "DELETE"
echo

perm_to_symbolic "754"
```

## Summary

PSH provides comprehensive arithmetic capabilities:

1. **Arithmetic Expansion** `$((...))` evaluates expressions and returns results
2. **Arithmetic Commands** `((...))` execute expressions with exit status
3. **Rich Operator Set**: arithmetic, comparison, logical, bitwise, assignment (except bitwise assignment operators)
4. **Advanced Features**: ternary operator, comma operator, increment/decrement
5. **Flexible Variable Handling**: no $ needed, undefined = 0
6. **Multiple Number Formats**: decimal, hex, octal, binary, any base

Key points to remember:
- Integer arithmetic only (no floating point)
- Division truncates (20/3 = 6)
- Comparison operators return 1 (true) or 0 (false)
- Variables don't need $ inside arithmetic contexts
- Exit status: 0 for non-zero results, 1 for zero results

Arithmetic in PSH enables everything from simple calculations to complex bit manipulation, making it suitable for system administration, data processing, and general scripting tasks.

In the next chapter, we'll explore quoting and escaping, which controls how the shell interprets special characters.

---

[← Previous: Chapter 6 - Expansions](06_expansions.md) | [Next: Chapter 8 - Quoting and Escaping →](08_quoting_and_escaping.md)