# Expansion Subsystem Code Quality Review

**Reviewer:** Claude Opus 4.6
**Date:** 2026-02-09
**Scope:** `psh/expansion/` (2,778 lines across 11 files)
**Version:** 0.141.0

*Revised to incorporate findings from the independent Codex implementation
review (`expander_implementation_review_2026-02-09.md`), which identified
several correctness bugs this review initially missed.*

> **Update (v0.145.0):** Most findings from this review have been
> addressed across v0.142.0–v0.145.0.  Of the 8 correctness bugs, 5
> are fixed, 1 was investigated and retained with documented rationale,
> and 2 remain open.  Of the 12 recommendations, 8 are done, 1 was
> investigated and deferred, and 3 remain open.  See per-item status
> annotations throughout.

---

## Executive Summary

The expansion subsystem is the most conceptually demanding part of psh.
Shell expansion is where POSIX compliance gets genuinely difficult:
quoting rules interact with splitting rules, which interact with
globbing rules, which interact with assignment detection rules, all of
which behave differently inside double quotes, single quotes, heredocs,
and unquoted contexts.  Getting it right requires tracking a lot of
state, and getting it *readable* while tracking that state is the real
challenge.

The module structure is well-chosen, the smaller files are genuinely
good code, and the educational intent comes through clearly in the
places where the code is cleanest.  But the two largest files ---
`variable.py` (900 lines) and `manager.py` (714 lines) --- have
accumulated enough complexity that they undermine the project's clarity
goals.  More concerning, both files contain correctness bugs in their
character-scanning logic: the hand-written parenthesis/brace scanners
are **not quote-aware**, causing real misparses when command
substitutions contain quoted `)` characters.

**Overall rating: B-.** *(Updated to approximately B+ after
v0.142.0–v0.145.0 fixes — see update note above.)*
Strong architecture, good small modules, but
the core files have both structural and correctness problems that need
attention.

### Consolidated Scores

*Original scores at v0.141.0; approximate updated scores in parentheses
after v0.145.0 fixes.*

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Correctness | 6.5/10 (~7.5) | ~~Quote-unaware scanners and assignment heuristic cause real bugs~~ Scanner and multi-$@ bugs fixed; assignment heuristic retained with rationale; 2 medium issues remain |
| Elegance | 6/10 (~7) | ~~Implementation of the two largest files is not~~ `expand_variable()` decomposed; `$@` deduplicated; scanners use shared helpers |
| Efficiency | 7.5/10 | Reasonable choices throughout; character-by-character scanning ~~is the main concern~~ now uses shared utility functions |
| Educational value | 7/10 (~7.5) | ~~`variable.py` intimidates rather than teaches~~ Decomposed into focused helpers; smaller modules remain excellent |
| Pythonic style | 6/10 (~7) | ~~Undermined by bare `except:`, C-style loops, inline imports~~ Bare `except:` eliminated; scanners now use library functions |

---

## Module-by-Module Assessment

### The Strong Modules

#### `word_splitter.py` (112 lines) --- A

This is the best file in the subsystem.  It does one thing, explains
exactly how it does it, and handles the edge cases correctly.

The class docstring is a model of useful documentation: it lists the
five rules that govern IFS splitting, including the non-obvious ones
(backslash escapes, empty IFS, whitespace-adjacent-to-non-whitespace
collapsing).  A reader can understand the POSIX IFS specification by
reading this docstring alone.

The implementation is a clean state machine.  The variable names are
descriptive (`ifs_whitespace`, `ifs_non_whitespace`, `current_field`),
the control flow is linear, and the comments explain *why* rather than
*what*.  The backslash-escape handling at lines 61--65 is particularly
well-placed --- it's the first check in the loop, so the reader
immediately understands that escaped characters are never delimiters.

This file is elegant, efficient, educational, and Pythonic.

#### `tilde.py` (54 lines) --- A

Minimal, correct, readable.  The two cases (bare `~` vs `~user`) are
handled with straightforward string operations.  The `pwd` module
fallback for `$HOME` is the right choice.  ~~The bare `except:` on
line 29 is the one blemish --- it should be `except (KeyError,
OSError):` --- but it's a single line in an otherwise clean file.~~
**Update (v0.142.0):** The bare `except:` has been replaced with
`except (KeyError, OSError):`.  No remaining blemishes.

#### `extglob.py` (260 lines) --- A-

Impressive for what it accomplishes.  Converting five extglob operators
with arbitrary nesting and pipe-separated alternatives into Python
regexes is inherently complex, and this module keeps the complexity
well-contained.

The structure is good: a module-level `_EXTGLOB_PREFIXES` frozenset, a
set of small focused functions (`contains_extglob`,
`_find_matching_paren`, `_split_pattern_list`), a recursive core
converter (`_convert_pattern`), and two public entry points.

The `match_extglob` function's optimisation for standalone `!(pattern)`
--- match the positive form and invert --- is a nice touch that shows
understanding of where regex negation gets unreliable.

The negation lookahead on line 147
(`(?:(?!(?:{alt_group}){star}).)*`) is dense but well-commented and
difficult to simplify further without sacrificing correctness.

#### `evaluator.py` (92 lines) --- A-

A clean delegation layer that bridges the Word AST with the expansion
machinery.  Each `_evaluate_*` method is 3--6 lines.  The docstrings
explain the design choice (avoid string round-trips through
`parse_expansion`).

One integration concern noted by the Codex review:
`ExpansionEvaluator.evaluate()` raises `ValueError` for unknown
expansion types (line 49) but does not handle `ProcessSubstitution`
nodes.  The combinator parser can produce
`ExpansionPart(ProcessSubstitution)` nodes
(`psh/parser/combinators/expansions.py:180`), but the evaluator has no
case for them.  If the combinator parser becomes the default, process
substitution would silently degrade.

#### `glob.py` (63 lines) --- A-

Clean and focused.  The extglob check-and-delegate pattern is
well-handled.  The separation between standard glob and extglob
expansion is appropriate.  ~~The `should_expand()` method (lines 65--87)
is dead code --- it references `arg_type`, a concept removed in
v0.120.0 --- and should be deleted.~~
**Update (v0.142.0):** Dead `should_expand()` method deleted.

#### `base.py` (9 lines) --- A

A documentation-only file that explains *why* there is no abstract base
class.  This is better than having an unused ABC or having no
explanation at all.  The note that the interfaces intentionally differ
(`expand()` returns `List[str]` for globs but `str` for variables;
`CommandSubstitution` uses `execute()`) is exactly the kind of design
rationale that helps future maintainers.

### The Complex Modules

#### `command_sub.py` (138 lines) --- B

Functionally correct and well-structured for what is an inherently
difficult operation (fork, pipe, capture, wait).  The code does the
right things: creates a pipe before forking, applies the child signal
policy, strips trailing newlines per POSIX, uses `b''.join(chunks)` for
O(n) concatenation.

Three concerns:

1. **Signal handling without context manager.** Lines 36--38 save and
   restore `SIGCHLD` manually.  If an exception occurs between
   `signal.signal(signal.SIGCHLD, signal.SIG_DFL)` and the `finally`
   block that restores it, the handler remains wrong.  The `finally`
   block is only on the parent side (line 136), but the `fork()` call
   itself could fail.  A context manager would make this airtight.

2. **The `PYTEST_CURRENT_TEST` guard** (line 63) is a testing concern
   leaked into production code.  This is understandable given the
   file-descriptor complexities of testing forked processes, but it
   breaks the abstraction.

3. ~~**Stale comment** (line 34): says "Block SIGCHLD" but the code
   actually resets the handler to `SIG_DFL`, which is the opposite of
   blocking.  (Noted by Codex review.)~~
   **Update (v0.142.0):** Fixed to "Reset SIGCHLD to default".

#### `parameter_expansion.py` (412 lines) --- B

This file has a split personality.  The operation methods
(`remove_shortest_prefix`, `substitute_all`, `extract_substring`, etc.)
are clean, well-named, and individually easy to understand.  The
`PatternMatcher` class is a solid glob-to-regex converter.  The case
modification methods are concise and correct.

But `parse_expansion()` (lines 22--142) is a 120-line sequential
character scan that's hard to follow.  The operator detection logic
iterates the content string looking for `#`, `%`, `/`, `:`, `^`, `,`
characters, but the rules for which character wins are implicit in the
iteration order rather than stated explicitly.  A reader has to trace
through the entire method to understand that `/` is checked before `:`
which is checked before `^`, and that the first match wins.

The Codex review notes that a second, independent parameter expansion
parser exists in `WordBuilder._parse_parameter_expansion()`.  Having
two parsers for the same syntax is a semantic-drift risk --- changes to
one may not be reflected in the other.  Consolidating to a single
parsing authority would reduce this risk.

The suffix-removal methods (lines 191--213) have a subtle correctness
concern: `remove_longest_suffix` iterates forward from index 0, which
finds the *earliest* starting position where the suffix regex matches
--- this is correct for "longest suffix" because starting earlier means
the suffix portion is longer.  But the iteration could be made more
readable by documenting this non-obvious relationship between
"iterating forward" and "finding the longest match from the end."

#### `manager.py` (~670 lines) --- B-

*Updated rating from C+ after v0.142.0–v0.145.0 fixes.*

This file is the orchestrator and it carries too much weight.  The
first 460 lines (`_expand_word`, `_expand_double_quoted_word`, the
escape processors, glob helpers, the utility methods) are reasonable
code: the Word AST traversal is methodical and the quote-context
tracking is correct in the common cases.

The last 250 lines (`execute_arithmetic_expansion`,
`_expand_command_subs_in_arithmetic`, `_expand_vars_in_arithmetic`) are
essentially a hand-written character-by-character parser for finding
`$(...)` and `$((...))` and `$var` inside arithmetic expressions.  This
code works for simple cases but is a different kind of thing from the
Word AST expansion above it.  It would be cleaner as a separate helper
module or as methods on the arithmetic evaluator itself.

**Correctness bugs** (from Codex review):

- **Assignment-word field splitting is over-suppressed** (lines
  231--234). — **RETAINED (v0.144.0)**
  The heuristic checks whether the first `LiteralPart`
  contains `=` and, if so, suppresses word splitting for the entire
  word.  But this fires for non-assignment arguments too: `a=$x`
  passed as a regular argument should undergo word splitting (bash:
  `x="1 2"; printf '<%s>\n' a=$x` produces `<a=1>` `<2>`; psh
  produces `<a=1 2>`).  The executor already identifies true prefix
  assignments before expansion (`command.py:77`), so the expansion
  layer should not duplicate this decision with a weaker heuristic.
  **Status:** Investigated; removal broke `declare VAR=$(...)` because
  builtins receive assignment arguments through `expand_arguments()`.
  Heuristic retained with documented rationale.

- ~~**Multiple `"$@"` in one quoted word** (lines 173--213, 282--309).
  The algorithm returns at the first `"$@"`, collecting everything
  after it (including a second `"$@"`) into a flat suffix string.
  Bash handles `"a$@b$@c"` with params `(1 2)` as three words
  `<a1>` `<2b1>` `<2c>`.  PSH produces `<a1>` `<2b1 2c>`.~~
  **FIXED (v0.145.0):** Extracted `_expand_at_with_affixes()` helper that
  continues processing remaining parts after each `$@`.

- ~~**Quote-unaware `$(...)` scanning in arithmetic pre-expansion**
  (lines 586, 615).  The parenthesis counter does not track quotes,
  so a `)` inside a quoted string within a command substitution is
  misinterpreted as the closing delimiter.~~
  **FIXED (v0.145.0):** Replaced with `pure_helpers` functions using
  `track_quotes=True`.

**Structural issues:**

- **`_expand_expansion` catches too broadly** (line 465).  The outer
  `except Exception` falls back to `str(expansion)`, which silently
  produces wrong output rather than failing visibly.  The inner catch
  for `ExpansionError` and `UnboundVariableError` is correct; the outer
  one hides bugs.  **Status: OPEN.**

- ~~**Duplicated `$@` handling.**  The `$@` splitting logic in
  `_expand_word` (lines 173--213) and `_expand_double_quoted_word`
  (lines 282--309) is structurally identical.  Both scan forward from
  the current part to collect suffix parts, build prefix/suffix strings,
  and distribute across parameters.  This is ~60 lines of near-duplicate
  code that should be extracted into a helper.~~
  **FIXED (v0.144.0):** Extracted `_expand_at_with_affixes()`.

- ~~**Dead method.**  `_split_words()` (line 471) appears to have no
  callers.~~
  **FIXED (v0.142.0):** Deleted.

#### `variable.py` (~850 lines) --- B

*Updated rating from C+ after v0.142.0–v0.145.0 fixes.*

**What's good:**  The `expand_parameter_direct` method and
`_apply_operator` are well-structured dispatch methods.  Each operator
case is 2--6 lines, the delegation to `ParameterExpansion` methods is
clean, and a reader can quickly find how any specific operator is
handled.  The `_expand_tilde_in_operand` helper is a good example of
extracting a small focused method.

**What's been improved (v0.142.0–v0.145.0):**

1. ~~**`expand_variable()` is a 380-line method** with five levels of
   nesting.~~  **FIXED (v0.143.0):** Decomposed into 5 focused helpers
   (`_expand_array_length`, `_expand_array_indices`, `_expand_array_slice`,
   `_expand_array_subscript`, `_expand_special_variable`).  The dispatcher
   is now ~80 lines.

2. ~~**Six bare `except:` handlers.**~~  **FIXED (v0.142.0):** All
   replaced with specific types: 5× `(ValueError, TypeError)`, plus
   the operator-detection heuristic in `expand_parameter_direct` replaced
   with unconditional `evaluate_arithmetic()`.

3. ~~**`expand_string_variables()` scanner is not quote-aware.**~~
   **FIXED (v0.145.0):** Hand-written scanners replaced with
   `find_balanced_parentheses(track_quotes=True)`,
   `find_balanced_double_parentheses(track_quotes=True)`, and
   `find_closing_delimiter(track_quotes=True)` from
   `psh/lexer/pure_helpers.py`.

4. ~~**`process_escapes` parameter is a dead API contract.**~~
   **FIXED (v0.142.0):** Parameter removed from `expand_string_variables()`
   in both `variable.py` and `manager.py`, and `process_escapes=False`
   removed from all 5 callers in `executor/array.py`.

5. ~~**Duplicated operator-detection pattern** in
   `expand_parameter_direct`.~~  **FIXED (v0.142.0):** Replaced
   with unconditional `evaluate_arithmetic()`, matching the v0.141.0
   fix already applied to the other code paths.

**Remaining issues:**

6. **Mixed error reporting.**  Some errors print to `sys.stderr` and
   set `last_exit_code`, some raise `ExpansionError`, and some do both.
   The `:?` operator handler prints, sets the exit code, *and* raises
   --- the caller catches the exception and the print becomes redundant
   if the caller also reports it.  **Status: OPEN.**

---

## Cross-Cutting Quality Dimensions

### Elegance

**Rating: C+** *(~B after v0.143.0–v0.145.0 refactoring)*

The *architecture* is elegant: a manager that delegates to focused
expanders, each handling one expansion type.  The Word AST design ---
per-part quote context propagating through the expansion pipeline ---
is a genuinely good abstraction that eliminates whole categories of
quoting bugs.

~~But the *implementation* of the two largest files is not elegant.
`expand_variable()` reads as an accretion of features rather than a
designed structure.  The duplicated `$@` logic, the multiple paths for
`${var:-default}`, and the scattered array-index parsing all suggest
code that was extended incrementally without periodic refactoring
passes.~~

**Update (v0.143.0–v0.145.0):** `expand_variable()` has been decomposed
into 5 focused helpers.  The duplicated `$@` logic has been extracted
into `_expand_at_with_affixes()`.  The hand-written scanners have been
replaced with shared `pure_helpers` functions.  The implementation now
better matches the architecture's quality.

The smaller files *are* elegant.  `WordSplitter`, `TildeExpander`,
`ExpansionEvaluator`, and `extglob` all demonstrate that the codebase
is capable of clean, focused design.

### Efficiency

**Rating: B+**

The code makes reasonable performance choices:

- `b''.join(chunks)` for command substitution output (O(n) instead of
  O(n^2) concatenation).
- `frozenset` for extglob prefix characters.
- Lazy loading of `ExpansionEvaluator` to avoid circular import
  overhead.
- Shell patterns compiled to Python regexes for matching, leveraging
  the regex engine's optimisations.

The main performance concern is in `expand_string_variables()`: a
character-by-character scan of the entire input string, building the
result one character at a time with `result.append()`.  For long
heredocs or assignment values, this is noticeably slower than it needs
to be.  A `re.finditer` approach that finds `$` and `` ` `` positions
and copies literal segments wholesale would be faster and arguably
clearer.

The suffix-removal iteration in `parameter_expansion.py` is O(n) per
call (linear scan from start), which is fine for typical shell
variables.  It could be O(1) with `re.search`, but the current approach
is simple and correct.

### Educational Value

**Rating: B-** *(~B after v0.143.0–v0.145.0 refactoring)*

The project's stated goal is to teach shell internals through clean,
readable code.  The expansion subsystem partially delivers on this.

**Where it succeeds:**

- The POSIX expansion order is documented in `ExpansionManager`'s
  docstring and in CLAUDE.md.  A student can read the numbered list and
  trace each step through the code.
- `WordSplitter` is a textbook implementation of IFS splitting that a
  student could study to understand the POSIX specification.
- `TildeExpander` and `GlobExpander` are simple enough to understand in
  a single reading.
- `base.py`'s documentation-only approach teaches that sometimes *not*
  abstracting is the right design choice.
- The `PatternMatcher` class clearly shows how shell globs relate to
  regular expressions.

**Where it falls short:**

- ~~`variable.py`'s `expand_variable()` method is too long and nested for
  a student to follow.  A 380-line method with five nesting levels does
  not teach --- it intimidates.~~
  **Update (v0.143.0):** Decomposed into 5 focused helpers
  (`_expand_array_length`, `_expand_array_indices`, `_expand_array_slice`,
  `_expand_array_subscript`, `_expand_special_variable`).  Each expansion
  form is now separately studyable.
- The relationship between `parse_expansion()` and the inline `:-`,
  `:=`, `:?`, `:+` handlers in `expand_variable()` is confusing.  A
  student would reasonably ask "which path handles `${var:-default}`?"
  and the answer ("both, but the inline one is a fallback that probably
  never runs") is not helpful for learning.
- ~~The correctness bugs in the character scanners mean a student studying
  the code would learn *incorrect* shell behaviour for edge cases
  involving quotes inside command substitutions.~~
  **Update (v0.145.0):** Scanners now use shared quote-aware functions.
- The lack of comments explaining *why* certain decisions were made ---
  for example, why `$@` splitting needs special handling, or why
  assignment words suppress word splitting --- means a student needs
  prior shell knowledge to understand the code.
  **Partially improved (v0.144.0):** The assignment-word heuristic now
  has a comment documenting why it exists (builtins need it).

### Pythonic Quality

**Rating: C+** *(~B- after v0.142.0–v0.145.0 fixes)*

The code follows Python conventions in many places: type hints in
function signatures, `TYPE_CHECKING` guards for circular imports,
list comprehensions where appropriate, `@property` for lazy
initialisation.

Areas that ~~are~~ were not Pythonic:

- ~~**Bare `except:` clauses** (6 instances in `variable.py`, 1 in
  `tilde.py`).~~  **FIXED (v0.142.0):** All replaced with specific types.

- **Character-by-character loops** where higher-level constructs would
  work.  ~~The `expand_string_variables`, `_expand_vars_in_arithmetic`,
  and `_expand_command_subs_in_arithmetic` methods all use `while i <
  len(text)` loops with manual index management.~~
  **Partially improved (v0.145.0):** The delimiter-finding portions
  now delegate to `pure_helpers` functions, though the outer loop in
  `expand_string_variables` and `_expand_vars_in_arithmetic` still uses
  manual index management.

- **Inline imports** scattered through the code rather than at module
  level.  Some are necessary (circular import avoidance via
  `TYPE_CHECKING`), but others (`import signal` in `command_sub.py`
  line 35, `import sys` in `manager.py` line 551) are inconsistent
  placement.

- **`str.startswith()` chains** instead of match/case or dictionary
  dispatch.  The special variable handling in ~~`expand_variable()`~~
  `_expand_special_variable()` is a long if/elif chain matching on
  `var_name`.  A dictionary mapping would be more Pythonic and
  extensible.

- ~~**Dead API parameters.**  `process_escapes` is accepted but ignored,
  giving callers a false sense of control.~~
  **FIXED (v0.142.0):** Parameter removed.

---

## Correctness Bugs (Consolidated)

Both reviews identified correctness issues.  These are consolidated
here in priority order, with repro cases from the Codex review.

### High Severity

| # | Bug | Status | Location | Repro |
|---|-----|--------|----------|-------|
| 1 | Assignment-word field splitting over-suppressed: `a=$x` in argument position skips word splitting | **RETAINED** (v0.144.0) — heuristic needed for builtins | `manager.py:231` | `x="1 2"; printf '<%s>\n' a=$x` --- bash: `<a=1>` `<2>`, psh: `<a=1 2>` |
| 2 | Multiple `"$@"` in one quoted word: second `$@` collapsed into suffix | **FIXED** (v0.145.0) | `manager.py:173` | `set -- 1 2; printf '<%s>\n' "a$@b$@c"` --- bash: 3 words, psh: 2 |
| 3 | `expand_string_variables()` scanner is not quote-aware: `)` in quotes breaks `$(...)` | **FIXED** (v0.145.0) | `variable.py:669` | `"${x:-$(printf 'a)b')}"` --- bash: `a)b`, psh: error |
| 4 | Arithmetic pre-expansion scanner has same quote-unaware bug | **FIXED** (v0.145.0) | `manager.py:586` | `echo $(( $(echo ')' >/dev/null; echo 2) + 1 ))` --- bash: `3`, psh: error |

### Medium Severity

| # | Bug | Status | Location | Impact |
|---|-----|--------|----------|--------|
| 5 | `process_escapes` parameter accepted but never checked | **FIXED** (v0.142.0) — parameter removed | `variable.py:633` | Array callers cannot opt out of escape processing |
| 6 | Silent failure degradation: evaluator errors become literal output | OPEN | `manager.py:465` | Bugs masked as wrong output |
| 7 | Process substitution AST not handled by evaluator | OPEN | `evaluator.py:49` | Combinator parser path would silently degrade |
| 8 | Remaining operator-detection heuristic in `expand_parameter_direct` | **FIXED** (v0.142.0) | `variable.py:488` | Bare variable names in array indices within parameter expansion not resolved |

---

## Architectural Observations

### What Works Well

1. **Manager+Specialist pattern.**  `ExpansionManager` owns instances
   of `VariableExpander`, `GlobExpander`, `CommandSubstitution`,
   `TildeExpander`, and `WordSplitter`.  Each specialist handles one
   expansion type.  The manager orchestrates them in the correct POSIX
   order.  This is the right architecture.

2. **Word AST with per-part quote context.**  The decision to track
   `quoted` and `quote_char` on each `LiteralPart` and `ExpansionPart`
   eliminates the old `\x00` marker system and makes quote-dependent
   behaviour structurally correct rather than string-inspection-based.
   This is a significant design improvement over the pre-v0.115 code.

3. **`ExpansionEvaluator` as a thin bridge.**  Rather than duplicating
   expansion logic for AST nodes, the evaluator reconstructs the
   canonical form and delegates.  The `expand_parameter_direct()` path
   avoids even the reconstruction step for parameter expansions.

4. **`ParameterExpansion` as a pure operations library.**  The class
   holds no state beyond a reference to the shell; each method takes a
   value and returns a transformed value.  This makes it easy to test
   and reason about.

### What Could Be Better

1. ~~**`variable.py` needs structural decomposition.**~~
   **DONE (v0.143.0):** `expand_variable()` decomposed into 5 focused
   helpers.  The file is still a single class, but the main method is
   now an ~80-line dispatcher.

2. ~~**A shared quote-aware balanced-scanner** should replace the three
   independent parenthesis/brace counters.~~
   **DONE (v0.145.0):** All 5 scanners in `variable.py` and `manager.py`
   replaced with `find_balanced_parentheses()`,
   `find_balanced_double_parentheses()`, and `find_closing_delimiter()`
   from `psh/lexer/pure_helpers.py`, all called with `track_quotes=True`.

3. **Assignment-word detection should be passed from the executor**
   rather than inferred from `=` in the first literal part. —
   **INVESTIGATED, DEFERRED (v0.144.0).**  Removal broke `declare`
   and other builtins that receive `VAR=value` through
   `expand_arguments()`.  Heuristic retained with rationale documented
   in the code.

4. **Parameter expansion parsing should have a single authority.**
   Currently it exists in both `ParameterExpansion.parse_expansion()`
   and `WordBuilder._parse_parameter_expansion()`.  Changes to one may
   not be reflected in the other.  **Status: OPEN.**

5. ~~**Duplicated `$@` splitting logic** in `manager.py` should be
   extracted into a helper.~~
   **DONE (v0.144.0):** Extracted `_expand_at_with_affixes()`.

6. **Error handling needs a consistent policy.**  Currently, some errors
   print + set exit code, some raise exceptions, some do both.  A
   single approach (raise, let the caller format the message and set the
   exit code) would be cleaner.  **Status: OPEN.**

---

## Quantitative Summary

*Updated after v0.142.0–v0.145.0 fixes.*

| File | Lines | Rating | Key Strength | Key Weakness | Status |
|------|-------|--------|-------------|--------------|--------|
| `word_splitter.py` | 112 | A | Perfect POSIX IFS implementation | --- | — |
| `tilde.py` | 54 | A | Minimal and correct | ~~Bare `except:`~~ | Fixed |
| `extglob.py` | 260 | A- | Recursive pattern conversion | Negation lookahead is dense | — |
| `evaluator.py` | 92 | A- | Clean delegation layer | No `ProcessSubstitution` handling | Open |
| `base.py` | 9 | A | Documents absence of abstraction | --- | — |
| `glob.py` | 63 | A- | Focused, clean | ~~Dead `should_expand()`~~ | Fixed |
| `command_sub.py` | 138 | B | Correct fork/pipe/wait | Signal handling fragility, ~~stale comment~~ | Partially fixed |
| `parameter_expansion.py` | 412 | B | Clean operation methods | `parse_expansion()` is opaque; dual-parser drift risk | Open |
| `manager.py` | ~670 | B- | Good Word AST expansion | ~~Quote-unaware scanners~~, assignment heuristic, ~~duplicated `$@`~~ | Mostly fixed |
| `variable.py` | ~850 | B | `_apply_operator` dispatch | ~~380-line method~~, ~~bare `except:`~~, ~~quote-unaware scanner~~, mixed error reporting | Mostly fixed |

---

## Recommendations (Priority Order)

The recommendations merge both reviews.  Items marked **(Codex)** were
identified by the independent Codex review; items marked **(Opus)**
were identified by this review; items marked **(Both)** were found
independently by both.

1. ~~**Introduce a shared quote-aware balanced-scanner utility** **(Codex)**
   for `$(`, `$((`, `${`, and `` ` `` boundaries.~~
   **DONE (v0.145.0):** All 5 scanners replaced with `pure_helpers`
   functions using `track_quotes=True`.  Added `track_quotes` param to
   `find_balanced_double_parentheses()`.

2. **Fix the assignment-word field-splitting heuristic** **(Codex)** —
   **INVESTIGATED, DEFERRED (v0.144.0).**  Removal broke builtins;
   heuristic retained with documented rationale.

3. ~~**Decompose `expand_variable()`** **(Both)**~~
   **DONE (v0.143.0):** Split into 5 helpers; dispatcher is ~80 lines.

4. ~~**Replace bare `except:` with specific exception types** **(Both)**~~
   **DONE (v0.142.0):** 5× `(ValueError, TypeError)` in `variable.py`,
   1× `(KeyError, OSError)` in `tilde.py`.

5. ~~**Extract `$@` splitting helper** **(Opus)**~~
   **DONE (v0.144.0–v0.145.0):** `_expand_at_with_affixes()` extracted
   and rewritten to handle multiple `$@`.

6. **Unify parameter-expansion parsing** **(Codex)** to a single
   authority.  Consolidate `ParameterExpansion.parse_expansion()` and
   `WordBuilder._parse_parameter_expansion()`.  **Status: OPEN.**

7. ~~**Apply the v0.141.0 arithmetic fix** **(Opus)**~~
   **DONE (v0.142.0):** Replaced with unconditional
   `evaluate_arithmetic()`.

8. ~~**Resolve `process_escapes` dead parameter** **(Codex)**~~
   **DONE (v0.142.0):** Parameter removed, all callers updated.

9. ~~**Delete dead code** **(Both)**~~
   **DONE (v0.142.0):** `GlobExpander.should_expand()` and
   `_split_words()` deleted.

10. **Standardise error handling** **(Both)**: raise `ExpansionError`
    and let callers decide whether to print and/or set exit codes.
    **Status: OPEN.**

11. **Align parser variants on ProcessSubstitution contracts** **(Codex)**.
    **Status: OPEN.**

12. ~~**Add regression tests** **(Codex)**~~
    **DONE (v0.142.0–v0.145.0):** 10 tests in
    `tests/regression/test_expansion_review_fixes.py`.

---

## Conclusion

The expansion subsystem's architecture is sound and its smaller modules
are genuinely high-quality educational code.  The `WordSplitter` alone
is worth studying as a reference implementation of IFS splitting.  The
Word AST design is a real improvement that eliminates structural
quoting bugs.

~~The subsystem's weakness is concentrated in two files.  `variable.py`
is the most important file to refactor: its 380-line dispatch method,
bare exception handlers, and quote-unaware scanner undermine both
readability and correctness.  `manager.py`'s assignment-word heuristic,
duplicated `$@` logic, and its own quote-unaware arithmetic scanner are
equally pressing from a correctness standpoint.~~

**Update (v0.145.0):** The focused work described above has been
completed across v0.142.0–v0.145.0.  `variable.py`'s dispatch method
has been decomposed into 5 helpers, all bare `except:` handlers have
been replaced, and all quote-unaware scanners have been replaced with
shared `pure_helpers` functions.  `manager.py`'s duplicated `$@` logic
has been extracted into a shared helper that correctly handles multiple
`$@` in one word.

Of the 12 recommendations, 8 are done:
- Shared quote-aware scanners (#1)
- Decompose `expand_variable()` (#3)
- Replace bare `except:` (#4)
- Extract `$@` splitting helper (#5)
- Apply arithmetic fix (#7)
- Remove `process_escapes` (#8)
- Delete dead code (#9)
- Add regression tests (#12)

Three remain open:
- Unify parameter-expansion parsing (#6)
- Standardise error handling (#10)
- Align ProcessSubstitution contracts (#11)

One was investigated and deferred:
- Assignment-word heuristic (#2) — needed by builtins

The subsystem has moved from **B-** to approximately **B+**: the
architecture remains strong, the smaller modules are excellent, and the
two previously problematic files are now structurally cleaner with their
highest-severity correctness bugs resolved.
