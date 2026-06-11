# Chapter 8: Quoting and Escaping

Quoting and escaping control how PSH interprets special characters. Understanding these mechanisms is crucial for handling filenames with spaces, preserving literal values, and controlling when expansions occur. PSH follows standard shell quoting rules with three main mechanisms: single quotes, double quotes, and backslash escaping.

## 8.1 Single Quotes

Single quotes preserve the literal value of all characters within them. No expansions or interpretations occur inside single quotes.

### Basic Single Quote Usage

```bash
# Preserve literal text
psh$ echo 'Hello World'
Hello World

# Special characters remain literal
psh$ echo '$HOME'
$HOME

psh$ echo '* ? [ ]'
* ? [ ]

# No variable expansion
psh$ name="Alice"
psh$ echo 'Hello $name'
Hello $name

# No command substitution
psh$ echo '$(date)'
$(date)

# No escape sequences
psh$ echo 'Line 1\nLine 2'
Line 1\nLine 2

# Spaces preserved exactly
psh$ echo 'Multiple    spaces    preserved'
Multiple    spaces    preserved
```

### Single Quotes Limitations

```bash
# Cannot include a single quote inside single quotes
psh$ echo 'It's broken'  # Error!

# Workarounds for single quotes
psh$ echo 'It'\''s working'     # End quote, escape quote, start new quote
It's working

psh$ echo "It's working"        # Use double quotes instead
It's working

# Multiple lines preserved
psh$ echo 'Line 1
> Line 2
> Line 3'
Line 1
Line 2
Line 3

# Combining with unquoted text
psh$ echo 'Hello'$USER'!'       # Concatenation
HelloAlice!
```

## 8.2 Double Quotes

Double quotes preserve literal values of most characters but allow certain expansions: variable expansion ($), command substitution ($(...) or `...`), arithmetic expansion ($((...))) and escape sequences (\).

### Basic Double Quote Usage

```bash
# Preserve spaces
psh$ echo "Hello    World"
Hello    World

# Variable expansion works
psh$ name="Alice"
psh$ echo "Hello $name"
Hello Alice

# Command substitution works
psh$ echo "Today is $(date +%A)"
Today is Monday

# Arithmetic expansion works
psh$ count=5
psh$ echo "Count plus one is $((count + 1))"
Count plus one is 6

# But wildcards don't expand
psh$ echo "*.txt"
*.txt

# Special characters preserved
psh$ echo "Use | and > carefully"
Use | and > carefully
```

### Escape Sequences in Double Quotes

```bash
# Backslash escapes special characters
psh$ echo "She said \"Hello\""
She said "Hello"

# Escape the dollar sign
psh$ echo "The price is \$50"
The price is $50

# Escape backslash itself
psh$ echo "C:\\Users\\Alice"
C:\Users\Alice

# Newlines need $'...' or echo -e
psh$ echo "Line 1\nLine 2"          # Literal \n
Line 1\nLine 2

psh$ echo -e "Line 1\nLine 2"       # Interpreted
Line 1
Line 2

# Preserve backticks
psh$ echo "Use \`command\` syntax"
Use `command` syntax
```

### Variable Expansion in Double Quotes

```bash
# Simple variables
psh$ user="alice"
psh$ echo "User: $user"
User: alice

# Braces for clarity
psh$ echo "File: ${user}_backup.tar"
File: alice_backup.tar

# Without braces can be ambiguous
psh$ echo "File: $user_backup.tar"   # Looking for $user_backup
File: .tar

# Special variables
psh$ echo "PID: $$, Exit: $?, Args: $#"
PID: 12345, Exit: 0, Args: 0

# Array expansion (if supported)
psh$ set -- one two three
psh$ echo "All args: $@"
All args: one two three

psh$ echo "All as one: $*"
All as one: one two three

# Difference between $@ and $* in quotes
psh$ printf '[%s]\n' "$@"
[one]
[two]
[three]

psh$ printf '[%s]\n' "$*"
[one two three]
```

## 8.3 Escape Characters (\)

The backslash escapes the next character, removing its special meaning.

### Basic Escaping

```bash
# Escape spaces
psh$ echo Hello\ World
Hello World

# Escape special characters
psh$ echo \$HOME
$HOME

psh$ echo \*.\*
*.*

# Escape newlines for continuation
psh$ echo This is a very long line that \
> continues on the next line
This is a very long line that continues on the next line

# Escape quotes
psh$ echo \'Single\' and \"Double\" quotes
'Single' and "Double" quotes

# Escape backslash
psh$ echo \\
\

# Multiple escapes
psh$ echo \\\$\\\*
\$\*
```

### Line Continuation

```bash
# Long commands
psh$ ls -la \
>    --color=auto \
>    --time-style=long-iso \
>    /usr/bin

# Long pipelines
psh$ cat large_file.txt | \
>    grep "pattern" | \
>    sort | \
>    uniq -c | \
>    sort -rn | \
>    head -10

# Variable assignments
psh$ CLASSPATH=/usr/share/java/lib1.jar:\
> /usr/share/java/lib2.jar:\
> /usr/share/java/lib3.jar

# String continuation
psh$ message="This is a very long message that \
> spans multiple lines but will be \
> treated as a single line"
psh$ echo "$message"
This is a very long message that spans multiple lines but will be treated as a single line
```

## 8.4 ANSI-C Quoting

PSH supports two forms of ANSI-C escape sequence handling: the `$'...'` quoting syntax and `echo -e`.

### The $'...' Syntax

The `$'...'` syntax interprets escape sequences at the quoting level, before the command runs:

```bash
# Basic escape sequences
psh$ echo $'Line 1\nLine 2'
Line 1
Line 2

psh$ echo $'Column1\tColumn2'
Column1	Column2

# Hex sequences
psh$ echo $'\x48\x65\x6c\x6c\x6f'
Hello

# Escape character
psh$ echo $'\e[31mRed Text\e[0m'   # ANSI color
Red Text  # (displayed in red)

# Unicode
psh$ echo $'\u2665 \u2663'
♥ ♣

# Octal sequences
psh$ echo $'\101\102\103'
ABC
```

> **Note:** PSH's `$'...'` supports `\n`, `\t`, `\r`, `\\`, `\'`, `\"`, `\a`, `\b`, `\f`, `\v`, `\e`, `\xHH` (hex), `\uNNNN` (Unicode), and `\NNN` (octal, with or without a leading zero), matching bash.

### The echo -e Syntax

With `echo -e`, escape sequences are interpreted in the string argument:

```bash
# Basic escape sequences
psh$ echo -e "Line 1\nLine 2\nLine 3"
Line 1
Line 2
Line 3

psh$ echo -e "Column1\tColumn2\tColumn3"
Column1	Column2	Column3

# Escape character
psh$ echo -e "\e[31mRed Text\e[0m"      # ANSI color
Red Text  # (displayed in red)

psh$ echo -e "\033[1mBold Text\033[0m"  # Using octal
Bold Text  # (displayed in bold)

# Hex and Unicode
psh$ echo -e "\x48\x65\x6c\x6c\x6f"     # Hex ASCII
Hello

psh$ echo -e "\u2665 \u2663 \u2660 \u2666"  # Unicode
♥ ♣ ♠ ♦

psh$ echo -e "\U0001F600"               # Extended Unicode
😀

# Octal sequences (zero-prefixed)
psh$ echo -e "\0101\0102\0103"          # Octal ASCII
ABC

# Stop output with \c
psh$ echo -e "First\cThis won't appear"
First
```

## 8.5 Quote Removal

After all expansions, PSH removes quotes that were used to control interpretation:

```bash
# Quotes are removed from final output
psh$ echo "Hello" 'World'
Hello World

# Not: "Hello" 'World'

# Mixed quoting
psh$ name="Alice"
psh$ echo "Hello "$name', welcome to '"$HOME"
Hello Alice, welcome to /home/alice

# Empty quotes create empty argument
psh$ echo one "" three
one  three

# But completely empty gives nothing
psh$ echo ""

psh$ echo

# Quote removal after expansion
psh$ var="test"
psh$ echo "$var"ing
testing

# Complex example
psh$ echo 'Single'"Double"'Single'
SingleDoubleSingle
```

## Practical Examples

### Handling Filenames with Spaces

```bash
#!/usr/bin/env psh
# Safe file handling with proper quoting

# Create test files with spaces
touch "My Document.txt" "Another File.pdf" "Year 2024 Report.doc"

# Wrong way - without quotes
for file in *.txt *.pdf *.doc; do
    echo Processing $file    # Breaks on spaces!
done

# Right way - with quotes
for file in *.txt *.pdf *.doc; do
    echo "Processing $file"
    
    # Safe operations with quotes
    if [ -f "$file" ]; then
        size=$(wc -c < "$file")
        echo "  Size: $size bytes"
        
        # Safe copy with quotes
        cp "$file" "backup_$file"
    fi
done

# Using find with spaces
find . -name "* *" -type f | while read -r file; do
    echo "Found: $file"
    # Always quote when using the variable
    mv "$file" "${file// /_}"  # Replace spaces with underscores
done

# Array handling with spaces
files=("My Document.txt" "Another File.pdf" "Year 2024 Report.doc")
for file in "${files[@]}"; do
    echo "Array file: $file"
done
```

### Building Complex Commands

```bash
#!/usr/bin/env psh
# Build commands with proper quoting

# Database query builder
build_query() {
    local table="$1"
    local condition="$2"
    local fields="${3:-*}"
    
    # Build SQL with proper quoting
    local query="SELECT $fields FROM \"$table\""
    
    if [ -n "$condition" ]; then
        query="$query WHERE $condition"
    fi
    
    echo "$query"
}

# Usage examples
query1=$(build_query "users" "age > 18" "name, email")
echo "Query 1: $query1"

query2=$(build_query "products" "price < 100 AND category = 'electronics'" "*")
echo "Query 2: $query2"

# Command builder with escaping
safe_ssh() {
    local host="$1"
    shift
    local remote_cmd="$*"
    
    # Escape single quotes in command
    remote_cmd="${remote_cmd//\'/\'\\\'\'}"
    
    echo "Executing on $host: $remote_cmd"
    ssh "$host" "$remote_cmd"
}

# JSON builder with proper escaping
json_escape() {
    local text="$1"
    text="${text//\\/\\\\}"      # Escape backslashes first
    text="${text//\"/\\\"}"       # Escape quotes
    echo "$text"
}

build_json() {
    local name="$1"
    local value="$2"

    name=$(json_escape "$name")
    value=$(json_escape "$value")

    echo "{\"$name\": \"$value\"}"
}

# Test JSON builder
json=$(build_json "message" "Hello \"World\"")
echo "JSON: $json"
```

### Shell Script Generator

```bash
#!/usr/bin/env psh
# Generate shell scripts with proper quoting

generate_backup_script() {
    local backup_name="$1"
    local source_dir="$2"
    local dest_dir="$3"
    
    cat << 'SCRIPT_START'
#!/usr/bin/env psh
# Auto-generated backup script
SCRIPT_START

    # Use quoted heredoc to prevent expansion
    cat << SCRIPT_BODY

# Configuration
BACKUP_NAME='${backup_name}'
SOURCE_DIR='${source_dir}'
DEST_DIR='${dest_dir}'
DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="\${DEST_DIR}/\${BACKUP_NAME}_\${DATE}.tar.gz"

# Create destination directory
mkdir -p "\$DEST_DIR"

# Perform backup
echo "Starting backup of \$SOURCE_DIR"
if tar -czf "\$BACKUP_FILE" -C "\$SOURCE_DIR" .; then
    echo "Backup successful: \$BACKUP_FILE"
    ls -lh "\$BACKUP_FILE"
else
    echo "Backup failed!" >&2
    exit 1
fi

SCRIPT_BODY
}

# Generate a script
generate_backup_script "myproject" "/home/alice/project" "/backups" > backup_script.sh
chmod +x backup_script.sh

# Quote-aware argument parser
parse_args() {
    echo "Parsing arguments with quote awareness:"
    local i=1
    for arg in "$@"; do
        echo "  Arg $i: [$arg]"
        ((i++))
    done
}

# Test the parser
parse_args "simple" "with spaces" "with|pipe" 'with$var' "with\"quotes"
```

### Configuration File Parser

```bash
#!/usr/bin/env psh
# Parse simple key=value configuration files with quote handling

parse_config() {
    local config_file="$1"

    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        case "$key" in
            \#*|"") continue ;;
        esac

        # Remove surrounding quotes from value
        case "$value" in
            \"*\") value="${value#\"}"; value="${value%\"}" ;;
            \'*\') value="${value#\'}"; value="${value%\'}" ;;
        esac

        # Set the configuration variable
        if [ -n "$key" ]; then
            declare -g "CONFIG_$key=$value"
            echo "Set: CONFIG_$key = '$value'"
        fi
    done < "$config_file"
}

# Test configuration
cat > test.conf << 'EOF'
# Sample configuration file
name="My Application"
path='/usr/local/bin'
debug=true
port=8080
EOF

echo "Parsing configuration:"
parse_config test.conf

echo
echo "Configuration loaded:"
set | grep ^CONFIG_
```

## Common Quoting Patterns

### Safe Variable Usage

```bash
# Always quote variables in tests
if [ -z "$var" ]; then          # Safe
if [ -z $var ]; then            # Unsafe - breaks if var is unset

# Quote in case statements
case "$option" in               # Safe
case $option in                 # Unsafe if option contains spaces

# Quote command arguments
grep "$pattern" "$file"         # Safe
grep $pattern $file             # Unsafe

# Quote array expansions
for item in "${array[@]}"; do   # Safe - preserves array elements
for item in ${array[@]}; do     # Unsafe - word splitting occurs
```

### Mixing Quotes

```bash
# Combine quote types for complex strings
echo 'Don'"'"'t worry'          # Don't worry
echo "It's \"quoted\""          # It's "quoted"

# Build commands with mixed quoting
cmd='echo "Hello $USER"'        # $USER not expanded yet
eval "$cmd"                     # Now it expands

# Nested quoting
ssh remote "echo 'Remote says \"Hello\"'"
```

### Here Documents and Quoting

```bash
# Quoted delimiter prevents expansion
cat << 'EOF'
$HOME is literal
$(date) is literal
EOF

# Unquoted delimiter allows expansion
cat << EOF
$HOME expands to: $HOME
$(date) expands to: $(date)
EOF
```

> **Note:** The backslash-escaped delimiter form (`<< \EOF`) is not supported in PSH. Use the single-quoted form (`<< 'EOF'`) instead to prevent expansion in heredocs.

### Locale Translation Quoting ($"...")

> **Note:** PSH accepts the `$"..."` locale translation quoting syntax and treats it as an ordinary double-quoted string (variables and command substitutions expand normally). No message-catalog translation is performed — which matches bash's behavior when no translation catalog is loaded. This is a rarely used bash feature intended for internationalization (i18n) of shell scripts.

## Summary

Quoting and escaping in PSH provide precise control over interpretation:

1. **Single Quotes** preserve everything literally - no expansions
2. **Double Quotes** allow variable, command, and arithmetic expansion
3. **Backslash** escapes individual characters
4. **ANSI-C Quoting** (`$'...'` and `echo -e`) interprets escape sequences
5. **Quote Removal** happens after all expansions

Key principles:
- Always quote variables to handle spaces and special characters safely
- Use single quotes for literal strings
- Use double quotes when you need expansion
- Remember quotes are removed from the final result
- Combine quote types when needed
- Test your quoting with filenames containing spaces

Understanding quoting is essential for writing robust scripts that handle all inputs correctly. In the next chapter, we'll explore I/O redirection, which controls where command input comes from and output goes to.

---

[← Previous: Chapter 7 - Arithmetic](07_arithmetic.md) | [Next: Chapter 9 - Input/Output Redirection →](09_io_redirection.md)