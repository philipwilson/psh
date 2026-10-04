# psh domain glossary

Names for concepts the code relies on but had not named. Architecture
reviews and the engineering skills use these terms; the invariants themselves
live in the subsystem `CLAUDE.md` files.

- **Write door** — the one interface every whole-variable write crosses:
  `VariableStore.assign` (`psh/core/variable_store.py`). It owns write policy
  (today: the `set -a` decision) and routes to the write primitives. Many
  entrances (`ShellState.set_variable`, the declaration engine, the `local`
  builtin) but one door.
- **Write primitive** — a `ScopeManager` method that performs the actual
  `.value`/`.attributes` mutation for one write shape (`_set_variable`,
  `_create_local`). Private: only the write door calls it.
- **Target scope** — the door's one selector for where a write lands:
  `DYNAMIC` (plain assignment: innermost visible instance, else a new global),
  `DEFAULT` (a declaration's default: current scope in a function, global at
  top level), `LOCAL` (the `local` builtin), `GLOBAL` (`declare -g`).
- **Tombstone** — a declared-but-unset variable: a cell carrying the `UNSET`
  attribute that shadows outer instances, reads as unset, and keeps its other
  attributes (`local -u x`, `declare -i y`).
- **Dynamic special** — a computed variable with a lifecycle in the special
  registry (`RANDOM`, `SECONDS`, `LINENO`, ...): a whole-variable write seeds
  or is ignored by its policy, and `set -a` never exports it.
- **Temp-env layer** — the binding a `VAR=x cmd` prefix installs for one
  command: a temp-env *scope* below a function's own scope, or a
  `command_temp_env` layer over a builtin/external, visible to name lookup but
  not to whole-table enumeration.
