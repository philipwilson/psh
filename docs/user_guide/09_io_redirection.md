# Chapter 9: Input/Output Redirection

I/O redirection is one of the most powerful features of the shell, allowing you to control where commands get their input and send their output. PSH supports all standard redirection operators, here documents, here strings, process substitution, and file descriptor manipulation.

## 9.1 Standard Streams (stdin, stdout, stderr)

Every process has three standard streams:
- **stdin** (0): Standard input - where commands read from
- **stdout** (1): Standard output - where commands write normal output
- **stderr** (2): Standard error - where commands write error messages

```bash
# Default behavior
psh$ echo "Hello"                    # stdout to terminal
Hello

psh$ read name                       # stdin from terminal
Alice
psh$ echo $name
Alice

psh$ ls /nonexistent                 # stderr to terminal
ls: /nonexistent: No such file or directory

# File descriptors
# 0 = stdin
# 1 = stdout
# 2 = stderr
```

## 9.2 Output Redirection (>, >>)

### Basic Output Redirection

```bash
# Redirect stdout to file (overwrite)
psh$ echo "Hello World" > output.txt
psh$ cat output.txt
Hello World

# Overwrite replaces existing content
psh$ echo "New content" > output.txt
psh$ cat output.txt
New content

# Append to file
psh$ echo "Line 1" > file.txt
psh$ echo "Line 2" >> file.txt
psh$ echo "Line 3" >> file.txt
psh$ cat file.txt
Line 1
Line 2
Line 3

# Create empty file
psh$ > empty.txt
psh$ ls -l empty.txt
-rw-r--r-- 1 alice alice 0 Jan 15 10:00 empty.txt

# Multiple commands via subshell
psh$ (echo "Header"; date; echo "Footer") > report.txt
psh$ cat report.txt
Header
Fri Feb 14 10:00:00 PST 2026
Footer

# Explicit file descriptor
psh$ echo "test" 1> output.txt      # Same as >
```

### Preventing Accidental Overwrites

```bash
# noclobber option prevents overwriting existing files
psh$ set -o noclobber
psh$ echo "first" > existing.txt     # Creates the file
psh$ echo "second" > existing.txt    # Fails!
psh: cannot overwrite existing file: existing.txt

# Append still works with noclobber
psh$ echo "more" >> existing.txt     # Safe with noclobber

# Disable noclobber
psh$ set +o noclobber
```

The `>|` operator forces an overwrite even while noclobber is set:

```bash
psh$ set -o noclobber
psh$ echo "second" >| existing.txt   # Succeeds despite noclobber
```

## 9.3 Input Redirection (<)

Input redirection reads from files instead of the keyboard:

```bash
# Read from file
psh$ wc -l < /etc/passwd
35

# Equivalent to
psh$ cat /etc/passwd | wc -l
35

# But more efficient (no cat process)

# Read variables from file
psh$ echo "Alice" > name.txt
psh$ read name < name.txt
psh$ echo "Hello, $name"
Hello, Alice

# Use with loops
psh$ cat > numbers.txt << EOF
1
2
3
4
5
EOF

psh$ while read num; do
>     echo "Number: $num"
> done < numbers.txt
Number: 1
Number: 2
Number: 3
Number: 4
Number: 5

# Combined input and output redirection
psh$ sort < unsorted.txt > sorted.txt
```

## 9.4 Error Redirection (2>, 2>>)

### Redirecting stderr

```bash
# Redirect stderr to file
psh$ ls /nonexistent 2> errors.txt
psh$ cat errors.txt
ls: /nonexistent: No such file or directory

# Append stderr
psh$ ls /another_nonexistent 2>> errors.txt

# Discard stderr
psh$ ls /nonexistent 2> /dev/null
# No error output

# Separate stdout and stderr
psh$ find /etc -name "*.conf" > configs.txt 2> errors.txt

# Both to same file (wrong way)
psh$ command > output.txt 2> output.txt    # Race condition!

# Both to same file (right way)
psh$ command > output.txt 2>&1
```

### Practical stderr Handling

```bash
# Log errors while showing output
psh$ make 2> build_errors.log | tee build_output.log

# Silent command with error check
psh$ if command 2>/dev/null; then
>     echo "Success"
> else
>     echo "Failed"
> fi

# Capture both streams separately
psh$ command 1> stdout.txt 2> stderr.txt
```

## 9.5 Combining Streams (2>&1, &>, >&2)

### Redirecting stderr to stdout

```bash
# Send stderr to stdout
psh$ ls /nonexistent 2>&1
ls: /nonexistent: No such file or directory

# Capture both in a file
psh$ command > output.txt 2>&1

# Order matters!
psh$ command 2>&1 > output.txt    # Wrong - stderr still to terminal

# Pipe both stdout and stderr
psh$ find / -name "*.log" 2>&1 | grep -v "Permission denied"

# Shorthand for > file 2>&1 (bash style)
psh$ command &> output.txt
```

> **Note:** The csh-style `>& file` syntax is not supported in PSH. Use `&> file` or `> file 2>&1` instead.

### Redirecting stdout to stderr

```bash
# Send output to stderr
psh$ echo "This is an error" >&2
This is an error    # Appears on stderr

# Useful in functions
error() {
    echo "Error: $*" >&2
}

warn() {
    echo "Warning: $*" >&2
}

# Usage
psh$ error "File not found"
Error: File not found

# In scripts
if [ ! -f "$file" ]; then
    echo "Cannot find $file" >&2
    exit 1
fi
```

## 9.6 Here Documents (<<, <<-)

Here documents provide multi-line input directly in scripts:

### Basic Here Documents

```bash
# Basic here document
psh$ cat << EOF
Line 1
Line 2
Line 3
EOF
Line 1
Line 2
Line 3

# With variable expansion
psh$ name="Alice"
psh$ cat << END
Hello, $name!
Today is $(date)
Your home is $HOME
END
Hello, Alice!
Today is Fri Feb 14 10:00:00 PST 2026
Your home is /home/alice

# Quoted delimiter prevents expansion
psh$ cat << 'EOF'
$HOME is literal
$(date) is literal
EOF
$HOME is literal
$(date) is literal

# Tab removal with <<-
psh$ cat <<- EOF
	Leading tabs removed
	But spaces remain
	    Mixed indentation
EOF
Leading tabs removed
But spaces remain
    Mixed indentation
```

### Here Documents in Scripts

```bash
#!/usr/bin/env psh
# Generate configuration files

# Create config file with variable expansion
cat > app.conf << EOF
# Application Configuration
# Generated on $(date)

[server]
host = localhost
port = 8080
workers = 4

[database]
driver = postgresql
host = ${DB_HOST:-localhost}
port = ${DB_PORT:-5432}
name = ${DB_NAME:-myapp}

[logging]
level = ${LOG_LEVEL:-info}
file = /var/log/app.log
EOF

# Create SQL script with no expansion (quoted delimiter)
cat > setup.sql << 'SQL'
-- Database setup script
CREATE DATABASE IF NOT EXISTS myapp;
USE myapp;

CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
SQL
```

## 9.7 Here Strings (<<<)

Here strings provide a single line of input:

```bash
# Basic here string
psh$ wc -w <<< "Hello World"
2

# Variable input
psh$ name="Alice"
psh$ read first last <<< "$name Smith"
psh$ echo "First: $first, Last: $last"
First: Alice, Last: Smith

# Useful for parsing
psh$ IFS=: read user pass uid gid rest <<< "root:x:0:0:root:/root:/bin/bash"
psh$ echo "User: $user, UID: $uid"
User: root, UID: 0

# Loop with here string
psh$ while read word; do
>     echo "Word: $word"
> done <<< "one two three"
Word: one two three

# For word splitting, use printf
psh$ printf '%s\n' one two three | while read word; do
>     echo "Word: $word"
> done
Word: one
Word: two
Word: three
```

## 9.8 Process Substitution (<(), >())

Process substitution lets you use command output as a file, or send output to a command as if writing to a file. This is a bash extension that PSH supports.

### Input Process Substitution (<())

```bash
# Use command output as a file
psh$ cat <(echo "hello from process sub")
hello from process sub

# Compare two command outputs
psh$ diff <(echo "hello") <(echo "world")
1c1
< hello
---
> world

# Use with commands that require file arguments
psh$ diff <(sort file1.txt) <(sort file2.txt)

# Multiple process substitutions
psh$ paste <(seq 1 3) <(seq 4 6)
1	4
2	5
3	6
```

### Output Process Substitution (>())

```bash
# Send output to a command
psh$ echo "test data" > >(cat)
test data

# Tee-like behavior with multiple destinations
psh$ echo "log entry" | tee >(grep "log" > matches.txt)
```

## 9.9 File Descriptors

Beyond standard streams, you can work with custom file descriptors:

### Writing to Custom File Descriptors

```bash
# Open file descriptor for writing
psh$ exec 4> output.txt

# Write to descriptor 4
psh$ echo "Hello" >&4
psh$ echo "World" >&4

# Close file descriptor
psh$ exec 4>&-

psh$ cat output.txt
Hello
World
```

### Saving and Restoring Streams

```bash
# Save stdout, redirect, then restore
psh$ exec 5>&1        # Save stdout to fd 5
psh$ exec 1> log.txt  # Redirect stdout to file
psh$ echo "This goes to log"
psh$ exec 1>&5        # Restore stdout
psh$ exec 5>&-        # Close saved descriptor
```

### Logging with Multiple File Descriptors

```bash
#!/usr/bin/env psh
# Logging with multiple file descriptors

# Setup logging
exec 3> debug.log    # Debug messages
exec 4> info.log     # Info messages
exec 5> error.log    # Error messages

# Logging functions
debug() { echo "[DEBUG] $*" >&3; }
info() { echo "[INFO] $*" >&4; }
error() { echo "[ERROR] $*" >&5; }

# Use logging
debug "Script started"
info "Processing files"

for file in *.txt; do
    if [ -f "$file" ]; then
        info "Processing $file"
    else
        error "File not found: $file"
    fi
done

# Cleanup
exec 3>&- 4>&- 5>&-
```

### Reading from Custom Descriptors

Descriptors opened with `exec` can be read with `read` via fd duplication, and `<>` opens a descriptor for both reading and writing:

```bash
# Read line by line from a custom descriptor
psh$ exec 3< data.txt
psh$ read first <&3      # Reads the first line
psh$ read second <&3     # Reads the second line
psh$ exec 3<&-           # Close it

# Read-write descriptor
psh$ exec 3<> scratch.txt
psh$ read line <&3
psh$ echo "more" >&3
psh$ exec 3>&-
```

File descriptor swapping chains (e.g., `3>&1 1>&2 2>&3 3>&-` to swap stdout and stderr) also work as in bash.

## 9.10 Redirections on Control Structures

PSH allows redirections on entire control structures:

### Loops with Redirection

```bash
# Redirect entire loop output
psh$ for i in 1 2 3; do
>     echo "Number: $i"
> done > numbers.txt

psh$ cat numbers.txt
Number: 1
Number: 2
Number: 3

# While loop reading from file
psh$ while read line; do
>     echo "Processing: $line"
> done < input.txt > output.txt 2> errors.txt

# Append mode
psh$ for file in *.log; do
>     echo "=== $file ==="
>     cat "$file"
> done >> combined.log
```

### Conditional and Case Redirections

```bash
# Redirect if statement
psh$ if [ -f data.txt ]; then
>     cat data.txt
>     echo "---"
>     wc -l data.txt
> fi > report.txt

# Redirect case statement
psh$ case "$option" in
>     start)
>         echo "Starting service..."
>         ;;
>     stop)
>         echo "Stopping service..."
>         ;;
> esac 2> service_errors.log

# Brace group with redirection
{
    echo "Line 1"
    echo "Line 2"
    echo "Line 3"
} > output.txt
```

## Practical Examples

### Backup Script with Logging

```bash
#!/usr/bin/env psh
# Backup with comprehensive logging

BACKUP_DIR="/backup"
LOG_DIR="/var/log/backup"
DATE=$(date +%Y%m%d_%H%M%S)

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Setup logging
exec 3> "$LOG_DIR/backup_$DATE.log"
exec 4>&1  # Save stdout

# Redirect stdout to log, keep stderr on terminal
exec 1>&3

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

show() {
    # Show on terminal and log
    echo "$*" >&4
    log "$*"
}

error() {
    echo "ERROR: $*" >&2
    log "ERROR: $*"
}

# Start backup
show "Starting backup at $(date)"

# Backup function
backup_directory() {
    local src="$1"
    local name="$(basename "$src")"
    local target="$BACKUP_DIR/${name}_$DATE.tar.gz"

    log "Backing up $src to $target"

    if tar -czf "$target" -C "$(dirname "$src")" "$name" 2>&1; then
        local size=$(du -h "$target" | cut -f1)
        show "$name backed up successfully ($size)"
    else
        error "Failed to backup $name"
        return 1
    fi
}

# Backup multiple directories
for dir in /home /etc /var/www; do
    if [ -d "$dir" ]; then
        backup_directory "$dir"
    else
        error "Directory not found: $dir"
    fi
done

# Summary
show "Backup completed at $(date)"
log "Disk usage: $(df -h "$BACKUP_DIR" | tail -1)"

# Restore descriptors
exec 1>&4 4>&- 3>&-
```

### Data Pipeline Builder

```bash
#!/usr/bin/env psh
# Build complex data processing pipelines

# Pipeline components
extract_data() {
    local source="$1"
    case "$source" in
        *.gz)  zcat "$source" ;;
        *.bz2) bzcat "$source" ;;
        *.zip) unzip -p "$source" ;;
        *)     cat "$source" ;;
    esac
}

transform_data() {
    local format="$1"
    case "$format" in
        csv)
            awk '{print $1","$2","$3}'
            ;;
        tsv)
            awk '{print $1"\t"$2"\t"$3}'
            ;;
    esac
}

# Build pipeline
process_file() {
    local input="$1"
    local output="$2"
    local format="${3:-csv}"
    local errors="errors_$(date +%s).log"

    {
        extract_data "$input" |
        grep -v "^#" |
        transform_data "$format" |
        sort |
        uniq
    } > "$output" 2> "$errors"

    # Check results
    if [ -s "$errors" ]; then
        echo "Errors occurred during processing:" >&2
        cat "$errors" >&2
    else
        rm -f "$errors"
    fi

    echo "Processed $(wc -l < "$output") lines"
}

# Usage
process_file "data.txt.gz" "output.csv" "csv"
```

## Common Patterns and Tips

### Safe Redirection Practices

```bash
# Always check before overwriting
if [ -f important.txt ]; then
    echo "File exists, backing up..."
    cp important.txt important.txt.bak
fi
command > important.txt

# Use tee for both display and save
command | tee output.txt

# Append with timestamp
echo "[$(date)] Log entry" >> logfile.txt

# Atomic file replacement
command > newfile.tmp && mv newfile.tmp finalfile.txt
```

### Debugging with Redirection

```bash
# Debug mode with conditional output
DEBUG=${DEBUG:-0}
debug() {
    [ "$DEBUG" -eq 1 ] && echo "DEBUG: $*" >&2
}

# Verbose logging
VERBOSE=${VERBOSE:-0}
exec 3>/dev/null
[ "$VERBOSE" -eq 1 ] && exec 3>&2

echo "Always shown"
echo "Only in verbose mode" >&3
```

## Summary

I/O redirection in PSH provides powerful control over data flow:

1. **Basic Redirection**: `>` (overwrite), `>>` (append), `<` (input)
2. **Error Handling**: `2>`, `2>>`, `2>&1` for stderr management
3. **Combined Output**: `&>` redirects both stdout and stderr
4. **Here Documents**: `<<` for multi-line input, `<<-` for tab-stripped input
5. **Here Strings**: `<<<` for single-line input
6. **Process Substitution**: `<()` and `>()` for using commands as files
7. **File Descriptors**: Writing to custom descriptors (3-9) with `exec`
8. **Control Structure Redirections**: Redirect entire loops, conditionals, and groups
9. **noclobber**: Prevent accidental overwrites with `set -o noclobber`

Key concepts:
- Three standard streams: stdin (0), stdout (1), stderr (2)
- Redirection order matters: `> file 2>&1` vs `2>&1 > file`
- Use `2>&1` or `&>` to combine stderr with stdout
- Here documents can expand variables or be literal (quoted delimiter)
- Process substitution enables powerful file-based command composition

Current limitations:
- `>& file` (csh-style) is not supported; use `&> file`

I/O redirection is fundamental to shell scripting, enabling log files, error handling, data processing pipelines, and clean separation of output types. In the next chapter, we'll explore pipelines and command lists.

---

[← Previous: Chapter 8 - Quoting and Escaping](08_quoting_and_escaping.md) | [Next: Chapter 10 - Pipelines and Lists →](10_pipelines_and_lists.md)
