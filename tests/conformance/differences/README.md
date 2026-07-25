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
- `help`: Context-aware help system. NOTE: psh has no `--help` OPTION on
  builtins — `--` reads as an invalid option (stderr, exit 2) where bash
  prints full help to stdout. That divergence is catalogued as
  `BUILTIN_LONG_HELP_OPTION`. (A `HELP_BUILTIN` entry describing the help
  builtin's output format was deleted in slot 1.3: real, but claimed nowhere
  in the user guide and referenced by no test.)

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
- Implemented, and **behaviorally identical to bash** — asserted by
  `test_bash_compatibility.py::TestDocumentedDifferences::test_directory_stack` and claimed as "Full
  support" in user guide ch17. Verified byte-for-byte from a shared working
  directory for `pushd`, `popd`, and `pushd /tmp`.
- The catalog formerly held three entries asserting a difference here
  (`PUSHD_BEHAVIOR`, `POPD_BEHAVIOR`, `PUSHD_CWD_DIFFERENCE`). All three were
  referenced by ZERO tests and were CONTRADICTED by the passing conformance
  test above; `PUSHD_CWD_DIFFERENCE` documented a harness artifact (psh and
  bash having been run from different working directories) as a shell
  difference. All three were deleted in slot 1.3.

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

1. **Update the JSON catalog** (`psh_bash_differences.json`) — every entry
   under `documented` MUST carry an `expected` block (see below)
2. **Document the difference** in this README
3. **Add conformance tests** to verify the behavior — every entry must be
   referenced by at least one test
4. **Categorize appropriately** (extension, limitation, etc.)

### The mandatory `expected` block

Classification is BEHAVIOR-AWARE. `_is_documented_difference` validates the
OBSERVED divergence against the entry's expected shape before returning
`DOCUMENTED_DIFFERENCE`; catalog membership is necessary but **not
sufficient**, and an entry with no `expected` block cannot classify at all.

Before this existed, matching was `command in catalog` with both results
unused, so a forged psh stdout for a catalogued command still classified as
documented — those pins could not fail for the right reason.

```json
"echo $$": {
  "id": "PROCESS_ID_DIFFERENCE",
  "description": "...",
  "expected": {
    "psh":  {"exit_code": 0, "stdout_pattern": "^\\d+\\n$", "stderr_pattern": "^$"},
    "bash": {"exit_code": 0, "stdout_pattern": "^\\d+\\n$", "stderr_pattern": "^$"},
    "note": "Both print their OWN pid: same shape, different value."
  }
}
```

`exit_code` is exact; `stdout_pattern`/`stderr_pattern` are regex SEARCHES, so
pin a whole stream with `^...$` or just the identifying fragment. An omitted
key is not checked. Write the shape so that a REGRESSION stops matching — that
is the alarm the block exists to raise.

Both invariants are enforced by
[`../test_documented_difference_shape.py`](../test_documented_difference_shape.py):
`test_every_documented_entry_carries_an_expected_shape` and
`test_no_documented_entry_is_dead_inventory`.

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