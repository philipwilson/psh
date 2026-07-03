# Chapter 5: Variables and Parameters

Variables are fundamental to shell programming. They store data that can be used throughout your scripts and interactive sessions. PSH supports shell variables, environment variables, special variables, and advanced parameter expansion features.

## 5.1 Variable Assignment and Usage

### Basic Variable Assignment

Variables in PSH follow these rules:
- Names start with a letter or underscore
- Can contain letters, numbers, and underscores
- Case-sensitive
- No spaces around the = sign

```bash
# Basic assignment
psh$ name="Alice"
psh$ age=25
psh$ city="New York"

# Using variables
psh$ echo "Hello, $name"
Hello, Alice

psh$ echo "Age: $age, City: $city"
Age: 25, City: New York

# Variable names are case-sensitive
psh$ Name="Bob"
psh$ echo "$name vs $Name"
Alice vs Bob

# No spaces allowed around =
psh$ var = "value"     # Wrong - runs 'var' command
psh: var: command not found

psh$ var= "value"      # Wrong - runs "value" with empty var
psh: value: command not found

psh$ var ="value"      # Wrong - runs 'var' command  
psh: var: command not found

psh$ var="value"       # Correct
```

### Variable Naming Conventions

```bash
# Valid variable names
psh$ user_name="alice"
psh$ USER_NAME="ALICE"
psh$ _private="hidden"
psh$ var123="numeric"
psh$ myVar="camelCase"

# Invalid names (won't work)
psh$ 123var="bad"      # Can't start with number
psh$ my-var="bad"      # No hyphens allowed
psh$ my var="bad"      # No spaces allowed
psh$ my.var="bad"      # No dots allowed

# Convention: Use UPPERCASE for environment/constants
psh$ readonly MAX_RETRIES=3
psh$ export DATABASE_URL="postgresql://localhost/mydb"

# Convention: Use lowercase for local variables
psh$ counter=0
psh$ temp_file="/tmp/data.tmp"
```

### Variable Scope

```bash
# Variables are global by default
psh$ global_var="I'm global"

psh$ show_var() {
>     echo "Inside function: $global_var"
>     global_var="Modified in function"
> }

psh$ show_var
Inside function: I'm global
psh$ echo "After function: $global_var"
After function: Modified in function

# Local variables in functions
psh$ test_locals() {
>     local local_var="I'm local"
>     echo "Inside function: $local_var"
> }

psh$ test_locals
Inside function: I'm local
psh$ echo "Outside function: $local_var"
Outside function: 
```

## 5.2 Environment vs Shell Variables

### Shell Variables

Shell variables exist only within the current shell:

```bash
# Create shell variable
psh$ MY_VAR="shell variable"
psh$ echo $MY_VAR
shell variable

# Not visible to child processes
psh$ psh -c 'echo "Child sees: $MY_VAR"'
Child sees: 

# View all shell variables with set
psh$ set | grep MY_VAR
MY_VAR=shell variable
```

### Environment Variables

Environment variables are passed to child processes:

```bash
# Export to environment
psh$ export ENV_VAR="environment variable"
psh$ echo $ENV_VAR
environment variable

# Visible to child processes
psh$ psh -c 'echo "Child sees: $ENV_VAR"'
Child sees: environment variable

# Export existing variable
psh$ ANOTHER_VAR="test"
psh$ psh -c 'echo "Before export: $ANOTHER_VAR"'
Before export: 
psh$ export ANOTHER_VAR
psh$ psh -c 'echo "After export: $ANOTHER_VAR"'
After export: test

# View environment with env
psh$ env | grep ENV_VAR
ENV_VAR=environment variable
```

### Common Environment Variables

```bash
# System-defined variables
psh$ echo $HOME
/home/alice

psh$ echo $USER
alice

psh$ echo $PATH
/usr/local/bin:/usr/bin:/bin

psh$ echo $PWD
/home/alice/documents

psh$ echo $SHELL
/usr/bin/psh

# Modify PATH
psh$ export PATH="$PATH:/home/alice/bin"
psh$ echo $PATH
/usr/local/bin:/usr/bin:/bin:/home/alice/bin

# Temporary environment for one command
psh$ TEMP_VAR=value command
psh$ echo $TEMP_VAR  # Not set in current shell
```

## 5.3 Special Variables

PSH provides several special variables with specific meanings:

### Positional Parameters

```bash
# In scripts or functions
# script.sh:
#!/usr/bin/env psh
echo "Script name: $0"
echo "First argument: $1"
echo "Second argument: $2"
echo "Third argument: $3"
echo "All arguments: $@"
echo "All as string: $*"
echo "Number of arguments: $#"

# Running the script
psh$ ./script.sh apple banana cherry
Script name: ./script.sh
First argument: apple
Second argument: banana
Third argument: cherry
All arguments: apple banana cherry
All as string: apple banana cherry
Number of arguments: 3

# Difference between $@ and $*
psh$ show_args() {
>     echo "Using \$@:"
>     for arg in "$@"; do
>         echo "  [$arg]"
>     done
>     echo "Using \$*:"
>     for arg in "$*"; do
>         echo "  [$arg]"
>     done
> }

psh$ show_args "hello world" "foo bar"
Using $@:
  [hello world]
  [foo bar]
Using $*:
  [hello world foo bar]
```

### Process Variables

```bash
# Current process ID
psh$ echo $$
12345

# Last background process ID
psh$ sleep 100 &
[1] 12346
psh$ echo $!
12346

# Exit status of last command
psh$ true
psh$ echo $?
0

psh$ false
psh$ echo $?
1

psh$ ls /nonexistent
ls: cannot access '/nonexistent': No such file or directory
psh$ echo $?
2
```

### Other Special Variables

```bash
# Current shell options
psh$ echo $-
sBH

# Shell version variable
psh$ echo $PSH_VERSION
0.x.y    # The current PSH version

# IFS (Internal Field Separator)
# The default IFS splits on spaces, tabs, and newlines
psh$ var="a b c"
psh$ for w in $var; do echo "[$w]"; done
[a]
[b]
[c]

# Change IFS for custom parsing
psh$ IFS=:
psh$ echo "root:x:0:0" | { read -r user pass uid gid; echo "User: $user, UID: $uid"; }
User: root, UID: 0
psh$ IFS=$' \t\n'  # Reset to default
```

## 5.4 Variable Expansion

### Basic Expansion

```bash
# Simple expansion
psh$ var="hello"
psh$ echo $var
hello

# Braces for clarity
psh$ echo ${var}
hello

# Braces required for disambiguation
psh$ prefix="pre"
psh$ echo "$prefix_fix"      # Looking for prefix_fix variable

psh$ echo "${prefix}_fix"    # Correct
pre_fix

# Concatenation
psh$ file="document"
psh$ echo "${file}.txt"
document.txt

# In strings
psh$ name="Alice"
psh$ echo "Hello, $name! Welcome to ${name}'s profile."
Hello, Alice! Welcome to Alice's profile.
```

### Default Values

```bash
# Use default if variable is unset or empty
psh$ echo ${username:-guest}
guest

psh$ username="alice"
psh$ echo ${username:-guest}
alice

# Set and use default if unset
psh$ echo ${config:=/etc/myapp.conf}
/etc/myapp.conf
psh$ echo $config
/etc/myapp.conf

# Display error if unset
psh$ echo ${required:?Error: required variable not set}
psh: required: Error: required variable not set

# Use alternate value if set
psh$ var="set"
psh$ echo ${var:+exists}
exists
psh$ echo ${unset:+exists}

```

### Indirect Expansion

Indirect variable expansion (`${!varname}`) expands to the value of the variable whose name is stored in `varname`:

```bash
psh$ red="FF0000"
psh$ varname="red"
psh$ echo ${!varname}
FF0000
```

## 5.5 Advanced Parameter Expansion

PSH supports most bash parameter expansion features:

### String Length

```bash
# Length of string
psh$ str="Hello, World!"
psh$ echo ${#str}
13

# Length of array elements
psh$ set -- one two three
psh$ echo ${#@}
3
psh$ echo ${#*}
3

# Length of specific positional parameter
psh$ echo ${#1}
3
psh$ echo ${#2}
3
```

### Pattern Removal

```bash
# Remove from beginning (# for shortest, ## for longest)
psh$ file="/home/alice/documents/report.txt"

psh$ echo ${file#*/}      # Remove shortest match from start
home/alice/documents/report.txt

psh$ echo ${file##*/}     # Remove longest match from start
report.txt

# Remove from end (% for shortest, %% for longest)
psh$ echo ${file%/*}      # Remove shortest match from end
/home/alice/documents

psh$ echo ${file%%/*}     # Remove longest match from end
(empty - removed everything)

# Practical examples
psh$ filename="archive.tar.gz"
psh$ echo ${filename%.gz}      # Remove .gz
archive.tar
psh$ echo ${filename%%.*}      # Remove all extensions
archive

# Remove path to get basename
psh$ path="/usr/local/bin/script.sh"
psh$ echo ${path##*/}
script.sh

# Remove filename to get directory
psh$ echo ${path%/*}
/usr/local/bin
```

### Pattern Substitution

```bash
# Replace first occurrence
psh$ text="hello hello world"
psh$ echo ${text/hello/hi}
hi hello world

# Replace all occurrences
psh$ echo ${text//hello/hi}
hi hi world

# Replace at beginning
psh$ echo ${text/#hello/hi}
hi hello world

# Replace at end
psh$ file="document.txt"
psh$ echo ${file/%txt/pdf}
document.pdf

# Delete pattern (replace with nothing)
psh$ spaces="hello   world   test"
psh$ echo ${spaces// /}
helloworldtest

# Case conversion in replacement
psh$ name="alice"
psh$ echo ${name/a/A}      # First 'a' to 'A'
Alice
psh$ echo ${name//a/A}     # All 'a' to 'A'
Alice
```

### Substring Extraction

```bash
# Extract substring ${var:offset:length}
psh$ str="Hello, World!"
psh$ echo ${str:0:5}
Hello
psh$ echo ${str:7:5}
World
psh$ echo ${str:7}        # From offset to end
World!

# Negative offsets (from end)
psh$ echo ${str: -6}      # Last 6 characters (note space)
World!
psh$ echo ${str: -6:5}    # 5 chars starting 6 from end
World
```

> **Note:** Slicing also works on positional parameters: `${@:offset:length}` selects a range of arguments rather than characters (e.g., `set -- a b c d; echo "${@:2:2}"` prints `b c`). Array slicing (`${array[@]:offset:length}`) behaves the same way.

### Case Modification

```bash
# Convert to uppercase
psh$ name="alice smith"
psh$ echo ${name^}        # First character
Alice smith
psh$ echo ${name^^}       # All characters
ALICE SMITH

# Convert to lowercase
psh$ NAME="ALICE SMITH"
psh$ echo ${NAME,}        # First character
aLICE SMITH
psh$ echo ${NAME,,}       # All characters
alice smith

# Pattern-based case conversion
psh$ text="hello world"
psh$ echo ${text^^[aeiou]}    # Uppercase vowels
hEllO wOrld

psh$ TEXT="HELLO WORLD"
psh$ echo ${TEXT,,[AEIOU]}    # Lowercase vowels
HeLLo WoRLD

# Capitalize each word
psh$ words="the quick brown fox"
psh$ echo ${words^}           # Just first char
The quick brown fox

# To capitalize each word, use a loop
psh$ result=""
psh$ for word in $words; do
>     result="$result${word^} "
> done
psh$ echo "$result"
The Quick Brown Fox 
```

### Variable Name Matching

Variable name prefix matching (`${!prefix*}` and `${!prefix@}`) expands to the names of all variables that begin with `prefix`:

```bash
psh$ USER_NAME=Alice
psh$ USER_AGE=25
psh$ USER_CITY=NYC
psh$ echo "${!USER_*}"
USER_AGE USER_CITY USER_NAME
```

> **Note:** As in bash, the quoted `"${!prefix@}"` form expands to one word per variable name (safe for `for` iteration), while `"${!prefix*}"` joins the names into a single IFS-separated word.

## 5.6 Local Variables in Functions

Local variables provide scope isolation within functions:

```bash
# Global vs local variables
psh$ counter=100

psh$ increment() {
>     local counter=0
>     counter=$((counter + 1))
>     echo "Local counter: $counter"
> }

psh$ increment
Local counter: 1
psh$ echo "Global counter: $counter"
Global counter: 100

# Local with initial value
psh$ process_file() {
>     local file="$1"
>     local -r max_size=1048576  # readonly local
>     local count=0
>     
>     echo "Processing $file (max size: $max_size)"
>     # ... processing logic ...
> }

# Locals are visible to nested functions
psh$ outer() {
>     local outer_var="outer"
>     
>     inner() {
>         echo "Inner sees: $outer_var"
>         local inner_var="inner"
>     }
>     
>     inner
>     echo "Outer cannot see: $inner_var"
> }

psh$ outer
Inner sees: outer
Outer cannot see: 

# Best practice: Always use local in functions
psh$ safe_function() {
>     local temp_file="/tmp/$$_temp"
>     local exit_code=0
>     local line
>     
>     while read -r line; do
>         echo "Processing: $line"
>     done < input.txt
>     
>     return $exit_code
> }
```

## Practical Examples

### Configuration File Parser

```bash
#!/usr/bin/env psh
# Parse a simple key=value configuration file

# Default configuration
DEFAULT_HOST="localhost"
DEFAULT_PORT="8080"
DEFAULT_DEBUG="false"

# Parse config file
parse_config() {
    local config_file="${1:-config.ini}"

    if [ ! -f "$config_file" ]; then
        echo "Warning: Config file not found, using defaults"
        return 1
    fi

    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        case "$key" in
            \#*|"") continue ;;
        esac

        # Set variables
        if [ -n "$key" ] && [ -n "$value" ]; then
            declare -g "$key=$value"
        fi
    done < "$config_file"
}

# Example config file:
# host=192.168.1.100
# port=9090
# debug=true

# Usage
parse_config "config.ini"

# Access configuration with defaults
HOST="${host:-$DEFAULT_HOST}"
PORT="${port:-$DEFAULT_PORT}"
DEBUG="${debug:-$DEFAULT_DEBUG}"

echo "Starting server on $HOST:$PORT (debug=$DEBUG)"
```

### Dynamic Variable Generator

```bash
#!/usr/bin/env psh
# Generate variables dynamically

# Create numbered variables
create_items() {
    local count="$1"
    local prefix="${2:-item}"
    local i

    for ((i=1; i<=count; i++)); do
        declare -g "${prefix}_${i}=Value $i"
        declare -g "${prefix}_${i}_status=pending"
    done
}

# Example usage
create_items 3 "task"

# Access generated variables directly
echo "task_1 = $task_1"
echo "task_2 = $task_2"
echo "task_3 = $task_3"
echo "task_1_status = $task_1_status"

# List variables with a prefix using set and grep
echo
echo "All task_ variables:"
set | grep '^task_'
```

### String Manipulation Utilities

```bash
#!/usr/bin/env psh
# Collection of string manipulation functions

# Trim whitespace (using sed since nested pattern expansion
# with character classes is not fully supported in PSH)
trim() {
    echo "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

# Join array elements
join() {
    local delimiter="$1"
    shift
    local first="$1"
    shift
    echo -n "$first"
    for item in "$@"; do
        echo -n "${delimiter}${item}"
    done
    echo
}

# Split string into array
split() {
    local string="$1"
    local delimiter="$2"
    local saved_ifs="$IFS"
    IFS="$delimiter"
    read -ra SPLIT_RESULT <<< "$string"
    IFS="$saved_ifs"
}

# URL encode
urlencode() {
    local string="$1"
    local length="${#string}"
    local encoded=""
    local i c

    for ((i=0; i<length; i++)); do
        c="${string:i:1}"
        case "$c" in
            [a-zA-Z0-9.~_-]) encoded="${encoded}${c}" ;;
            *) encoded="${encoded}$(printf '%%%02X' "'$c")" ;;
        esac
    done
    echo "$encoded"
}

# Examples
psh$ text="  hello world  "
psh$ trimmed=$(trim "$text")
psh$ echo "[$trimmed]"
[hello world]

psh$ join ":" apple banana cherry
apple:banana:cherry

psh$ split "one,two,three" ","
psh$ echo "${SPLIT_RESULT[@]}"
one two three

psh$ url=$(urlencode "hello world?foo=bar")
psh$ echo "$url"
hello%20world%3Ffoo%3Dbar
```

## 5.7 Array Variables

PSH supports indexed arrays with full bash-compatible syntax. Arrays provide a way to store multiple values in a single variable.

### Creating Arrays

```bash
# Array initialization with list
psh$ fruits=(apple banana cherry)
psh$ echo ${fruits[0]}
apple

# Declare an array explicitly
psh$ declare -a colors
psh$ colors=(red green blue)

# Assign individual elements
psh$ animals[0]="cat"
psh$ animals[1]="dog"
psh$ animals[5]="bird"  # Sparse arrays are supported

# Array from command substitution
psh$ files=($(ls *.txt))

# Array from glob expansion
psh$ images=(*.jpg *.png)
```

### Accessing Array Elements

```bash
# Access by index
psh$ echo ${fruits[0]}
apple
psh$ echo ${fruits[1]}
banana

# Negative indices (from end)
psh$ echo ${fruits[-1]}
cherry
psh$ echo ${fruits[-2]}
banana

# Using variables as indices
psh$ i=2
psh$ echo ${fruits[$i]}
cherry

# Arithmetic in indices
psh$ echo ${fruits[$((i-1))]}
banana
```

### Array Expansions

```bash
# All elements as separate words
psh$ echo ${fruits[@]}
apple banana cherry

# All elements as single word (with IFS)
psh$ echo ${fruits[*]}
apple banana cherry

# Number of elements
psh$ echo ${#fruits[@]}
3

# Length of specific element
psh$ echo ${#fruits[0]}
5

# All defined indices (useful for sparse arrays)
psh$ animals[0]="cat"
psh$ animals[5]="bird"
psh$ echo ${!animals[@]}
0 5

# Array slice (offset:length)
psh$ echo ${fruits[@]:1:2}
banana cherry

# Negative offset (note the space before -2)
psh$ echo ${fruits[@]: -2:2}
cherry date
```

### Modifying Arrays

```bash
# Append to array
psh$ fruits+=(orange grape)
psh$ echo ${fruits[@]}
apple banana cherry orange grape

# Append to element
psh$ fruits[0]+=" pie"
psh$ echo ${fruits[0]}
apple pie

# Replace element
psh$ fruits[1]="mango"

# Unset element (creates gap)
psh$ unset fruits[2]
psh$ echo ${fruits[@]}
apple pie mango orange grape

# Unset entire array
psh$ unset fruits
```

### Array Parameter Expansion

Many parameter expansion features work with array elements:

```bash
# Pattern substitution on all elements
psh$ files=(document.txt image.txt data.txt)
psh$ echo ${files[@]/.txt/.bak}
document.bak image.bak data.bak

# Case modification on all elements
psh$ names=(alice bob charlie)
psh$ echo ${names[@]^}
Alice Bob Charlie

# Length of each element
psh$ for file in "${files[@]}"; do
>     echo "$file: ${#file} chars"
> done
```

Pattern removal (`#`, `##`, `%`, `%%`) also applies to every element with the `[@]` form:

```bash
psh$ paths=(/home/user/file1 /home/user/file2)
psh$ echo "${paths[@]##*/}"
file1 file2
psh$ echo "${files[@]%.txt}"
document image data
```

### Practical Array Examples

```bash
#!/usr/bin/env psh
# Array manipulation examples

# Process command line arguments
process_args() {
    local args=("$@")
    local i
    
    echo "Got ${#args[@]} arguments:"
    for ((i=0; i<${#args[@]}; i++)); do
        echo "  [$i] = ${args[i]}"
    done
}

# Build command dynamically
build_command() {
    local cmd=()
    cmd+=(rsync)
    cmd+=(-avz)
    
    if [ "$VERBOSE" = "true" ]; then
        cmd+=(--verbose)
    fi
    
    cmd+=("$1" "$2")
    
    # Execute the command
    "${cmd[@]}"
}

# Parse CSV line into array
parse_csv() {
    local line="$1"
    local oldIFS="$IFS"
    IFS=','
    local fields=($line)
    IFS="$oldIFS"
    
    echo "Found ${#fields[@]} fields:"
    local i
    for ((i=0; i<${#fields[@]}; i++)); do
        echo "  Field $i: ${fields[i]}"
    done
}

# Find and process files
process_files() {
    local pattern="$1"
    local files=()
    
    # Collect matching files
    while IFS= read -r file; do
        files+=("$file")
    done < <(find . -name "$pattern" -type f)
    
    echo "Found ${#files[@]} files matching $pattern"
    
    # Process in batches
    local batch_size=10
    local i
    for ((i=0; i<${#files[@]}; i+=batch_size)); do
        echo "Processing batch starting at $i..."
        process_batch "${files[@]:i:batch_size}"
    done
}

# Menu system using arrays
show_menu() {
    local title="$1"
    shift
    local options=("$@")
    local choice
    
    echo "$title"
    echo
    
    local i
    for ((i=0; i<${#options[@]}; i++)); do
        echo "  $((i+1))) ${options[i]}"
    done
    echo
    
    read -p "Select option (1-${#options[@]}): " choice
    
    if ((choice > 0 && choice <= ${#options[@]})); then
        echo "You selected: ${options[$((choice-1))]}"
        return $((choice-1))
    else
        echo "Invalid selection"
        return 255
    fi
}

# Example usage
psh$ menu_items=(
>     "Start service"
>     "Stop service"
>     "View logs"
>     "Exit"
> )
psh$ show_menu "Service Manager" "${menu_items[@]}"
```

### Array Best Practices

1. **Always quote array expansions** to preserve elements with spaces:
   ```bash
   # Good
   for item in "${array[@]}"; do
   
   # Bad - splits elements with spaces
   for item in ${array[@]}; do
   ```

2. **Use declare -a** for clarity when creating arrays:
   ```bash
   declare -a my_array
   ```

3. **Check if index exists** in sparse arrays:
   ```bash
   if [[ -n "${array[5]+set}" ]]; then
       echo "Index 5 exists"
   fi
   ```

4. **Copy arrays** properly:
   ```bash
   # Good - preserves all elements
   new_array=("${old_array[@]}")
   
   # Bad - creates single element
   new_array="${old_array[@]}"
   ```

## 5.8 Associative Arrays

PSH supports associative arrays (also called hash tables or dictionaries) that use string keys instead of numeric indices. Associative arrays must be explicitly declared with `declare -A`.

### Creating Associative Arrays

```bash
# Declare an associative array
psh$ declare -A colors
psh$ echo "Created associative array 'colors'"
Created associative array 'colors'

# Assign values using string keys
psh$ colors[red]="#FF0000"
psh$ colors[green]="#00FF00"
psh$ colors[blue]="#0000FF"

# Keys can contain spaces (use quotes)
psh$ colors["light blue"]="#ADD8E6"
psh$ colors['dark red']="#8B0000"

# Initialization with declare
psh$ declare -A fruits=([apple]="red" [banana]="yellow" [grape]="purple")
```

### Accessing Associative Array Elements

```bash
# Access by key
psh$ echo ${colors[red]}
#FF0000

psh$ echo ${colors["light blue"]}
#ADD8E6

# Using variables as keys
psh$ key="green"
psh$ echo ${colors[$key]}
#00FF00

# Complex key expressions
psh$ prefix="light"
psh$ suffix="blue"
psh$ echo ${colors["${prefix} ${suffix}"]}
#ADD8E6
```

### Associative Array Expansions

```bash
# All values
psh$ echo ${colors[@]}
#FF0000 #00FF00 #0000FF #ADD8E6 #8B0000

# All keys
psh$ echo ${!colors[@]}
red green blue light blue dark red

# Number of elements
psh$ echo ${#colors[@]}
5

# Check if key exists
psh$ if [[ -v colors[red] ]]; then
>     echo "Key 'red' exists"
> fi
Key 'red' exists

# Alternative existence check
psh$ if [[ -n "${colors[red]+set}" ]]; then
>     echo "Key 'red' exists"
> fi
Key 'red' exists
```

### Modifying Associative Arrays

```bash
# Update existing key
psh$ colors[red]="#CC0000"
psh$ echo ${colors[red]}
#CC0000

# Append to value (using +=)
psh$ colors[note]="RGB"
psh$ colors[note]+=" color"
psh$ echo ${colors[note]}
RGB color

# Remove a key
psh$ unset colors["light blue"]
psh$ echo ${!colors[@]}
red green blue dark red note

# Clear all elements
psh$ unset colors
```

### Key Differences from Indexed Arrays

```bash
# Associative arrays require declare -A
psh$ declare -A assoc
psh$ assoc[key]="value"     # Works

# Regular arrays auto-create
psh$ indexed[0]="value"     # Works without declare

# Keys are treated as strings in associative arrays
psh$ declare -A calc
psh$ calc[2+2]="not four"   # Key is literally "2+2"
psh$ echo ${calc[2+2]}
not four

# vs indexed arrays where expressions are evaluated
psh$ indexed[2+2]="four"    # Index is calculated as 4
psh$ echo ${indexed[4]}
four
```

### Practical Examples

```bash
#!/usr/bin/env psh
# Configuration management using associative arrays

# Server configuration (single-line initialization)
declare -A config=([hostname]="web01.example.com" [port]="8080" [ssl_enabled]="true")

# Print configuration
print_config() {
    echo "Server Configuration:"
    for key in "${!config[@]}"; do
        printf "  %-15s: %s\n" "$key" "${config[$key]}"
    done
}

# User database simulation
declare -A users
users[alice]="alice@example.com:admin"
users[bob]="bob@example.com:user"
users[charlie]="charlie@example.com:user"

# Look up user
lookup_user() {
    local username="$1"
    if [[ -v users[$username] ]]; then
        IFS=':' read -r email role <<< "${users[$username]}"
        echo "User: $username"
        echo "Email: $email"
        echo "Role: $role"
    else
        echo "User not found: $username"
        return 1
    fi
}

# File type mapping
declare -A extensions
extensions[txt]="Text file"
extensions[jpg]="JPEG image"
extensions[pdf]="PDF document"

# Classify files
classify_file() {
    local filename="$1"
    local ext="${filename##*.}"  # Get extension
    local description="${extensions[$ext]:-Unknown file type}"

    echo "$filename: $description"
}

# Example usage
psh$ print_config
psh$ lookup_user alice
psh$ classify_file document.pdf
```

> **Note:** Multi-line compound initialization (`declare -A hash=(\n[key1]="val1"\n[key2]="val2"\n)`) is not supported in PSH. Use single-line compound initialization or assign elements individually instead.

### Best Practices for Associative Arrays

1. **Always use declare -A** before assignment:
   ```bash
   # Required for associative arrays
   declare -A my_hash
   my_hash[key]="value"
   ```

2. **Quote keys with special characters**:
   ```bash
   hash["key with spaces"]="value"
   hash["key/with/slashes"]="value"
   ```

3. **Use meaningful key names**:
   ```bash
   # Good
   user_info[email]="user@example.com"
   user_info[role]="admin"
   
   # Less clear
   user_info[0]="user@example.com"
   user_info[1]="admin"
   ```

4. **Check key existence before access**:
   ```bash
   if [[ -v config[database_url] ]]; then
       db_url="${config[database_url]}"
   else
       db_url="localhost:5432"
   fi
   ```

5. **Iterate over keys or values appropriately**:
   ```bash
   # Process all key-value pairs
   for key in "${!config[@]}"; do
       echo "$key = ${config[$key]}"
   done
   
   # Process all values
   for value in "${config[@]}"; do
       echo "Value: $value"
   done
   ```

### Associative Arrays vs Regular Variables

| Feature | Regular Variables | Associative Arrays |
|---------|------------------|-------------------|
| Storage | Single value | Multiple key-value pairs |
| Access | `$var` | `${array[key]}` |
| Declaration | Optional | Required (`declare -A`) |
| Keys | N/A | String-based |
| Iteration | N/A | Over keys or values |
| Use Case | Simple values | Structured data |

## Summary

Variables and parameters in PSH provide powerful ways to store and manipulate data:

1. **Basic variables** store values with simple assignment
2. **Environment variables** pass data to child processes
3. **Special variables** provide system and process information
4. **Parameter expansion** enables default values and string manipulation
5. **Advanced expansion** supports pattern matching, substitution, and case conversion
6. **Local variables** provide function scope isolation
7. **Array variables** store multiple values with indexed access and powerful expansions
8. **Associative arrays** provide key-value storage for structured data

Understanding these features is essential for effective shell scripting. Variables are the foundation for storing state, passing data between commands, and building complex scripts.

In the next chapter, we'll explore the various expansion mechanisms that make shell scripting so powerful.

---

[← Previous: Chapter 4 - Built-in Commands](04_builtin_commands.md) | [Next: Chapter 6 - Expansions →](06_expansions.md)