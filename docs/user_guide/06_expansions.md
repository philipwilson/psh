# Chapter 6: Expansions

Shell expansions transform the text you type into the commands that actually run. Understanding expansion order and behavior is crucial for effective shell use. PSH performs expansions in a specific order, with each type serving a distinct purpose.

## 6.1 Expansion Order

PSH performs expansions in this order:
1. Brace expansion
2. Tilde expansion  
3. Parameter and variable expansion
4. Command substitution
5. Arithmetic expansion
6. Word splitting
7. Pathname expansion (globbing)
8. Quote removal

Understanding this order helps predict how your commands will be interpreted:

```bash
# Example showing multiple expansions
psh$ echo ~/{file1,file2}-{a,b}.{txt,log}
/home/alice/file1-a.txt /home/alice/file1-a.log /home/alice/file1-b.txt /home/alice/file1-b.log /home/alice/file2-a.txt /home/alice/file2-a.log /home/alice/file2-b.txt /home/alice/file2-b.log

# Breaking it down:
# 1. Brace expansion: {file1,file2}-{a,b}.{txt,log}
# 2. Tilde expansion: ~/... becomes /home/alice/...
# 3. No other expansions apply
# Result: 8 different filenames
```

## 6.2 Brace Expansion

Brace expansion generates strings based on patterns. It happens before other expansions, making it powerful for creating multiple similar items.

### List Expansion

```bash
# Basic list
psh$ echo {apple,banana,cherry}
apple banana cherry

# With prefix/suffix
psh$ echo file{1,2,3}.txt
file1.txt file2.txt file3.txt

# Multiple braces
psh$ echo {a,b}{1,2}
a1 a2 b1 b2

# Nested braces
psh$ echo {a,b{1,2},c}
a b1 b2 c

# Empty elements
psh$ echo {a,,c}
a  c

# In commands
psh$ mkdir dir{1,2,3}
psh$ ls
dir1  dir2  dir3

# Backup files
psh$ cp file.conf{,.bak}
# Expands to: cp file.conf file.conf.bak
```

### Sequence Expansion

```bash
# Numeric sequences
psh$ echo {1..5}
1 2 3 4 5

psh$ echo {10..1}
10 9 8 7 6 5 4 3 2 1

# With increment
psh$ echo {0..20..5}
0 5 10 15 20

# Zero-padded
psh$ echo {01..10}
01 02 03 04 05 06 07 08 09 10

# Character sequences
psh$ echo {a..e}
a b c d e

psh$ echo {Z..T}
Z Y X W V U T

# Mixed case
psh$ echo {a..F}
# Expands using ASCII values

# Practical examples
psh$ touch log-{01..12}-2024.txt
psh$ ls
log-01-2024.txt  log-04-2024.txt  log-07-2024.txt  log-10-2024.txt
log-02-2024.txt  log-05-2024.txt  log-08-2024.txt  log-11-2024.txt
log-03-2024.txt  log-06-2024.txt  log-09-2024.txt  log-12-2024.txt

# Create directory structure
psh$ mkdir -p project/{src,tests,docs}/{main,utils,helpers}
psh$ tree project
project
├── docs
│   ├── helpers
│   ├── main
│   └── utils
├── src
│   ├── helpers
│   ├── main
│   └── utils
└── tests
    ├── helpers
    ├── main
    └── utils
```

### Combining List and Sequence

```bash
# Mix list and sequence
psh$ echo {{1..3},{a..c}}
1 2 3 a b c

# Multiple expansions
psh$ echo {2020..2022}-{01..03}-{01..05}
# Generates dates for 3 years × 3 months × 5 days = 45 dates

# Complex patterns
psh$ echo img_{portrait,landscape}_{small,medium,large}_{01..03}.jpg
# Generates 18 filenames
```

## 6.3 Tilde Expansion

Tilde expansion provides shortcuts to home directories:

```bash
# Current user's home
psh$ echo ~
/home/alice

# Specific user's home
psh$ echo ~bob
/home/bob

# In paths
psh$ echo ~/Documents
/home/alice/Documents

# Multiple tildes
psh$ echo ~/file1 ~bob/file2
/home/alice/file1 /home/bob/file2

# Tilde must be at word boundary
psh$ echo test~
test~

# Quoted tildes are not expanded
psh$ echo "~"
~
psh$ echo '~'
~
```

> **Note:** PSH supports `~`, `~/path`, and `~username` tilde expansion but does not currently support `~+` (current directory) or `~-` (previous directory). Use `$PWD` and `$OLDPWD` as alternatives.

## 6.4 Command Substitution

Command substitution replaces a command with its output:

### Modern Syntax: $(...)

```bash
# Basic substitution
psh$ echo "Today is $(date)"
Today is Mon Jan 15 14:30:45 PST 2024

# Capture in variable
psh$ current_date=$(date +%Y-%m-%d)
psh$ echo $current_date
2024-01-15

# Nested substitution
psh$ echo "File count: $(ls $(pwd) | wc -l)"
File count: 42

# Multi-line commands
psh$ result=$(
>     echo "Line 1"
>     echo "Line 2"
>     echo "Line 3"
> )
psh$ echo "$result"
Line 1
Line 2
Line 3

# In arithmetic
psh$ count=$(($(ls | wc -l) * 2))
psh$ echo $count
84
```

### Legacy Syntax: `...`

```bash
# Backticks (legacy, less preferred)
psh$ echo "Today is `date`"
Today is Mon Jan 15 14:30:45 PST 2024

# Nesting is difficult with backticks
psh$ echo "Count: `ls \`pwd\` | wc -l`"
# Complex escaping required

# Modern syntax is clearer
psh$ echo "Count: $(ls $(pwd) | wc -l)"
Count: 42

# Both work, but $(...) is recommended
psh$ old_way=`whoami`
psh$ new_way=$(whoami)
psh$ echo "$old_way = $new_way"
alice = alice
```

### Command Substitution Tips

```bash
# Preserve newlines with quotes
psh$ lines=$(ls -l)
psh$ echo $lines    # Newlines become spaces
total 48 -rw-r--r-- 1 alice alice 1234 Jan 15 10:00 file1.txt ...

psh$ echo "$lines"  # Newlines preserved
total 48
-rw-r--r-- 1 alice alice 1234 Jan 15 10:00 file1.txt
...

# Error handling
psh$ result=$(command_that_fails 2>&1)
psh$ if [ $? -ne 0 ]; then
>     echo "Command failed: $result"
> fi

# Read file via cat
psh$ content=$(cat file.txt)
```

> **Note:** The `$(< file)` shortcut for reading files (without running `cat`) is not supported in PSH. Use `$(cat file)` instead.

## 6.5 Arithmetic Expansion $((...))

Arithmetic expansion evaluates mathematical expressions:

### Basic Arithmetic

```bash
# Basic operations
psh$ echo $((2 + 2))
4

psh$ echo $((10 - 3))
7

psh$ echo $((4 * 5))
20

psh$ echo $((20 / 4))
5

psh$ echo $((17 % 5))
2

psh$ echo $((2 ** 8))
256

# Variables in arithmetic
psh$ x=10
psh$ y=3
psh$ echo $((x + y))
13

psh$ echo $((x * y))
30

# Increment/decrement
psh$ i=5
psh$ echo $((++i))  # Pre-increment
6
psh$ echo $i
6

psh$ echo $((i++))  # Post-increment
6
psh$ echo $i
7
```

### Advanced Operations

```bash
# Comparison operators (return 1 for true, 0 for false)
psh$ echo $((5 > 3))
1

psh$ echo $((5 < 3))
0

psh$ echo $((5 == 5))
1

psh$ echo $((5 != 5))
0

# Logical operators
psh$ echo $((1 && 1))
1

psh$ echo $((1 || 0))
1

psh$ echo $((! 0))
1

# Bitwise operators
psh$ echo $((5 & 3))   # AND: 101 & 011 = 001
1

psh$ echo $((5 | 3))   # OR: 101 | 011 = 111
7

psh$ echo $((5 ^ 3))   # XOR: 101 ^ 011 = 110
6

psh$ echo $((~5))      # NOT (two's complement)
-6

psh$ echo $((5 << 2))  # Left shift
20

psh$ echo $((20 >> 2)) # Right shift
5

# Ternary operator
psh$ age=18
psh$ echo $((age >= 18 ? 1 : 0))
1

```

### Arithmetic in Practice

```bash
# Loop with arithmetic
psh$ for ((i=0; i<5; i++)); do
>     echo "Count: $i"
> done
Count: 0
Count: 1
Count: 2
Count: 3
Count: 4

# Calculate percentages
psh$ used=45
psh$ total=100
psh$ percent=$((used * 100 / total))
psh$ echo "${percent}% used"
45% used

# File size calculations
psh$ bytes=1048576
psh$ kb=$((bytes / 1024))
psh$ mb=$((bytes / 1024 / 1024))
psh$ echo "$bytes bytes = $kb KB = $mb MB"
1048576 bytes = 1024 KB = 1 MB
```

## 6.6 Pathname Expansion (Globbing)

Pathname expansion matches filenames using patterns:

### Basic Wildcards

```bash
# * matches zero or more characters
psh$ ls *.txt
file1.txt  file2.txt  document.txt

# ? matches exactly one character
psh$ ls file?.txt
file1.txt  file2.txt

# [...] matches any character in set
psh$ ls file[123].txt
file1.txt  file2.txt  file3.txt

# Ranges in brackets
psh$ ls file[1-5].txt
file1.txt  file2.txt  file3.txt  file4.txt  file5.txt

psh$ ls [a-c]*.txt
apple.txt  banana.txt  cherry.txt

# Negation with [!...] or [^...]
psh$ ls file[!1].txt
file2.txt  file3.txt  file4.txt  file5.txt
```

### Advanced Patterns

```bash
# Multiple patterns
psh$ ls *.{txt,log,tmp}
file.txt  error.log  cache.tmp

# Hidden files (. files not matched by default)
psh$ ls *
file1  file2  file3

psh$ ls .*
.  ..  .bashrc  .profile

# Match all including hidden (except . and ..)
psh$ ls {*,.[!.]*}
file1  file2  file3  .bashrc  .profile

# Recursive patterns (with find)
psh$ find . -name "*.txt"
./file1.txt
./subdir/file2.txt
./subdir/deep/file3.txt

# Character classes
psh$ ls [[:digit:]]*
1file  2file  3file

psh$ ls [[:alpha:]]*
afile  bfile  cfile

# Escaping wildcards
psh$ touch 'file*.txt'
psh$ ls file\*.txt
file*.txt
```

### Glob Expansion Behavior

```bash
# No matches - pattern remains literal
psh$ echo no_such_file_*
no_such_file_*

# Disable globbing for a command
psh$ set -f  # Or set -o noglob
psh$ echo *
*
psh$ set +f  # Re-enable

# Quotes prevent globbing
psh$ echo "*"
*
psh$ echo '*'
*

# Empty matches
psh$ shopt -s nullglob
psh$ echo no_match_*
# (empty output - no matching files, so nothing is printed)
psh$ shopt -u nullglob  # Restore default behavior
```

## 6.7 Process Substitution

Process substitution treats command output as a file:

### Input Process Substitution <(...)

```bash
# Compare two command outputs
psh$ diff <(ls dir1) <(ls dir2)
2c2
< file1.txt
---
> file2.txt

# Multiple inputs
psh$ paste <(seq 1 5) <(seq 6 10)
1	6
2	7
3	8
4	9
5	10

# Read from command output
psh$ while read line; do
>     echo "Line: $line"
> done < <(ls -l)
Line: total 48
Line: -rw-r--r-- 1 alice alice 1234 Jan 15 10:00 file1.txt
...

# Use with comm
psh$ comm <(sort file1) <(sort file2)
```

### Output Process Substitution >(...)

```bash
# Write to multiple commands
psh$ echo "test data" | tee >(md5sum) >(wc -c) >/dev/null
39df5136522d3eca1ee80c7a44b6b65f  -
10

# Log to file and analyze simultaneously
psh$ command 2>&1 | tee >(grep ERROR > errors.log) >(grep WARN > warnings.log)

# Multiple outputs
psh$ seq 1 100 | tee >(grep 1 > ones.txt) >(grep 2 > twos.txt) > all.txt

# Process and save
psh$ cat data.txt | tee >(gzip > data.gz) | analysis_program
```

### Process Substitution Examples

```bash
# Compare directory structures
psh$ diff <(cd dir1 && find . | sort) <(cd dir2 && find . | sort)

# Join data from commands
psh$ join <(sort users.txt) <(sort scores.txt)

# Real-time log analysis
psh$ tail -f app.log | tee >(grep ERROR >&2) | grep -v DEBUG

# Benchmark comparison
psh$ time command1 > >(tee output1.txt) 2> >(tee errors1.txt >&2)
```

## Practical Examples

### Bulk File Operations

```bash
#!/usr/bin/env psh
# Bulk rename files using expansions

# Rename all .jpeg to .jpg
for file in *.jpeg; do
    [ -f "$file" ] || continue
    mv "$file" "${file%.jpeg}.jpg"
done

# Add date prefix to files
date_prefix=$(date +%Y%m%d)
for file in *.{txt,log}; do
    [ -f "$file" ] || continue
    mv "$file" "${date_prefix}_${file}"
done

# Convert spaces to underscores
for file in *\ *; do
    [ -f "$file" ] || continue
    newname=${file// /_}
    mv "$file" "$newname"
done

# Batch resize images (requires ImageMagick)
mkdir -p thumbnails
for img in *.{jpg,png}; do
    [ -f "$img" ] || continue
    convert "$img" -resize 200x200 "thumbnails/thumb_${img}"
done
```

### System Report Generator

```bash
#!/usr/bin/env psh
# Generate system report using various expansions

report_file="system_report_$(date +%Y%m%d_%H%M%S).txt"

{
    echo "=== System Report - $(date) ==="
    echo
    
    # System info
    echo "Hostname: $(hostname)"
    echo "Uptime: $(uptime)"
    echo "Kernel: $(uname -r)"
    echo
    
    # Disk usage
    echo "=== Disk Usage ==="
    df -h | grep -E '^/dev/'
    echo
    
    # Memory info
    echo "=== Memory ==="
    free -h 2>/dev/null || vm_stat 2>/dev/null
    echo
    
    # CPU info
    echo "=== CPU ==="
    if [ -f /proc/cpuinfo ]; then
        grep "model name" /proc/cpuinfo | head -1
        echo "Cores: $(grep -c processor /proc/cpuinfo)"
    else
        sysctl -n machdep.cpu.brand_string 2>/dev/null
    fi
    echo
    
    # Network interfaces
    echo "=== Network ==="
    ip addr 2>/dev/null || ifconfig
    echo
    
    # Recent logs
    echo "=== Recent System Logs ==="
    journalctl -n 20 --no-pager 2>/dev/null || tail -20 /var/log/system.log 2>/dev/null
    
} > "$report_file"

echo "Report saved to: $report_file"

# Create summary
{
    echo "Summary for $(date +%Y-%m-%d):"
    echo "- Disk usage: $(df -h / | awk 'NR==2 {print $5}')"
    echo "- Load average: $(uptime | grep -o 'load average:.*')"
    echo "- Memory free: $(free -h 2>/dev/null | awk '/^Mem:/ {print $4}')"
} > "summary_${report_file}"
```

### Advanced File Finder

```bash
#!/usr/bin/env psh
# Find files using multiple expansion techniques

find_files() {
    local pattern="$1"
    local days="${2:-7}"
    local size="${3:-+0c}"
    
    echo "Searching for files matching pattern: $pattern"
    echo "Modified within $days days, size $size"
    echo
    
    # Find in common locations
    for dir in ~ ~/Documents ~/Downloads /tmp /var/log; do
        [ -d "$dir" ] || continue
        
        echo "=== Searching $dir ==="
        find "$dir" -name "$pattern" -type f -mtime -"$days" -size "$size" 2>/dev/null |
        while read -r file; do
            size=$(du -h "$file" | cut -f1)
            date=$(date -r "$file" +%Y-%m-%d 2>/dev/null || stat -f %Sm -t %Y-%m-%d "$file")
            echo "  $date $size $file"
        done
    done
}

# Search for various file types
echo "Recent large log files:"
find_files "*.log" 7 "+1M"

echo -e "\nRecent backup files:"
find_files "*.{bak,backup,old}" 30

echo -e "\nTemporary files:"
find_files "{tmp,temp,cache}*" 1

# Find duplicate filenames
echo -e "\n=== Potential Duplicates ==="
find ~ -type f -name "*copy*" -o -name "*([0-9])*" 2>/dev/null |
    grep -E '\(([0-9]+)\)|copy|Copy|COPY' |
    sort
```

## Summary

Shell expansions are powerful text transformation tools that execute in a specific order:

1. **Brace expansion** generates multiple strings from patterns
2. **Tilde expansion** provides home directory shortcuts
3. **Command substitution** captures command output
4. **Arithmetic expansion** evaluates mathematical expressions
5. **Pathname expansion** matches files using wildcards
6. **Process substitution** treats command I/O as files

Understanding expansion order and syntax enables you to:
- Write concise commands that expand to complex operations
- Avoid common pitfalls with quoting and escaping
- Combine multiple expansions for powerful one-liners
- Create efficient scripts using expansion features

The key to mastering expansions is practice and understanding when each type applies. In the next chapter, we'll dive deeper into arithmetic operations and expressions.

---

[← Previous: Chapter 5 - Variables and Parameters](05_variables_and_parameters.md) | [Next: Chapter 7 - Arithmetic →](07_arithmetic.md)