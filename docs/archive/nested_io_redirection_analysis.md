# Nested I/O Redirection Analysis

This document analyzes the xfail tests in `tests/integration/control_flow/test_nested_structures_io_conservative.py` and identifies fixes needed for I/O redirection in nested control structures.

## Summary

8 tests are marked as xfail, all related to I/O redirection in nested control structures:

## Core Issue: Variable Expansion in Redirect Targets

### Root Cause
The primary issue is that **redirect targets are not being expanded for variables**. When a command like:
```bash
echo "Hello" > "item_${i}.txt"
```
is executed, the file created is literally named `item_${i}.txt` instead of `item_1.txt` or `item_2.txt`.

### Current Behavior
- Only tilde expansion (`~`) is performed on redirect targets
- Variable expansion (`$var`, `${var}`) is NOT performed
- This affects all redirect types: `>`, `>>`, `<`

### Code Location
In `/Users/pwilson/src/psh/psh/io_redirect/file_redirect.py`:
```python
# Line 41 - Only tilde expansion is done
if target and redirect.type in ('<', '>', '>>') and target.startswith('~'):
    target = self.shell.expansion_manager.expand_tilde(target)
```

## Affected Tests

### 1. Simple Output Redirection in Loops
```bash
for i in 1 2; do
    echo "Item $i" > "item_${i}.txt"
done
```
**Issue**: Creates file `item_${i}.txt` instead of `item_1.txt` and `item_2.txt`

### 2. Complex Nested Redirection
```bash
for outer in 1 2; do
    for inner in a b; do
        echo "${outer}-${inner}"
    done > "output${outer}.txt"
done
```
**Issue**: Creates file `output${outer}.txt` instead of `output1.txt` and `output2.txt`

### 3. Function Output Redirection
```bash
generate_data() {
    echo "Data for: $1"
    echo "Value: $2"
}

for item in item1 item2; do
    generate_data "test" "$item" > "${item}_data.txt"
done
```
**Issue**: Creates file `${item}_data.txt` instead of `item1_data.txt` and `item2_data.txt`

### 4. Heredoc in Case Statements
```bash
case "$section" in
    header)
        cat > "${section}.txt" << 'EOF'
This is the header.
EOF
        ;;
esac
```
**Issue**: May have issues with heredoc handling in case statements

### 5. While Read with Pipes
```bash
echo -e "line1\nline2\nline3" | while read line; do
    case "$line" in
        line1)
            echo "First: $line" > first.txt
            ;;
    esac
done
```
**Issue**: Complex pipeline processing limitations

### 6. Error Handling with Redirection
```bash
if echo "test" > "$operation" 2>/dev/null; then
    success_count=$((success_count + 1))
fi
```
**Issue**: Error handling when redirection fails

### 7-8. Complex Nested Structures
Two tests check that basic functionality still works after complex nested structures with redirections.

## Recommended Fix

### Solution: Add Variable Expansion to Redirect Targets

The fix needs to be implemented in multiple places:

1. **In `file_redirect.py`** - Add variable expansion for all file redirect targets:
```python
# Expand variables in target for file redirections
if target and redirect.type in ('<', '>', '>>'):
    # First expand tilde
    if target.startswith('~'):
        target = self.shell.expansion_manager.expand_tilde(target)
    # Then expand variables
    target = self.shell.expansion_manager.expand_string_variables(target)
```

2. **In `io_manager.py`** - Similar fix for builtin redirections

3. **Consider Quote Context** - Need to respect quoting:
   - `> "$file"` - expand variables but not globs
   - `> $file` - expand variables and globs
   - `> '$file'` - no expansion

### Alternative Approach: Expand During Parsing

Another approach would be to expand redirect targets during command execution, before passing to the I/O manager. This could be done in the command executor.

## Priority

**High Priority** - This is a fundamental shell feature that affects:
- Script portability
- Common shell patterns (loops with file output)
- POSIX compliance

## Implementation Complexity

**Medium** - The fix is straightforward but needs to be applied consistently:
- Multiple locations need updating
- Need to handle quoting correctly
- Test coverage is already good (8 xfail tests)

## Related Issues

- This is separate from the alias expansion issue
- May interact with process substitution handling
- Need to ensure proper expansion order is maintained