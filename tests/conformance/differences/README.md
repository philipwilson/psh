# PSH vs Bash Differences Documentation

This directory contains documentation of differences between PSH and bash behavior, categorized by type and impact.

## Difference Categories

### 1. PSH Extensions
Features that PSH provides but bash doesn't (or implements differently).

#### Educational/Debug Features
- `--debug-ast`: Show AST structure before execution
- `--debug-tokens`: Show tokenization output  
- `--debug-expansion`: Trace variable/command expansion
- `--validate`: Parse and validate without executing

#### Enhanced Builtins
- `version`: Show PSH version information
- `help`: Context-aware help system

### 2. Major Bash Features PSH Supports
This doc formerly listed the features below as "not implemented." That was
badly stale: **every item here is implemented and covered by conformance
tests.** They are called out explicitly so migrating users and reviewers
know PSH has them (see the mapped conformance files for the proving tests).

#### Advanced Conditionals
- `[[ ]]`: extended test construct — `[[ "hello" == hel* ]]`
- `(( ))`: arithmetic evaluation construct — `(( x++ ))`, `(( 3 > 2 ))`

#### Arrays
- `declare -a`: indexed array declaration
- `declare -A`: associative array declaration
- `${array[@]}` / `${array[*]}`: array expansion
- `${#array[@]}`: array length; `${!array[@]}`: index/key list

#### Advanced Parameter Expansion
- `${var^}`, `${var^^}`, `${var,}`, `${var,,}`: case conversion
- `${var/pattern/replacement}`, `${var//pattern/replacement}`: pattern substitution
- `${var@P}`, `${var@Q}`, `${var@K}`/`${var@k}` and friends: `@`-operator transforms

#### Process Substitution
- `<(command)`: process substitution input
- `>(command)`: process substitution output

#### Extended Globbing (`shopt -s extglob`)
- `?(pattern)`, `+(pattern)`, `*(pattern)`, `@(pattern)`, `!(pattern)` — in
  pathname expansion, `case` patterns, `[[ ]]` matches, and parameter-expansion
  patterns. As in bash, `shopt -s extglob` must take effect **before** the line
  using the syntax is parsed (bash rejects `shopt -s extglob; case x in @(a));;`
  on a single `-c` line for the same reason).

#### Bash Builtins
- `declare` / `typeset`: variable declaration with attributes
- `local`: function-local variables
- `mapfile` / `readarray`: read lines into an array
- `shopt`: shell option setting

### 3. Bash Features PSH Does NOT Implement
Features bash provides that PSH genuinely lacks. The **authoritative,
continuously-verified ledger** is
[`tests/conformance/bash/test_absent_features.py`](../bash/test_absent_features.py):
each entry is a `strict-xfail` that turns the suite RED the moment PSH
implements the feature, so this list cannot silently rot.

#### Unimplemented builtins (report "command not found")
- `bind`: readline key-binding builtin
- `compgen` / `complete`: programmable-completion builtins
- `caller`: print the call site of the current function
- `enable`: enable/disable shell builtins
- `suspend`: suspend the shell

#### Job control / process features
- `coproc`: co-processes
- `wait -f`: wait until a job fully terminates
- `jobs -x`: replace jobspecs with PGIDs in a command's arguments
- `shopt -s lastpipe`: run the last pipeline element in the current shell
  (rejected honestly as "invalid shell option name")

### 4. Documented Behavioral Differences
Areas where PSH and bash both support a feature but with different behavior.

#### History Expansion
- History expansion **is** implemented: event designators (`!!`, `!n`,
  `!string`, `!?string?`), word designators, `:h`/`:t`/`:r`/`:e`/`:s`/`:g&`
  modifiers, and `^old^new` quick substitution. Like bash, it is
  **interactive-only** — both shells disable it for non-interactive `-c`
  strings and scripts (proving coverage:
  [`tests/conformance/bash/test_history_expansion_conformance.py`](../bash/test_history_expansion_conformance.py)).
- Divergence: PSH toggles history expansion via the `histexpand` shell option
  (`H` in `$-`), but **does not accept `set -H` / `set +H`** as a way to flip
  it (`set -H` reports "invalid option"). bash accepts both.
- Multi-key associative-array iteration order is PSH insertion order vs bash's
  internal hash order (a PSH-wide associative property, not an absent feature).

#### Directory Stack (pushd/popd/dirs)
- Implemented; output format and some error messages may differ in wording
  from bash.

#### Signal Handling
- Some signal behavior is platform-specific: real-time signals
  (`SIGRTMIN+n`) exist on Linux but not macOS, and a few signal-name aliases
  (`SIGCHLD`/`SIGCLD`) vary by platform. Trap semantics otherwise match bash.

## Testing Strategy

### Conformance Tests
1. **POSIX Compliance**: Test features required by POSIX
2. **Bash Compatibility**: Test bash-specific features
3. **Difference Documentation**: Catalog and test known differences

### Test Categories
- **Identical**: PSH and bash produce identical results
- **Documented Difference**: Known and documented difference
- **PSH Extension**: PSH supports something bash doesn't  
- **Bash Specific**: Bash supports something PSH doesn't
- **PSH Bug**: Unexpected difference (potential bug)

### Usage in Tests
```python
# Test identical behavior
self.assert_identical_behavior('echo hello')

# Test documented difference
self.assert_documented_difference('version', 'VERSION_BUILTIN')

# Test PSH extension
self.assert_psh_extension('psh --debug-ast script.sh')

# Investigate difference
result = self.check_behavior('complex_command')
```

## Updating Documentation

When adding new tests or discovering differences:

1. **Update the JSON catalog** (`psh_bash_differences.json`)
2. **Document the difference** in this README
3. **Add conformance tests** to verify the behavior
4. **Categorize appropriately** (extension, limitation, etc.)

## Compliance Goals

### POSIX Compliance Target: >95%
PSH should support all required POSIX shell features with identical behavior to bash.

### Bash Compatibility Target: >80%
PSH should support common bash features while documenting intentional differences.

### Quality Targets
- Zero undocumented differences in core features
- All differences should be intentional design decisions
- Clear documentation for users migrating from bash

## References

- [POSIX Shell Standard](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html)
- [Bash Manual](https://www.gnu.org/software/bash/manual/bash.html)
- [PSH Architecture Documentation](../../../ARCHITECTURE.md)