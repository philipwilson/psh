# PSH POSIX Compatibility Guide

This guide helps users understand PSH's POSIX compliance level and how to write portable shell scripts that work in both PSH and POSIX shells.

## Quick Reference

### POSIX Compliance Status

| Category | Compliance | Notes |
|----------|------------|-------|
| **Shell Grammar** | ✅ 95% | All major constructs supported |
| **Built-ins** | ⚠️ 75% | Missing: trap, shift, exec, wait, getopts |
| **Expansions** | ✅ 90% | Full POSIX expansion order |
| **Redirections** | ✅ 95% | Missing: `<>` (read-write) |
| **Exit Status** | ✅ 90% | Standard codes implemented |
| **Variables** | ✅ 85% | Missing: some `$-` flags |

**Overall POSIX Compliance: ~85%**

## Writing POSIX-Compatible Scripts in PSH

### Use POSIX-Compliant Features Only

```bash
#!/bin/sh
# Good - POSIX compliant shebang

# POSIX variable assignment
name="value"
readonly CONSTANT="immutable"

# POSIX parameter expansion
echo "${name:-default}"
echo "${path#*/}"
echo "${file%.txt}"

# POSIX command substitution
result=$(command)  # Good - POSIX
# result=`command` # Also POSIX but $() preferred

# POSIX arithmetic
count=$((count + 1))

# POSIX conditionals
if [ "$var" = "value" ]; then
    echo "Match"
fi

# POSIX loops
for file in *.txt; do
    echo "$file"
done

while read line; do
    echo "$line"
done < input.txt
```

### Avoid Non-POSIX Extensions

```bash
# BAD - Not POSIX compliant
array=(one two three)        # Arrays not in POSIX
[[ $var =~ regex ]]          # [[ ]] not in POSIX
for ((i=0; i<10; i++)); do  # C-style for not in POSIX
echo {1..10}                 # Brace expansion not in POSIX
result=$(<file)              # $(<) not in POSIX
local var="value"            # 'local' not in POSIX
```

### POSIX Alternatives for Common Patterns

#### Arrays → Use positional parameters or word lists
```bash
# Instead of: array=(one two three)
set -- one two three
echo "$1"  # First element
echo "$@"  # All elements
echo "$#"  # Count

# Or use a string with IFS
items="one:two:three"
IFS=:
for item in $items; do
    echo "$item"
done
```

#### Enhanced test [[ ]] → Use standard test [ ]
```bash
# Instead of: [[ $string =~ ^[0-9]+$ ]]
case "$string" in
    *[!0-9]*) echo "Not a number" ;;
    *) echo "Is a number" ;;
esac

# Instead of: [[ $a < $b ]]
[ "$(printf '%s\n' "$a" "$b" | sort | head -n1)" = "$a" ]
```

#### Local variables → Use functions with subshells
```bash
# Instead of: local var="value"
# Use a subshell to isolate variables
process_data() (  # Note: ( ) instead of { }
    var="local_value"
    echo "$var"
)
```

#### Brace expansion → Use loops or multiple commands
```bash
# Instead of: mkdir -p dir/{a,b,c}
for d in a b c; do
    mkdir -p "dir/$d"
done

# Instead of: cp file.{txt,bak}
cp file.txt file.bak
```

## Feature Compatibility Table

### Fully POSIX Compliant Features ✅

These features work identically in PSH and POSIX shells:

| Feature | Example | Notes |
|---------|---------|-------|
| Simple commands | `ls -l` | Full support |
| Pipelines | `cmd1 \| cmd2` | Full support |
| Redirections | `>`, `<`, `>>`, `2>` | Except `<>` |
| Here documents | `<< EOF` | Including `<<-` |
| Command substitution | `$(...)`, `` `...` `` | Both forms |
| Variable expansion | `$var`, `${var}` | All POSIX forms |
| Arithmetic expansion | `$((expr))` | Full operators |
| For loops | `for x in ...; do` | POSIX syntax |
| While loops | `while ...; do` | Full support |
| If statements | `if ...; then` | With elif/else |
| Case statements | `case ... in` | With patterns |
| Functions | `name() { ... }` | POSIX syntax |
| Standard test | `[ expr ]` | All POSIX operators |

### PSH Extensions (Not POSIX) ⚠️

These work in PSH but not in POSIX shells:

| Feature | PSH Syntax | POSIX Alternative |
|---------|------------|-------------------|
| Arrays | `arr=(a b c)` | Use `set --` |
| Associative arrays | `declare -A` | Use separate variables |
| Enhanced test | `[[ expr ]]` | Use `[ expr ]` |
| Local variables | `local var` | Use subshells |
| Brace expansion | `{1..10}` | Use loops |
| Process substitution | `<(cmd)` | Use temp files |
| C-style for | `for ((;;))` | Use while with counter |
| `+=` operator | `var+=text` | `var="${var}text"` |

### Missing POSIX Features ❌

These POSIX features are not yet implemented in PSH:

| Feature | POSIX Usage | Workaround |
|---------|-------------|------------|
| `trap` | `trap 'cleanup' EXIT` | Manual cleanup |
| `shift` | `shift 2` | Reassign positionals |
| `exec` | `exec > file` | Use redirections |
| `wait` | `wait $pid` | No good workaround |
| `getopts` | `getopts "ab:" opt` | Manual parsing |
| `command` | `command -v cmd` | Use `type` or `which` |
| `<>` redirect | `cmd <> file` | Use separate `<` and `>` |

## Best Practices for Portability

### 1. Test with POSIX Mode

```bash
# Test your script with a POSIX shell
dash script.sh
sh script.sh
bash --posix script.sh
```

### 2. Use Shellcheck

```bash
# Install shellcheck
brew install shellcheck  # macOS
apt-get install shellcheck  # Debian/Ubuntu

# Check for POSIX compliance
shellcheck -s sh script.sh
```

### 3. Avoid Bashisms

Common bashisms to avoid:
- `function` keyword (use `name()` instead)
- `source` (use `.` instead)
- `$RANDOM` (use `$(awk 'BEGIN{srand(); print int(rand()*32768)}')`)
- `$SECONDS` (use `date +%s` math)
- `${!var}` indirect expansion
- `${var^^}` case modification

### 4. Quote Variables

Always quote variables to prevent word splitting:
```bash
# Good
if [ "$var" = "value" ]; then
    cp "$source" "$dest"
fi

# Bad - can break with spaces
if [ $var = value ]; then
    cp $source $dest
fi
```

### 5. Check Exit Status Explicitly

```bash
if command; then
    echo "Success"
else
    echo "Failed with status $?"
fi
```

## Testing for POSIX Compliance

### Run the Compliance Checker

```bash
# Check PSH POSIX compliance
python scripts/check_posix_compliance.py

# Verbose output
python scripts/check_posix_compliance.py -v

# Save report
python scripts/check_posix_compliance.py -o posix_report.json
```

### Manual Testing

Test specific POSIX features:

```bash
# Test parameter expansion
psh -c 'x=/path/to/file.txt; echo ${x##*/}'
# Should output: file.txt

# Test command substitution
psh -c 'echo "Today is $(date +%A)"'

# Test exit status
psh -c 'false || echo "Failed with $?"'
# Should output: Failed with 1
```

## Migration Guide

### From Bash to POSIX in PSH

If you have bash scripts that you want to run in POSIX mode:

1. **Replace arrays with positional parameters**
   ```bash
   # Bash
   files=(*.txt)
   echo "${files[0]}"
   
   # POSIX
   set -- *.txt
   echo "$1"
   ```

2. **Replace [[ ]] with [ ] or case**
   ```bash
   # Bash
   if [[ $file == *.txt ]]; then
   
   # POSIX
   case "$file" in
       *.txt) ... ;;
   esac
   ```

3. **Replace local with function subshells**
   ```bash
   # Bash
   func() {
       local temp="$1"
   }
   
   # POSIX  
   func() (
       temp="$1"
   )
   ```

4. **Replace process substitution with temp files**
   ```bash
   # Bash
   diff <(sort file1) <(sort file2)
   
   # POSIX
   sort file1 > /tmp/sorted1
   sort file2 > /tmp/sorted2
   diff /tmp/sorted1 /tmp/sorted2
   rm /tmp/sorted1 /tmp/sorted2
   ```

## Future POSIX Mode

PSH may implement a strict POSIX mode in the future:

```bash
# Potential future feature
psh --posix script.sh
# or
set -o posix
```

This would:
- Disable all non-POSIX extensions
- Provide warnings for non-POSIX usage
- Ensure strict POSIX behavior
- Enable POSIX-only built-ins

## Resources

- [POSIX.1-2017 Specification](https://pubs.opengroup.org/onlinepubs/9699919799/)
- [Shellcheck](https://www.shellcheck.net/) - Online POSIX compliance checker
- [Dash Shell](http://gondor.apana.org.au/~herbert/dash/) - Reference POSIX shell
- [POSIX Shell Tutorial](https://www.grymoire.com/Unix/Sh.html)

## Contributing

To improve PSH's POSIX compliance:

1. Run the compliance test suite
2. Identify missing features
3. Implement POSIX-compliant behavior
4. Add tests to `tests/posix_compliance/`
5. Update this guide with changes

Priority areas for contribution:
- Implement `trap` command (high priority)
- Implement `shift` command (high priority)
- Implement `exec` command (medium priority)
- Add `getopts` built-in (medium priority)
- Complete `$-` special parameter (low priority)