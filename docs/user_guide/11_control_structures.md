# Chapter 11: Control Structures

Control structures enable conditional execution and loops in shell scripts. PSH provides full support for if statements, while and until loops, for loops (both traditional and C-style), case statements with fallthrough, select menus, and loop control commands. All control structures can also be used as pipeline components (see [Chapter 10](10_pipelines_and_lists.md#102-control-structures-in-pipelines)).

## 11.1 Conditional Statements (if/then/else/fi)

The if statement executes commands conditionally based on the exit status of test commands.

### Basic if Statement

```bash
# Simple if statement
psh$ if [ -f file.txt ]; then
>     echo "File exists"
> fi
File exists

# One-line if statement
psh$ if true; then echo "success"; fi
success

# Using command exit status
psh$ if ls /home; then
>     echo "Listed home directory"
> fi
/home/alice
Listed home directory

# Multiple commands in condition
psh$ if cd /tmp && ls -la; then
>     echo "Successfully changed directory and listed files"
> fi
```

### if/else Statement

```bash
# Basic if/else
psh$ if [ -f config.txt ]; then
>     echo "Config file found"
> else
>     echo "Config file missing"
> fi
Config file missing

# File existence check
psh$ filename="data.txt"
psh$ if [ -f "$filename" ]; then
>     echo "Processing $filename"
>     cat "$filename"
> else
>     echo "Creating $filename"
>     touch "$filename"
> fi
Creating data.txt

# Command success/failure
psh$ if ping -c 1 google.com >/dev/null 2>&1; then
>     echo "Network is up"
> else
>     echo "Network is down"
> fi
Network is up
```

### if/elif/else Statement

```bash
# Multiple conditions
psh$ score=85
psh$ if [ "$score" -ge 90 ]; then
>     echo "Grade: A"
> elif [ "$score" -ge 80 ]; then
>     echo "Grade: B"
> elif [ "$score" -ge 70 ]; then
>     echo "Grade: C"
> else
>     echo "Grade: F"
> fi
Grade: B

# File type detection
psh$ path="/etc/passwd"
psh$ if [ -f "$path" ]; then
>     echo "$path is a regular file"
> elif [ -d "$path" ]; then
>     echo "$path is a directory"
> elif [ -L "$path" ]; then
>     echo "$path is a symbolic link"
> else
>     echo "$path does not exist or is special"
> fi
/etc/passwd is a regular file
```

### Complex Conditions

```bash
# Multiple test conditions with && and ||
psh$ if [ -f file.txt ] && [ -r file.txt ]; then
>     echo "File exists and is readable"
> fi

# Using command -v to check for programs
psh$ if command -v git >/dev/null; then
>     echo "Git is installed"
> fi

# String comparisons
psh$ user="admin"
psh$ if [ "$user" = "admin" ] || [ "$user" = "root" ]; then
>     echo "Administrative user"
> fi

# Numeric comparisons
psh$ age=25
psh$ if [ "$age" -ge 18 ] && [ "$age" -le 65 ]; then
>     echo "Working age"
> fi
```

The `!` keyword negates a command's exit status, which is especially useful in conditionals:

```bash
psh$ if ! grep -q "$USER" /etc/passwd; then
>     echo "User not in passwd file"
> fi
```

### If Statements in Pipelines

If statements can be used as pipeline components:

```bash
# Conditional processing based on pipeline input
psh$ echo "success" | if grep -q "success"; then
>     echo "Success detected in pipeline"
> else
>     echo "Success not found"
> fi
Success detected in pipeline
```

## 11.2 While Loops (while/do/done)

While loops execute commands repeatedly as long as the condition remains true.

### Basic While Loop

```bash
# Simple counter
psh$ count=1
psh$ while [ "$count" -le 5 ]; do
>     echo "Count: $count"
>     count=$((count + 1))
> done
Count: 1
Count: 2
Count: 3
Count: 4
Count: 5

# Process files
psh$ while [ -f "input.txt" ]; do
>     echo "Processing input.txt"
>     mv input.txt processed.txt
>     sleep 1
> done
```

### Reading Input with While

```bash
# Read lines from file
psh$ while read line; do
>     echo "Line: $line"
> done < input.txt

# Read fields from CSV
psh$ while IFS=, read name age city; do
>     echo "Name: $name, Age: $age, City: $city"
> done < data.csv

# Process command output
psh$ ps aux | while read user pid cpu mem rest; do
>     if [ "$cpu" -gt 50 ]; then
>         echo "High CPU process: $pid ($cpu%)"
>     fi
> done
```

### While Loops in Pipelines

While loops can be used as pipeline components:

```bash
# Process data line by line through pipeline
psh$ echo -e "red\ngreen\nblue" | while read color; do
>     echo "Color: $color (length: ${#color})"
> done
Color: red (length: 3)
Color: green (length: 5)
Color: blue (length: 4)

# Count and process numbers
psh$ seq 1 5 | while read num; do
>     echo "Number $num squared is $((num * num))"
> done
Number 1 squared is 1
Number 2 squared is 4
Number 3 squared is 9
Number 4 squared is 16
Number 5 squared is 25
```

### While Loop Patterns

```bash
# Infinite loop with break
psh$ counter=0
psh$ while true; do
>     echo "Iteration $counter"
>     counter=$((counter + 1))
>     [ "$counter" -gt 3 ] && break
> done

# File monitoring
psh$ while true; do
>     if [ -f new_data.txt ]; then
>         echo "Processing new data"
>         mv new_data.txt processed/
>     fi
>     sleep 10
> done

# Log tail with processing
psh$ tail -f /var/log/app.log | while read line; do
>     echo "$line" | grep -q "ERROR" && echo "Error detected: $line"
> done
```

## 11.3 Until Loops (until/do/done)

Until loops execute commands repeatedly as long as the condition remains false (the opposite of while):

```bash
# Basic until loop
psh$ count=1
psh$ until [ "$count" -gt 3 ]; do
>     echo "Count: $count"
>     count=$((count + 1))
> done
Count: 1
Count: 2
Count: 3

# Wait for a file to appear
psh$ until [ -f /tmp/ready.flag ]; do
>     echo "Waiting for ready signal..."
>     sleep 5
> done
psh$ echo "Ready!"

# Wait for network
psh$ until ping -c 1 server.com >/dev/null 2>&1; do
>     echo "Waiting for server..."
>     sleep 5
> done
psh$ echo "Server is up!"
```

## 11.4 For Loops

PSH supports both traditional for/in loops and C-style for loops.

### Traditional For Loops (for/in/do/done)

```bash
# Basic for loop
psh$ for i in 1 2 3 4 5; do
>     echo "Number: $i"
> done
Number: 1
Number: 2
Number: 3
Number: 4
Number: 5

# Iterate over files
psh$ for file in *.txt; do
>     echo "Processing $file"
>     wc -l "$file"
> done

# Iterate over command output
psh$ for user in $(cat /etc/passwd | cut -d: -f1); do
>     echo "User: $user"
> done

# Iterate over arguments
process_files() {
    for file in "$@"; do
        if [ -f "$file" ]; then
            echo "Processing $file"
        else
            echo "Warning: $file not found"
        fi
    done
}

# Range with brace expansion
psh$ for i in {1..5}; do
>     echo "Item $i"
> done
Item 1
Item 2
Item 3
Item 4
Item 5

# Parsing structured data
psh$ for item in apple:red banana:yellow grape:purple; do
>     fruit=${item%:*}
>     color=${item#*:}
>     echo "$fruit is $color"
> done
apple is red
banana is yellow
grape is purple
```

### For Loops in Pipelines

For loops can be used as pipeline components:

```bash
# For loop as pipeline component
psh$ echo "processing data" | for item in alpha beta gamma; do
>     echo "Processing item: $item"
> done
Processing item: alpha
Processing item: beta
Processing item: gamma

# Dynamic for loop with pipeline input
psh$ seq 1 3 | for num in $(cat); do
>     echo "Processing number: $num (doubled: $((num * 2)))"
> done
Processing number: 1 (doubled: 2)
Processing number: 2 (doubled: 4)
Processing number: 3 (doubled: 6)
```

### C-Style For Loops

```bash
# Basic C-style for loop
psh$ for ((i=1; i<=5; i++)); do
>     echo "Iteration $i"
> done
Iteration 1
Iteration 2
Iteration 3
Iteration 4
Iteration 5

# With step increment
psh$ for ((i=0; i<=10; i+=2)); do
>     echo "Even number: $i"
> done
Even number: 0
Even number: 2
Even number: 4
Even number: 6
Even number: 8
Even number: 10

# Countdown
psh$ for ((i=5; i>=1; i--)); do
>     echo "Countdown: $i"
> done
psh$ echo "Go!"

# Multiple variables
psh$ for ((i=1, j=10; i<=3; i++, j--)); do
>     echo "i=$i, j=$j"
> done
i=1, j=10
i=2, j=9
i=3, j=8

# Infinite loop (use break to exit)
psh$ for ((;;)); do
>     echo "Infinite loop iteration"
>     break
> done
```

### Advanced For Loop Patterns

```bash
# Nested loops
psh$ for i in {1..3}; do
>     for j in a b c; do
>         echo "$i$j"
>     done
> done
1a
1b
1c
2a
2b
2c
3a
3b
3c

# Parallel processing simulation
psh$ for i in {1..5}; do
>     {
>         echo "Starting task $i"
>         sleep $i
>         echo "Completed task $i"
>     } &
> done
psh$ wait  # Wait for all background tasks

# File processing with progress
process_directory() {
    local dir="$1"
    local count=0

    for file in "$dir"/*.log; do
        [ -f "$file" ] || continue
        count=$((count + 1))
        echo "Processing file $count: $(basename "$file")"
        grep ERROR "$file" > "${file%.log}_errors.txt"
    done
}
```

## 11.5 Case Statements (case/esac)

Case statements provide pattern matching for multiple conditions.

### Basic Case Statement

```bash
# Simple case statement
psh$ option="start"
psh$ case "$option" in
>     start)
>         echo "Starting service"
>         ;;
>     stop)
>         echo "Stopping service"
>         ;;
>     restart)
>         echo "Restarting service"
>         ;;
>     *)
>         echo "Unknown option: $option"
>         ;;
> esac
Starting service

# File extension handling
process_file() {
    local file="$1"
    case "$file" in
        *.txt)
            echo "Processing text file: $file"
            cat "$file"
            ;;
        *.csv)
            echo "Processing CSV file: $file"
            cut -d, -f1 "$file"
            ;;
        *.log)
            echo "Processing log file: $file"
            tail -10 "$file"
            ;;
        *)
            echo "Unknown file type: $file"
            ;;
    esac
}

# Multiple patterns with |
psh$ answer=yes
psh$ case "$answer" in
>     y|Y|yes|YES)
>         echo "Accepted"
>         ;;
>     n|N|no|NO)
>         echo "Declined"
>         ;;
>     *)
>         echo "Please answer yes or no"
>         ;;
> esac
Accepted
```

### Pattern Matching

```bash
# Wildcard patterns
psh$ filename="report_2024.pdf"
psh$ case "$filename" in
>     *.pdf)
>         echo "PDF document"
>         ;;
>     *.doc|*.docx)
>         echo "Word document"
>         ;;
>     *.txt)
>         echo "Text file"
>         ;;
>     *)
>         echo "Unknown file type"
>         ;;
> esac
PDF document

# Character classes
psh$ input="5"
psh$ case "$input" in
>     [0-9])
>         echo "Single digit"
>         ;;
>     [a-z])
>         echo "Lowercase letter"
>         ;;
>     [A-Z])
>         echo "Uppercase letter"
>         ;;
>     *)
>         echo "Other character"
>         ;;
> esac
Single digit

# Range patterns
check_grade() {
    local score="$1"
    case "$score" in
        [9][0-9]|100)
            echo "Grade: A"
            ;;
        [8][0-9])
            echo "Grade: B"
            ;;
        [7][0-9])
            echo "Grade: C"
            ;;
        [6][0-9])
            echo "Grade: D"
            ;;
        *)
            echo "Grade: F"
            ;;
    esac
}
```

### Advanced Case Features

PSH supports the bash-style fallthrough (`;&`) and continue-matching (`;;&`) terminators:

```bash
# Fallthrough with ;&
psh$ value="2"
psh$ case "$value" in
>     1|2|3)
>         echo "Low value"
>         ;&  # Fallthrough to next case
>     [1-5])
>         echo "In range 1-5"
>         ;;
>     *)
>         echo "Other value"
>         ;;
> esac
Low value
In range 1-5

# Continue matching with ;;&
psh$ text="hello world"
psh$ case "$text" in
>     *hello*)
>         echo "Contains hello"
>         ;;&  # Continue matching
>     *world*)
>         echo "Contains world"
>         ;;&  # Continue matching
>     *o*)
>         echo "Contains letter o"
>         ;;
> esac
Contains hello
Contains world
Contains letter o
```

## 11.6 Loop Control (break and continue)

Break and continue statements control loop execution flow.

### Break Statement

```bash
# Basic break
psh$ for i in {1..10}; do
>     if [ "$i" -eq 5 ]; then
>         break
>     fi
>     echo "Number: $i"
> done
Number: 1
Number: 2
Number: 3
Number: 4

# Break from while loop
psh$ count=1
psh$ while true; do
>     echo "Count: $count"
>     count=$((count + 1))
>     if [ "$count" -gt 3 ]; then
>         break
>     fi
> done
Count: 1
Count: 2
Count: 3
```

### Continue Statement

```bash
# Basic continue
psh$ for i in {1..5}; do
>     if [ "$i" -eq 3 ]; then
>         continue
>     fi
>     echo "Number: $i"
> done
Number: 1
Number: 2
Number: 4
Number: 5

# Error handling with continue
process_files() {
    for file in "$@"; do
        if [ ! -f "$file" ]; then
            echo "Warning: $file not found, skipping"
            continue
        fi

        if [ ! -r "$file" ]; then
            echo "Warning: $file not readable, skipping"
            continue
        fi

        echo "Processing $file"
    done
}
```

### Multi-level Break and Continue

```bash
# Break from nested loops
psh$ for i in {1..3}; do
>     for j in {1..3}; do
>         echo "i=$i, j=$j"
>         if [ "$i" -eq 2 ] && [ "$j" -eq 2 ]; then
>             break 2  # Break from both loops
>         fi
>     done
> done
i=1, j=1
i=1, j=2
i=1, j=3
i=2, j=1
i=2, j=2

# Continue outer loop
psh$ for i in {1..3}; do
>     echo "Outer loop: $i"
>     for j in {1..3}; do
>         if [ "$j" -eq 2 ]; then
>             continue 2  # Continue outer loop
>         fi
>         echo "  Inner loop: $j"
>     done
>     echo "End of outer loop $i"
> done
Outer loop: 1
  Inner loop: 1
Outer loop: 2
  Inner loop: 1
Outer loop: 3
  Inner loop: 1
```

## 11.7 Select Statement (select/in/do/done)

The select statement creates interactive menus, allowing users to choose from a list of options.

### Basic Select Statement

```bash
# Simple menu
psh$ select option in "Start" "Stop" "Restart" "Status" "Exit"; do
>     case "$option" in
>         "Start")   echo "Starting service..." ;;
>         "Stop")    echo "Stopping service..." ;;
>         "Restart") echo "Restarting service..." ;;
>         "Status")  echo "Checking status..." ;;
>         "Exit")    break ;;
>         *)         echo "Invalid option" ;;
>     esac
> done
1) Start
2) Stop
3) Restart
4) Status
5) Exit
#? 3
Restarting service...
#? 5

# Using variable in select
psh$ fruits="apple banana orange grape"
psh$ select fruit in $fruits; do
>     echo "You selected: $fruit"
>     break
> done
1) apple
2) banana
3) orange
4) grape
#? 2
You selected: banana
```

### Using REPLY Variable

The select statement sets two variables:
- The chosen variable receives the selected item
- REPLY contains the raw user input (the number entered)

```bash
# Using REPLY for numeric choices
psh$ select item in "Option A" "Option B" "Option C"; do
>     echo "You selected #$REPLY: $item"
>     break
> done
1) Option A
2) Option B
3) Option C
#? 2
You selected #2: Option B

# Handling invalid input
psh$ select choice in "Yes" "No" "Maybe"; do
>     if [ -z "$choice" ]; then
>         echo "Invalid selection: $REPLY"
>         continue
>     fi
>     echo "You chose: $choice"
>     break
> done
1) Yes
2) No
3) Maybe
#? 4
Invalid selection: 4
#? 1
You chose: Yes
```

### Custom Prompt with PS3

The PS3 variable controls the select prompt (default is "#? "):

```bash
# Custom select prompt
psh$ PS3="Please enter your choice: "
psh$ select option in "Create" "Edit" "Delete" "List" "Quit"; do
>     case "$option" in
>         "Create") echo "Creating new item..." ;;
>         "Edit")   echo "Editing item..." ;;
>         "Delete") echo "Deleting item..." ;;
>         "List")   echo "Listing items..." ;;
>         "Quit")   break ;;
>     esac
> done
1) Create
2) Edit
3) Delete
4) List
5) Quit
Please enter your choice: 2
Editing item...
Please enter your choice: 5
```

### Practical Select Examples

```bash
# File operation menu
file_menu() {
    local PS3="Choose file operation: "
    local filename

    read -p "Enter filename: " filename

    select operation in "View" "Copy" "Delete" "Back"; do
        case "$operation" in
            "View")
                if [ -f "$filename" ]; then
                    cat "$filename"
                else
                    echo "File not found: $filename"
                fi
                ;;
            "Copy")
                read -p "Copy to: " destination
                cp "$filename" "$destination"
                echo "Copied to $destination"
                ;;
            "Delete")
                read -p "Are you sure? (y/n): " confirm
                if [ "$confirm" = "y" ]; then
                    rm "$filename"
                    echo "File deleted"
                    break
                fi
                ;;
            "Back")
                break
                ;;
            *)
                echo "Invalid option: $REPLY"
                ;;
        esac
    done
}
```

## 11.8 Enhanced Test Operators [[ ]]

PSH supports the enhanced test syntax `[[ ]]` with additional operators beyond what `[ ]` provides.

### String Comparisons

```bash
# Equality
psh$ if [[ "hello" == "hello" ]]; then
>     echo "Match"
> fi
Match

# Lexicographic comparison
psh$ if [[ "apple" < "banana" ]]; then
>     echo "apple comes before banana"
> fi
apple comes before banana

# Multiple conditions with && and ||
psh$ user="admin"
psh$ if [[ "$user" == "admin" && -f "/etc/passwd" ]]; then
>     echo "Admin user with passwd file"
> fi
Admin user with passwd file

# No word splitting needed
psh$ text="hello world"
psh$ if [[ $text == "hello world" ]]; then  # No quotes needed on left side
>     echo "Match found"
> fi
Match found
```

### Regular Expression Matching

```bash
# Basic regex matching
psh$ if [[ "hello123" =~ ^hello[0-9]+$ ]]; then
>     echo "Matches pattern"
> fi
Matches pattern

# Email-like pattern validation
psh$ email="user@example.com"
psh$ if [[ "$email" =~ @.*\. ]]; then
>     echo "Looks like an email"
> fi
Looks like an email

# File extension check
psh$ filename="report.txt"
psh$ if [[ "$filename" =~ \.txt$ ]]; then
>     echo "Text file detected"
> fi
Text file detected
```

Capture groups (parentheses in patterns) populate the `BASH_REMATCH` array after a successful match, and `!` negates conditions inside `[[ ]]`:

```bash
# Capture groups via BASH_REMATCH
psh$ if [[ "abc-123" =~ ^([a-z]+)-([0-9]+)$ ]]; then
>     echo "word=${BASH_REMATCH[1]} number=${BASH_REMATCH[2]}"
> fi
word=abc number=123

# Negation inside [[ ]]
psh$ if [[ ! -f /nonexistent ]]; then
>     echo "Not a file"
> fi
Not a file
```

## 11.9 Practical Examples

### System Administration Script

```bash
#!/usr/bin/env psh
# System maintenance script with control structures

LOG_FILE="/var/log/maintenance.log"
MAX_DISK_USAGE=80

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_disk_usage() {
    log "Checking disk usage..."

    df -h | while read filesystem size used avail percent mount; do
        # Skip header
        [ "$filesystem" = "Filesystem" ] && continue

        # Extract percentage number
        usage=${percent%\%}

        if [ "$usage" -gt "$MAX_DISK_USAGE" ] 2>/dev/null; then
            log "WARNING: $mount is ${usage}% full"

            case "$mount" in
                /var/log)
                    log "Cleaning old log files..."
                    find /var/log -name "*.log.*" -mtime +7 -delete
                    ;;
                /tmp)
                    log "Cleaning temporary files..."
                    find /tmp -type f -mtime +1 -delete
                    ;;
                *)
                    log "Manual intervention needed for $mount"
                    ;;
            esac
        else
            log "OK: $mount is ${usage}% full"
        fi
    done
}

backup_configs() {
    log "Backing up configuration files..."

    local backup_date=$(date +%Y%m%d)
    local backup_path="/backup/configs_$backup_date"

    mkdir -p "$backup_path"

    for config in /etc/passwd /etc/group /etc/fstab /etc/hosts; do
        if [ -f "$config" ]; then
            cp "$config" "$backup_path/"
            log "Backed up $config"
        else
            log "Config file not found: $config"
        fi
    done

    tar -czf "$backup_path.tar.gz" -C "/backup" "configs_$backup_date"
    rm -rf "$backup_path"
    log "Backup created: $backup_path.tar.gz"
}

main() {
    log "Starting maintenance script"

    for task in check_disk_usage backup_configs; do
        log "Running task: $task"

        if $task; then
            log "Task completed successfully: $task"
        else
            log "Task failed: $task"
        fi

        sleep 2
    done

    log "Maintenance script completed"
}

main "$@"
```

### Interactive Log Analysis

```bash
#!/usr/bin/env psh
# Interactive log analysis with control structures

interactive_mode() {
    while true; do
        echo
        echo "=== Log Analysis Menu ==="
        echo "1) Search for errors"
        echo "2) Find large files"
        echo "3) Show disk usage"
        echo "4) Exit"
        echo
        read -p "Choose option [1-4]: " choice

        case "$choice" in
            1)
                read -p "Enter log file path: " logfile
                if [ -f "$logfile" ]; then
                    echo "Errors found:"
                    grep -i "error" "$logfile" | tail -20
                else
                    echo "File not found: $logfile"
                fi
                ;;
            2)
                read -p "Enter directory to search: " directory
                if [ -d "$directory" ]; then
                    find "$directory" -type f -size +100M 2>/dev/null | while read file; do
                        size=$(du -h "$file" | cut -f1)
                        echo "$size $file"
                    done | sort -hr
                else
                    echo "Directory not found"
                fi
                ;;
            3)
                df -h
                ;;
            4)
                echo "Goodbye!"
                break
                ;;
            *)
                echo "Invalid option"
                ;;
        esac
    done
}

interactive_mode
```

## Summary

Control structures are essential for building complex shell scripts:

1. **if/then/elif/else/fi**: Conditional execution based on command exit status
2. **while/do/done**: Repeat commands while condition is true
3. **until/do/done**: Repeat commands until condition becomes true
4. **for/in/do/done**: Iterate over lists of items
5. **for ((;;))**: C-style loops with arithmetic expressions
6. **case/esac**: Pattern matching with `;;`, fallthrough with `;&`, and continue-matching with `;;&`
7. **select/in/do/done**: Interactive menu system with PS3 prompt and REPLY variable
8. **break/continue**: Control loop flow with optional levels (`break N`, `continue N`)
9. **[[ ]]**: Enhanced test operators with `==`, `<`, `>`, `=~` (regex), `&&`, `||`

Key concepts:
- All control structures use command exit status for decisions
- Proper quoting is essential for string comparisons
- Nested structures enable complex program logic
- Loop control statements provide fine-grained flow control
- Pattern matching in case statements supports wildcards, character classes, and ranges
- Select provides interactive menus with automatic numbering
- All control structures can be used as pipeline components

---

[← Previous: Chapter 10 - Pipelines and Lists](10_pipelines_and_lists.md) | [Next: Chapter 12 - Functions →](12_functions.md)
