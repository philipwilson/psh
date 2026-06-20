# Shell Options Typing / Consolidation Plan

Date: 2026-06-19

Related review item: `docs/reviews/code_architecture_teaching_quality_review_2026-06-18.md`,
priority #4: "Turn prose-only semantic contracts into explicit interfaces" —
specifically the sub-point that `ShellState.options` "remains a large string-keyed
policy surface," to be moved "into typed groups, following the pattern already used
for `ExecutionState`, `StreamBindings`, `TerminalState`, and `HistoryState`."

## TL;DR

The review's literal recommendation — make options "a typed group like
`ExecutionState`" (one clean attribute per field) — **does not fit**, and we should
say so explicitly. Shell options are an inherently *dynamic, string-keyed* surface:
`set -o $name`, `shopt $name`, and `$-` all operate on option **names as runtime
data**. You cannot replace `state.options[name]` with attribute access when `name`
is a variable, and several option names are not valid Python identifiers
(`debug-ast`, `strict-errors`, `parser-mode`).

The real, valuable win is the one underneath the review's wording: replace the
**bare untyped dict + metadata scattered across four files** with a **single option
registry** (the one source of truth for every option's default, value type, short
flag, and category) behind a **dict-compatible `ShellOptions` container**. This
gets the typing/validation/consolidation benefit at low blast radius, because the
~280 existing `state.options[...]` / `.options.get(...)` call sites keep working
unchanged.

## Current State (evidence)

### Scale

- `state.options` is a plain `dict` with **41 keys** (40 `bool`, 1 `str` —
  `parser-mode`), defined as a literal in `psh/core/state.py` (lines ~99–155).
- **~174** `.options` references in `psh/` and **~104** in `tests/`. Access shapes:
  111 `.options.get(`, 47 `.options[`, 2 `.options.update`, 4 `… in …options`,
  ~42 of the subscripts are writes. Concentrated in `core/state.py`,
  `builtins/parser_control.py`, `builtins/debug_control.py`,
  `builtins/environment.py`, plus the executor/expansion hot paths.
- **Conclusion:** any approach that rewrites every call site touches ~280 places.
  That is the cost to beat.

### Why the `ExecutionState` pattern does not transfer

`ExecutionState`/`StreamBindings`/`TerminalState`/`HistoryState` each lifted a few
fields with **fixed, clean names** read at a handful of sites, and `ShellState`
kept delegating properties (`state.last_exit_code`). Options differ on every axis:

1. **Dynamic name access.** `set`, `shopt`, and `$-` index options by a *runtime*
   name (`shell.state.options[short_to_long[opt_char]] = enable`). A per-field
   dataclass cannot serve `options[name]` for a variable `name`.
2. **Non-identifier names.** `debug-ast`, `debug-exec-fork`, `strict-errors`,
   `parser-mode` contain hyphens; `expand_aliases`, `collect_errors`, `stdin_mode`
   use underscores. A field-per-option dataclass needs a name-translation layer.
3. **Mixed value types.** 40 booleans plus `parser-mode: 'balanced'` (a string enum
   over performance/balanced/development).
4. **It is the user-facing surface.** Options are enumerated and round-tripped by
   `set -o`, `set +o`, and `shopt [-p]`; they are not internal scratch state.

### Metadata is scattered across four+ places

The single concept "what options exist and how each one behaves" is duplicated:

| Where | What it encodes |
|-------|-----------------|
| `core/state.py` dict literal | every option's existence + default value |
| `core/state.py` `get_option_string()` | the name→`$-` short-letter map (a-x, B/C/H), hard-coded again |
| `builtins/environment.py` `SetBuiltin.short_to_long` | the `set -e`/`-u`/… short→long map |
| `builtins/shell_options.py` `ShoptBuiltin.SHOPT_OPTIONS` | which options are shopt-managed and their keys |

Consequences observed:

- **`command_mode` is undeclared.** `__main__.py` does
  `shell.state.options['command_mode'] = True` for `-c`, and `get_option_string()`
  reads it, but it is absent from the initial dict. It works only because the dict
  is open. The "valid options" list that `set -o` prints is literally
  `state.options.keys()`, so it advertises whatever keys happen to exist.
- **Validation is data-driven off live keys, not a declared set.** `set -o badname`
  is correctly rejected today (matches bash, rc 2) — but because the check reads the
  current dict keys, a stray internal write (`options['typo'] = …`) would silently
  enlarge the "valid" set rather than fail.
- Adding/renaming an option means editing up to four places by hand with nothing
  enforcing they agree.

## Design Decision: facade + registry, NOT field-per-option

### Option 1 (recommended): dict-compatible `ShellOptions` over a registry

- A single `OPTION_REGISTRY`: `name -> OptionSpec(default, value_type, short_flag,
  category, in_dollar_dash)`. Every existing scattered map is *derived* from it.
- `ShellState.options` becomes a `ShellOptions` object that **still behaves like the
  dict** — implements `__getitem__`, `__setitem__`, `get`, `__contains__`,
  `__iter__`, `items`, `update`, `keys` — so the ~280 call sites are untouched.
- `__setitem__` validates against the registry (reject/または warn on unknown names
  — see Open Questions), giving the typed/validated surface the review asked for.
- Optional, additive: typed convenience accessors for the hottest internal reads
  (`options.errexit`, `options.nounset`) for readability — but NOT required, and not
  a reason to churn call sites.

Pros: typing + validation + single source of truth; ~0 call-site churn; keeps the
dynamic-by-name surface that `set`/`shopt`/`$-` genuinely need. Cons: `ShellOptions`
is a dict-like, not a flat dataclass, so the win is "validated registry-backed map,"
not "every option is an attribute."

### Option 2 (rejected): field-per-option dataclass + delegating properties

Mirror `ExecutionState` literally. Rejected because: it cannot serve dynamic
`options[name]`; it needs a hyphen↔underscore translation layer anyway; and it would
rewrite the dynamic builtins (`set`, `shopt`) into name→attribute reflection, which
is *less* clear than a registry lookup. High churn, lower clarity.

### Recommendation

Option 1. It is the honest reading of "make this a typed, explicit surface" for a
structure that is dynamic by nature. Record Option 2's rejection so the choice is
deliberate.

## Target Architecture

New `psh/core/option_registry.py` (name chosen to avoid colliding with the existing
`builtins/shell_options.py` shopt builtin):

```python
class OptionCategory(Enum):
    SET = auto()       # set -o / short flag (errexit, xtrace, ...)
    SHOPT = auto()     # shopt -s/-u (extglob, globstar, ...)
    DEBUG = auto()     # debug-ast, debug-tokens, ...
    INTERNAL = auto()  # interactive, stdin_mode, command_mode (set by the shell)

@dataclass(frozen=True)
class OptionSpec:
    name: str
    default: bool | str
    value_type: type            # bool or str
    category: OptionCategory
    short_flag: Optional[str] = None      # 'e' for errexit; drives set + $-
    dollar_dash: Optional[str] = None     # letter in $- (often == short_flag)
    notes: str = ""                       # e.g. expand_aliases "no-op gate"

OPTION_REGISTRY: dict[str, OptionSpec] = { ... }   # the ONE source of truth
```

`ShellOptions` (same file or `core/options.py`): a registry-backed `MutableMapping`
seeded from the registry defaults, validating names on write, and offering
`option_string()` (replaces `get_option_string`), `set_short(flag, enable)`, and the
shopt/set helpers that the builtins currently hand-roll.

`ShellState.options` returns the `ShellOptions` instance. `get_option_string()`
delegates to `options.option_string()`. `adopt()` copies via
`self.options.update(parent.options)` as today (the container supports it).

The three scattered maps (`short_to_long`, the `$-` letters, `SHOPT_OPTIONS`) are
deleted and re-derived from the registry.

## Migration Plan

### Phase 0: Characterize before changing

Pin current behavior so the refactor cannot drift it. New
`tests/unit/core/test_shell_options.py` (and extend existing set/shopt tests):

- `$-` for representative option combos, vs bash (the order is load-bearing —
  lowercase, uppercase, then `c`/`s` last; see `get_option_string` doc).
- `set -o` / `set +o` display formats; `shopt` and `shopt -p` formats.
- `set -o badname` → rc 2 + message; `shopt badname` → error.
- `set -euo pipefail` short-cluster + trailing `-o name` consumption.
- `parser-mode` string value survives round-trips.
- The `expand_aliases` always-on no-op (toggling it does not change behavior).
- A meta-test enumerating the known option set (like the existing builtin/keyword
  sync tests) so adding/removing an option is a deliberate registry edit.

### Phase 1: Introduce the registry (no behavior change)

Add `option_registry.py` with `OPTION_REGISTRY` populated from the current dict +
the three scattered maps (including a declared `command_mode`). Add a test asserting
the registry reproduces today's defaults, short→long map, `$-` letters, and shopt
set exactly. Nothing consumes it yet.

### Phase 2: Introduce `ShellOptions`, re-point `ShellState`

Replace `self.options = {…}` with `self.options = ShellOptions()` (seeded from the
registry). Implement the full dict-compatible API so all call sites compile and pass
unchanged. `get_option_string()` → `self.options.option_string()`. Run the full
suite; expect green with zero call-site edits.

### Phase 3: Consolidate the scattered consumers

Re-point `SetBuiltin` (short→long, `set -o` display, validity check) and
`ShoptBuiltin` (`SHOPT_OPTIONS`) at the registry; delete the duplicated maps. Decide
and implement the unknown-name write policy (Open Questions). Declare `command_mode`
in the registry and drop its special-case.

### Phase 4: Docs + release

Update `psh/core/CLAUDE.md` (the options section) to describe the registry as the
single source of truth and `ShellOptions` as the validated container. Version bump +
CHANGELOG. Optionally add the additive typed accessors for the hot reads.

## Risks

- **`$-` ordering / set -o display drift** — load-bearing and bash-pinned. Mitigation:
  Phase 0 characterization first; derive letters from the registry in the *same*
  order.
- **Unknown-name write policy is a behavior change** if we move from "silently
  accept" to "reject." `set -o badname` already errors; the risk is internal
  `options['x'] = …` writes. Mitigation: registry-complete first (Phase 1 proves no
  real option is missing), then tighten — and keep `command_mode` etc. declared so
  nothing legitimately fails.
- **`adopt()` copy** must still carry options into subshells. Mitigation: container
  supports `update`; add a copy test (subshell sees parent's `set -e`, etc.).
- **`MutableMapping` subtleties** — truthiness, iteration order (Python dict order is
  relied on by `set -o` display sorting? it sorts explicitly — verify), `in` checks.
  Mitigation: back it with a real dict internally; only gate writes.
- **The always-on `expand_aliases` no-op** and the `parser-mode` string must keep
  their current semantics. Mitigation: registry `notes` + a pinned test.

## Acceptance Criteria

1. One `OPTION_REGISTRY` is the sole source of option defaults, short flags, `$-`
   letters, and shopt membership; the duplicated maps in `state.py`,
   `environment.py`, and `shell_options.py` are gone.
2. `state.options` is a registry-backed `ShellOptions` with a dict-compatible API;
   call sites are unchanged in shape.
3. `command_mode` is a declared option, not an ad-hoc key.
4. Unknown option names are handled by one explicit, tested policy.
5. `$-`, `set -o`/`+o`, `shopt`/`-p`, subshell option inheritance, and parser-mode
   all behave exactly as before (bash-pinned where applicable).
6. Full suite green; ruff + mypy clean; `core/CLAUDE.md` documents the new surface.

## Open Questions (for the requester)

1. **Unknown-name write policy.** Keep silent-accept for internal writes, or make
   `ShellOptions.__setitem__` reject unknown names (turning typos into loud errors)?
   Recommendation: reject, after Phase 1 proves the registry is complete — it is the
   main correctness upside. `set -o`/`shopt` keep their existing user-facing errors.
2. **Typed convenience accessors.** Add `options.errexit`-style properties for the
   hot reads (readability), or leave all access as `.get('errexit')`? Recommendation:
   add a *small* set additively, no call-site churn required.
3. **Spike?** As with Finding #3, a Phase-2 spike (swap the container, run the suite)
   would confirm the ~0-churn claim before committing. Recommendation: yes — cheap
   and de-risks the central assumption.

## Suggested Sequence

1. Phase 0 characterization tests (+ bash pins for `$-`/`set -o`/`shopt`).
2. Spike: `ShellOptions` container swap; confirm full suite green with no call-site edits.
3. Registry + re-point consumers + unknown-name policy.
4. Declare `command_mode`; delete the duplicated maps.
5. Docs + version bump.
