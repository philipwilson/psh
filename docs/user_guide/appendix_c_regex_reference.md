# Appendix C: Regular Expression Reference

This appendix provides a comprehensive guide to regular expressions and pattern matching in PSH. Regular expressions are used in various contexts including the `[[` conditional operator's `=~` match, glob patterns, and case statement patterns.

## Table of Contents

1. [Pattern Matching Contexts](#pattern-matching-contexts)
2. [Glob Patterns](#glob-patterns)
3. [Regular Expression Basics](#regular-expression-basics)
4. [Character Classes](#character-classes)
5. [Quantifiers](#quantifiers)
6. [Anchors and Boundaries](#anchors-and-boundaries)
7. [Groups and Capturing](#groups-and-capturing)
8. [Common Patterns](#common-patterns)
9. [Case Statement Patterns](#case-statement-patterns)
10. [Examples and Recipes](#examples-and-recipes)

## Pattern Matching Contexts

PSH supports pattern matching in several contexts:

### 1. Pathname Expansion (Globbing)
```bash
ls *.txt          # All .txt files
rm temp??.log     # Remove temp files with 2 characters after 'temp'
cp [abc]*.sh ~/   # Copy scripts starting with a, b, or c
```

### 2. Conditional Expressions with `[[`
```bash
if [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo "Valid email format"
fi
```

### 3. Case Statements
```bash
case "$filename" in
    *.txt|*.log)     echo "Text file" ;;
    *.sh|*.bash)     echo "Shell script" ;;
    *.[ch])          echo "C source file" ;;
    *)               echo "Other file type" ;;
esac
```

### 4. Parameter Expansion
```bash
${var#pattern}   # Remove shortest match from beginning
${var##pattern}  # Remove longest match from beginning
${var%pattern}   # Remove shortest match from end
${var%%pattern}  # Remove longest match from end
${var/pattern/replacement}  # Replace first match
${var//pattern/replacement} # Replace all matches
```

## Glob Patterns

Glob patterns are used for filename matching and simple pattern matching:

### Basic Glob Metacharacters

| Pattern | Description | Example | Matches |
|---------|-------------|---------|---------|
| `*` | Match any string (including empty) | `*.txt` | `file.txt`, `a.txt`, `.txt` |
| `?` | Match any single character | `file?.txt` | `file1.txt`, `fileA.txt` |
| `[...]` | Match any character in set | `file[123].txt` | `file1.txt`, `file2.txt`, `file3.txt` |
| `[!...]` | Match any character NOT in set | `file[!0-9].txt` | `fileA.txt`, `file_.txt` |
| `[^...]` | Same as `[!...]` | `file[^0-9].txt` | `fileA.txt`, `file_.txt` |

### Character Ranges

```bash
[a-z]     # Any lowercase letter
[A-Z]     # Any uppercase letter
[0-9]     # Any digit
[a-zA-Z]  # Any letter
[a-f0-9]  # Any hexadecimal digit (lowercase)
```

### Character Classes in Globs

```bash
[[:alnum:]]   # Alphanumeric characters [a-zA-Z0-9]
[[:alpha:]]   # Alphabetic characters [a-zA-Z]
[[:digit:]]   # Digits [0-9]
[[:lower:]]   # Lowercase letters [a-z]
[[:upper:]]   # Uppercase letters [A-Z]
[[:space:]]   # Whitespace characters
[[:punct:]]   # Punctuation characters
```

### Glob Examples

```bash
# Match hidden files (starting with .)
ls .[!.]*

# Match files with 3-letter extensions
ls *.???

# Match files starting with 'log' followed by a digit
ls log[0-9]*

# Match all except backup files
ls *[!~]
```

## Regular Expression Basics

When using the `=~` operator in `[[ ]]`, PSH supports POSIX Extended Regular Expressions (ERE):

### Basic Metacharacters

| Character | Description | Example | Matches |
|-----------|-------------|---------|---------|
| `.` | Any single character | `a.c` | `abc`, `a1c`, `a c` |
| `*` | Zero or more of preceding | `ab*c` | `ac`, `abc`, `abbc` |
| `+` | One or more of preceding | `ab+c` | `abc`, `abbc` (not `ac`) |
| `?` | Zero or one of preceding | `ab?c` | `ac`, `abc` (not `abbc`) |
| `\|` | Alternation (OR) | `cat\|dog` | `cat` or `dog` |
| `()` | Grouping | `(ab)+` | `ab`, `abab`, `ababab` |
| `[]` | Character class | `[aeiou]` | Any vowel |
| `[^]` | Negated character class | `[^0-9]` | Any non-digit |

### Escaping Special Characters

To match literal metacharacters, escape them with backslash:

```bash
\.    # Literal period
\*    # Literal asterisk
\?    # Literal question mark
\[    # Literal square bracket
\\    # Literal backslash
\$    # Literal dollar sign
\^    # Literal caret
```

## Character Classes

### Predefined Character Classes

| Class | Description | Equivalent |
|-------|-------------|------------|
| `[[:alnum:]]` | Alphanumeric | `[a-zA-Z0-9]` |
| `[[:alpha:]]` | Alphabetic | `[a-zA-Z]` |
| `[[:blank:]]` | Space or tab | `[ \t]` |
| `[[:cntrl:]]` | Control characters | `[\x00-\x1F\x7F]` |
| `[[:digit:]]` | Decimal digits | `[0-9]` |
| `[[:graph:]]` | Visible characters | `[!-~]` |
| `[[:lower:]]` | Lowercase letters | `[a-z]` |
| `[[:print:]]` | Printable characters | `[ -~]` |
| `[[:punct:]]` | Punctuation | ``[!-/:-@\[-`{-~]`` |
| `[[:space:]]` | Whitespace | `[ \t\n\r\f\v]` |
| `[[:upper:]]` | Uppercase letters | `[A-Z]` |
| `[[:xdigit:]]` | Hexadecimal digits | `[0-9A-Fa-f]` |

### Custom Character Classes

```bash
[aeiou]          # Any vowel
[^aeiou]         # Any non-vowel
[a-z0-9_]        # Alphanumeric plus underscore
[a-zA-Z0-9.-]    # Letters, digits, period, hyphen
```

## Quantifiers

### Basic Quantifiers

| Quantifier | Description | Example | Matches |
|------------|-------------|---------|---------|
| `*` | 0 or more | `a*` | `""`, `a`, `aa`, `aaa` |
| `+` | 1 or more | `a+` | `a`, `aa`, `aaa` |
| `?` | 0 or 1 | `a?` | `""`, `a` |
| `{n}` | Exactly n | `a{3}` | `aaa` |
| `{n,}` | n or more | `a{2,}` | `aa`, `aaa`, `aaaa` |
| `{n,m}` | Between n and m | `a{2,4}` | `aa`, `aaa`, `aaaa` |

### Quantifier Examples

```bash
# Match repeated words
[[ "$text" =~ ([[:alpha:]]+)[[:space:]]+\1 ]]

# Match IP address octets (simplified)
[[ "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]

# Match US phone numbers
[[ "$phone" =~ ^[0-9]{3}-[0-9]{3}-[0-9]{4}$ ]]
```

## Anchors and Boundaries

### Position Anchors

| Anchor | Description | Example | Matches |
|--------|-------------|---------|---------|
| `^` | Start of string | `^Hello` | "Hello" at beginning |
| `$` | End of string | `world$` | "world" at end |
| `\<` | Word boundary (start) | `\<cat` | "cat" in "the cat" |
| `\>` | Word boundary (end) | `cat\>` | "cat" in "cat sat" |
| `\b` | Word boundary | `\bcat\b` | "cat" as whole word |
| `\B` | Not word boundary | `\Bcat` | "cat" in "scat" |

### Anchor Examples

```bash
# Match lines starting with comment
[[ "$line" =~ ^[[:space:]]*# ]]

# Match file extensions
[[ "$file" =~ \.(txt|log|dat)$ ]]

# Match whole words
[[ "$text" =~ \<word\> ]]
```

## Groups and Capturing

### Grouping Constructs

| Construct | Description | Example |
|-----------|-------------|---------|
| `()` | Capturing group | `(ab)+` |
| `\1`, `\2` | Backreference | `(.).*\1` |
| `(?:)` | Non-capturing group* | `(?:ab)+` |

*Note: Non-capturing groups may not be supported in all PSH regex contexts.

### Grouping Examples

```bash
# Match repeated characters
[[ "$text" =~ (.)\1{2,} ]]  # Three or more same characters

# Match quoted strings
[[ "$text" =~ ["\']([^"\']*)["\'] ]]

# Match HTML tags (simplified)
[[ "$html" =~ \<([a-zA-Z]+)\>.*\</\1\> ]]
```

## Common Patterns

### Email Address (Simplified)
```bash
^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
```

### URL (Basic)
```bash
^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$
```

### IPv4 Address
```bash
^([0-9]{1,3}\.){3}[0-9]{1,3}$
```

### Date (YYYY-MM-DD)
```bash
^[0-9]{4}-[0-9]{2}-[0-9]{2}$
```

### Time (HH:MM:SS)
```bash
^[0-9]{2}:[0-9]{2}:[0-9]{2}$
```

### Username (Alphanumeric + underscore)
```bash
^[a-zA-Z0-9_]{3,16}$
```

### Hexadecimal Color Code
```bash
^#[0-9A-Fa-f]{6}$
```

### Floating Point Number
```bash
^-?[0-9]+(\.[0-9]+)?$
```

## Case Statement Patterns

Case statements in PSH use glob patterns with some extensions:

### Basic Case Patterns

```bash
case "$var" in
    # Exact match
    hello)
        echo "Exact match" ;;
    
    # Glob patterns
    *.txt)
        echo "Text file" ;;
    
    # Character classes
    [0-9]*)
        echo "Starts with digit" ;;
    
    # Multiple patterns
    *.jpg|*.png|*.gif)
        echo "Image file" ;;
    
    # Default
    *)
        echo "No match" ;;
esac
```

### Advanced Case Features

```bash
# Fallthrough with ;&
case "$char" in
    [a-z])
        echo "Lowercase"
        ;&  # Fall through to next
    [a-zA-Z])
        echo "Letter" ;;
esac

# Continue matching with ;;&
case "$num" in
    *[0-9]*)
        echo "Contains digit"
        ;;&  # Continue checking
    *[02468])
        echo "Ends with even digit" ;;
esac
```

## Examples and Recipes

### Validation Functions

```bash
# Validate email
is_email() {
    [[ "$1" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]
}

# Validate integer
is_integer() {
    [[ "$1" =~ ^-?[0-9]+$ ]]
}

# Validate positive number
is_positive() {
    [[ "$1" =~ ^[0-9]+(\.[0-9]+)?$ ]] && [[ "$1" != "0" ]]
}

# Validate filename (no path separators)
is_filename() {
    [[ "$1" =~ ^[^/]+$ ]] && [[ "$1" != "." ]] && [[ "$1" != ".." ]]
}
```

### Text Processing

```bash
# Extract domain from email (using parameter expansion)
email="user@example.com"
domain="${email#*@}"  # Removes everything up to and including @

# Remove leading zeros
number="00123"
cleaned="${number##0}"  # Remove leading zero (use a loop for multiple)

# Extract file extension
filename="document.pdf"
extension="${filename##*.}"

# Remove file extension
basename="${filename%.*}"
```

### Pattern Matching in Loops

```bash
# Process different file types
for file in *; do
    case "$file" in
        *.sh|*.bash)
            echo "Shell script: $file"
            chmod +x "$file"
            ;;
        *.txt|*.md)
            echo "Text file: $file"
            ;;
        *.bak|*~)
            echo "Backup file: $file"
            ;;
    esac
done

# Filter files by pattern
for file in *; do
    if [[ "$file" =~ ^[0-9]{8}_.*\.log$ ]]; then
        echo "Processing log: $file"
    fi
done
```

### Advanced Pattern Usage

```bash
# Parse configuration lines
while read line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue

    # Parse key=value using parameter expansion
    key="${line%%=*}"
    value="${line#*=}"
    echo "Key: $key, Value: $value"
done < config.file

# Validate and parse version numbers using parameter expansion
version="v2.5.3-beta"
# Strip leading 'v'
ver="${version#v}"
# Extract major.minor.patch
major="${ver%%.*}"
rest="${ver#*.}"
minor="${rest%%.*}"
rest="${rest#*.}"
patch="${rest%%-*}"
echo "Major: $major, Minor: $minor, Patch: $patch"
```

## Pattern Matching Best Practices

1. **Anchor patterns when needed** - Use `^` and `$` to match entire strings
2. **Escape special characters** - Remember to escape `.`, `*`, `?`, etc. when matching literally
3. **Use character classes** - `[[:alpha:]]` is more portable than `[a-zA-Z]`
4. **Test patterns thoroughly** - Edge cases often reveal pattern flaws
5. **Keep patterns simple** - Complex patterns are hard to maintain
6. **Document complex patterns** - Add comments explaining what patterns match
7. **Consider case sensitivity** - Use `shopt -s nocasematch` for case-insensitive matching (if available)

## Limitations in PSH

While PSH supports many pattern matching features, some limitations exist:

1. **Limited backreferences** - Backreferences may not work in all contexts
2. **No Perl-style extensions** - Advanced regex features like lookahead/lookbehind aren't supported (same as bash)
3. **POSIX ERE only** - Extended regular expressions, not Perl-compatible (PCRE); same as bash

Capturing groups in `[[ string =~ regex ]]` patterns are fully supported, and successful matches populate the `BASH_REMATCH` array (`${BASH_REMATCH[0]}` is the whole match, `${BASH_REMATCH[1]}` the first group, and so on).

## Quick Reference Card

### Glob Patterns
```
*           Any string
?           Any single character  
[abc]       Any of a, b, or c
[!abc]      Any except a, b, or c
[a-z]       Any lowercase letter
```

### Regex Metacharacters
```
.           Any character
^           Start of string
$           End of string
*           0 or more
+           1 or more
?           0 or 1
|           Alternation
()          Grouping
[]          Character class
[^]         Negated class
```

### Common Character Classes
```
[[:alnum:]]  Alphanumeric
[[:alpha:]]  Letters
[[:digit:]]  Digits
[[:lower:]]  Lowercase
[[:upper:]]  Uppercase
[[:space:]]  Whitespace
```

This reference should help you effectively use pattern matching in PSH for file operations, string validation, text processing, and control flow.