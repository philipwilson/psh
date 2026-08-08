# Ground-Up Reappraisal #20: Correctness and Textbook Quality

**Date:** 2026-07-11
**Snapshot:** PSH 0.698.0, commit `8d1cb9f6`
**Scope:** all production packages, command-line and interactive entry paths,
test architecture, CI/tooling, and representative documentation
**Method:** fresh static review, targeted unit/integration suites, adversarial
differential probes against bash, complexity/import analysis, and the canonical
local gate
**Overall grade:** **B-**

> **Current status (2026-07-14):** See the
> [v0.724 correctness continuation](ground_up_reappraisal_20_correctness_continuation_2026-07-14.md).
> Critical finding C1 is fixed. Every high-severity category below still has a
> live residual at v0.724; H2 and H7 are partially improved. The independent
> [#21 textbook appraisal](ground_up_reappraisal_21_textbook_2026-07-12.md)
> covers the intervening architecture and code-quality campaign.
>
> **Implementation plan (2026-07-16):** the
> [Boundary Integrity Campaign](boundary_campaign_briefs_2026-07-16.md)
> turns this appraisal's semantic-boundary diagnosis and C1/H1-H19 ledger into
> canonical representations, dependency-ordered work packages, and executable
> exit criteria.

This is a point-in-time appraisal, not a compatibility promise or an
implementation plan already completed. Earlier reviews were not accepted as
evidence: every defect below was tied to the current code and, where practical,
to a fresh reproducer.

## Executive assessment

PSH is an unusually substantial educational shell: approximately 69,000 lines
of production Python, a broad 116,000-line test tree, explicit AST and execution
models, good diagnostics, and serious attention to process, descriptor, and
shell-state behavior. The happy-path architecture is legible and the project
contains several genuinely strong implementations, notably its arithmetic
parser, option registry, child-launch policy, fd remapping, transactional
rollback, structured `Word` representation, and test runner hardening.

It is not yet textbook-quality code. The dominant problem is **semantic
information loss at subsystem boundaries**:

- syntax is sometimes flattened into strings and later reparsed;
- expansion fields lose per-character quote/protection and field-boundary data;
- redirection has two execution backends and, in places, two independent input
  cursors;
- command resolution is recomputed from partial facts rather than represented
  once as a typed result;
- shell-local locale and variable state can fall through to process-global or
  stale environment state;
- visitors implement their own incomplete traversals over a non-canonical AST.

Those are architectural causes, not isolated edge cases. They explain most of
the critical/high findings and should be repaired as coherent model changes,
not as a sequence of narrow conditionals.

### Scorecard

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Semantic correctness | **C+** | Impressive breadth, but fresh probes found execution of expanded data, wrong ordered-redirection behavior, delayed syntax errors, field-boundary loss, signal/job errors, and state isolation defects. |
| Architecture | **B-** | Clear package names and strong local components; the static dependency graph nevertheless forms one large strongly connected component and `Shell` is a broad service locator. |
| Clarity and teaching value | **B** | Excellent comments and subsystem guides in many hard areas; parallel representations, long dispatch functions, dynamic attributes, and special-case expansion paths undermine canonical explanations. |
| Elegance | **B-** | Good abstractions exist, but several core semantics are represented below the minimum fidelity required by the language. |
| Efficiency | **C+** | O(1) pipe/job mechanisms are strong; whole-buffer reparsing, catastrophic regex backtracking, eager script reads, list-front popping, and code-point rendering are material counterexamples. |
| Tests | **B** | Exceptional volume and many differential cases; the canonical gate failed non-deterministically, performance tests are globally excluded, and some tests skip on unexpected behavior. |
| Documentation | **A-** | Extensive, candid, and unusually useful. A few testing claims do not match actual pytest configuration. |
| Tooling/release discipline | **B-** | Ruff and mypy pass, but PR CI is disabled, coverage is non-gating, dev extras omit gate tools, and mypy still permits missing signatures globally. |

## Scope and verification

The review covered the production packages under `psh/`: `lexer`, both parser
implementations, `ast_nodes`, `visitor`, `expansion`, `io_redirect`, `executor`,
`builtins`, `core`, `scripting`, `interactive`, utilities, `shell.py`, and the
CLI. Static inventory at the snapshot was 255 production Python files / 69,106
lines and 641 test-side Python files / 115,889 lines.

| Check | Result |
| --- | --- |
| `ruff check psh tests` | Passed |
| `mypy` | Passed over 255 production files under the configured, permissive signature policy |
| `python run_tests.py --quick` | 8,818 passed, 4 skipped, 1 xfailed in 23.14s |
| Syntax-focused audit | 2,897 passed, 2 skipped; Ruff passed |
| Expansion/I/O-focused audit | 3,024 passed, 1 skipped; Ruff and targeted mypy passed |
| Executor/builtins-focused audit | 2,099 passed, 1 xfailed; two host-signal-sensitive comparisons failed during one collection |
| `python run_tests.py --parallel` | **Failed:** 14,775 passed, 18 failed, 1,354 skipped, 13 xfailed |
| Isolated reruns of the 18 gate failures | All passed: history case, 11 process-substitution cases, and 36 fatal-signal/EXIT-trap cases |

The full-gate failures are therefore not evidence that those 18 product cases
are independently broken. They are evidence that the gate is not hermetic:
capture/fd conditions affect `/dev/stdout`, live-bash process-substitution
behavior changes under the full run, and process-global signal state appears to
leak into the serial phase. A release gate that is red in aggregate and green by
file cannot be treated as authoritative until its isolation defect is found.

## Critical finding

### C1. Expanded redirect data is executed as process-substitution syntax

[`planner.py:58`](../../psh/io_redirect/planner.py#L58) expands a redirect target
to a plain string and passes it to
[`process_sub.py:298`](../../psh/io_redirect/process_sub.py#L298), which recognizes
`<(...)` and `>(...)` from the expanded text rather than from the AST.

```sh
x='<(touch marker)'
printf DATA > "$x"
```

Bash creates the literal file `<(touch marker)`. PSH executes `touch marker`,
does not create the requested file, and then fails against `/dev/fd`. This
violates the interpreter's central code/data boundary and creates an injection
primitive anywhere a redirect filename contains untrusted expanded data.

**Required correction:** represent process substitution only as a structural AST
node and carry that typed origin into `RedirectPlan`. No post-expansion string
may be reparsed as shell syntax.

## High-severity findings

### H1. Multiple heredocs can close out of source order

[`command_accumulator.py:248`](../../psh/scripting/command_accumulator.py#L248)
scans every pending delimiter instead of allowing only the first open heredoc to
close. A line matching a later delimiter prematurely mutates the queue and makes
body text execute as commands. The following differs materially from bash:

```sh
cat <<A <<B
B
a body
A
b body
B
echo after
```

**Correction:** only compare against `_open_heredocs[0]`; model collection as an
ordered queue and add permutations where body lines equal later delimiters.

### H2. Invalid nested substitutions escape read-time syntax validation

Parameter operands, arithmetic text, C-style loop expressions, and array
subscripts remain opaque strings or token lists in
[`words.py:82`](../../psh/ast_nodes/words.py#L82),
[`words.py:130`](../../psh/ast_nodes/words.py#L130),
[`control.py:89`](../../psh/ast_nodes/control.py#L89), and
[`arrays.py:71`](../../psh/ast_nodes/arrays.py#L71). Eager nested parsing covers
only top-level `Word` parts in
[`word_builder.py:122`](../../psh/parser/recursive_descent/support/word_builder.py#L122).

Consequently PSH executes `echo before` where bash rejects the complete input
before executing anything:

```sh
echo before; x=set; echo "${x:-$(if)}"; echo after
echo before; echo $(( $(if) + 1 )); echo after
echo before; a[$(if)]=x; echo after
```

**Correction:** use structured expression/substitution nodes everywhere, or run
one exhaustive recursive syntax-validation pass before execution.

### H3. Heredoc delimiter representation is lossy

Delimiter quote removal is independently approximated by
[`heredoc_lexer.py:210`](../../psh/lexer/heredoc_lexer.py#L210); process-sub tokens
are excluded at [`heredoc_lexer.py:22`](../../psh/lexer/heredoc_lexer.py#L22);
the parser reconstructs a cooked target from lossy token values at
[`redirections.py:83`](../../psh/parser/recursive_descent/parsers/redirections.py#L83);
and the formatter trusts that value at
[`formatter_visitor.py:675`](../../psh/visitor/formatter_visitor.py#L675).

Verified failures include `$'EOF'`, `$"EOF"`, and `"E\q"` delimiters,
`<< <(x)`, and formatter output that changes `<<$X` to `<<X` and can terminate
the body early.

**Correction:** introduce a canonical `HeredocSpec(raw, cooked, quoted, strip_tabs,
body)` derived through the normal quote-removal machinery. Parser, accumulator,
executor, and formatter should share it.

### H4. Builtin fd closes violate left-to-right redirection order

[`manager.py:466`](../../psh/io_redirect/manager.py#L466) defers descriptor closes
until [`manager.py:517`](../../psh/io_redirect/manager.py#L517). Later dups can
therefore see fds that should be closed, and close-then-reopen can finish closed.

- `: 1>&- 2>&1` succeeds in PSH; bash reports a bad fd.
- `: 3>&- 4>&3` succeeds when fd 3 began open; bash fails.
- `eval '/bin/echo child' 1>&- 1>f` leaves the child's stdout closed and `f`
  empty in PSH.

**Correction:** normalize redirections into ordered operations and apply every
operation immediately. Relocate internal fds instead of postponing semantic
operations.

### H5. Composite multi-field expansion loses shell field boundaries

Special paths in
[`word_expander.py:365`](../../psh/expansion/word_expander.py#L365) and
[`word_expander.py:764`](../../psh/expansion/word_expander.py#L764) flatten or
short-circuit embedded `$@`, so later unquoted fragments do not undergo the
correct splitting/globbing pipeline.

```sh
set -- a b; x='c d'; printf '<%s>\n' "$@"$x
```

Bash produces `a`, `bc`, `d`; PSH produces `a`, `bc d`. Affixes, custom `IFS`,
and empty positional elements expose related errors.

**Correction:** replace `Union[str, List[str]]` and early returns with a
field-producing IR whose elements retain boundaries, quote state, and expansion
origin through splitting and pathname generation.

### H6. Glob protection is word-wide rather than character-precise

[`word_expander.py:188`](../../psh/expansion/word_expander.py#L188) removes
escapes and [`word_expander.py:488`](../../psh/expansion/word_expander.py#L488)
later sends a joined string to globbing. If any metacharacter is active,
protected metacharacters in the same word become active too. `"*"*` matches
everything instead of names beginning with literal `*`; `a\*b*` overmatches.

**Correction:** preserve protection per character/segment in the same field IR
proposed for H5, and compile pathname patterns from that representation.

### H7. Plain glob patterns are semantically wrong and can backtrack exponentially

[`extglob.py:146`](../../psh/expansion/extglob.py#L146) translates `?`/`*` to
`.`/`.*`; [`pattern.py:76`](../../psh/expansion/pattern.py#L76) reserves the
memoized engine for extglob. Python regex `.` excludes newlines, so `*` and `?`
are wrong in `case`, `[[ ]]`, and parameter removal. A 14-fragment adversarial
plain pattern took about 1.26s versus 0.00076s in the existing engine.

The engine itself is recursive at
[`pattern_engine.py:224`](../../psh/expansion/pattern_engine.py#L224) and raises
`RecursionError` on a roughly 1,500-literal direct pattern.

**Correction:** make engine evaluation iterative, then route plain and extended
patterns through one compiled, memoized implementation with shell newline
semantics. Add adversarial scaling tests to the real gate.

### H8. Heredoc/here-string input has two independent cursors

The fd backend materializes data at
[`file_redirect.py:171`](../../psh/io_redirect/file_redirect.py#L171), while
builtins receive a separate `StringIO` at
[`manager.py:562`](../../psh/io_redirect/manager.py#L562). If `eval` runs `read`
and then an external `cat`, the child replays data the builtin already consumed.

**Correction:** builtin and child consumers must share one open file description
and offset. Treat cursor ownership as part of the redirection resource model.

### H9. Function definitions are excluded from the ordinary command grammar

[`statements.py:31`](../../psh/parser/recursive_descent/parsers/statements.py#L31)
special-cases functions before and-or parsing, while pipeline dispatch at
[`commands.py:448`](../../psh/parser/recursive_descent/parsers/commands.py#L448)
cannot return a `FunctionDef`. PSH rejects valid forms such as
`f() { :; } | cat`, `f() { :; } && echo y`, background function definitions,
and `! f() { :; }`.

**Correction:** make `FunctionDef` an ordinary command/pipeline component in the
AST and grammar; let statement/list wrappers compose it normally.

### H10. POSIX special-builtin resolution is computed inconsistently

[`command.py:470`](../../psh/executor/command.py#L470) chooses temporary-scope
policy from the mere existence of a same-named function, while the actual POSIX
resolution later selects the special builtin at
[`command.py:772`](../../psh/executor/command.py#L772). The finalizer then drops
assignments that must persist; the `exec` shortcut has the same stale test.

```sh
eval(){ :; }; set -o posix; unset X
X=kept eval :
echo "${X-unset}"
```

PSH prints `unset`; bash prints `kept`.

**Correction:** resolve once to a typed `ResolvedCommand` before any assignment,
scope, redirection, or execution-strategy decision, then carry that value through
the transaction.

### H11. Background pipeline members receive the wrong signal disposition

[`process_launcher.py:257`](../../psh/executor/process_launcher.py#L257) applies
asynchronous-list signal defaults only to `SINGLE`; members launched by
[`pipeline.py:269`](../../psh/executor/pipeline.py#L269) retain default
`SIGINT`/`SIGQUIT`. A delayed `kill -INT %1` completes with status 0 in bash and
terminates the PSH pipeline with 130.

**Correction:** separate `/dev/null` stdin policy from asynchronous signal
policy and apply the latter to every member of a background job.

### H12. Foreground subshells bypass the shared job lifecycle

[`subshell.py:199`](../../psh/executor/subshell.py#L199) creates and waits for a
job but does not run the normal foreground registration, terminal-state capture,
abnormal-termination reporting, or completion transaction. Signal deaths are
silent and Ctrl-Z/`fg` state is unreliable.

**Correction:** express external commands, pipelines, and subshells through one
foreground-job transaction; cover signal reporting and PTY stop/resume behavior.

### H13. A shadowing unset local falls through to the exported environment

[`state.py:840`](../../psh/core/state.py#L840) asks the scope manager, then falls
back to `self.env`. Valid inherited environment entries were already imported as
exported shell variables at
[`state.py:148`](../../psh/core/state.py#L148), so this creates an illicit second
variable namespace.

```sh
export FOO=outer
f(){ local FOO; printf '<%s> <%s>\n' "$FOO" "${FOO-u}"; }
f
```

PSH sees `outer` twice; bash sees an empty value and `u`.

**Correction:** remove normal environment fallback or make lookup tri-state
(`missing`, `present-unset`, `present-value`). Preserve the outer exported value
only when materializing a child process environment.

### H14. Script files are eagerly read to EOF before execution

[`input_sources.py:93`](../../psh/scripting/input_sources.py#L93) reads the whole
file into memory and closes it before executing line one. This makes regular-file
memory use unbounded and breaks FIFO/stream semantics: a producer waiting for an
early command's side effect cannot send the rest of the script.

**Correction:** implement a lazy physical-line source. Relocate/protect a live
script fd from user redirections, or use a separate streaming path for
non-regular files.

### H15. Multiline completeness checking is quadratic

Every [`CommandAccumulator.feed`](../../psh/scripting/command_accumulator.py#L174)
rejoins, preprocesses, scans, tokenizes, and parses the entire open buffer;
[`HeredocLexer`](../../psh/lexer/heredoc_lexer.py#L137) independently retries the
growing logical command. A 100/200/400-line open `if` body measured
0.275/0.750/2.648s while bash remained near 0.005s; a 2,000-line open quote took
about 0.94s.

**Correction:** maintain resumable lexical/completeness state and parse once
when structurally complete. Add end-to-end doubling-ratio tests.

### H16. Malformed UTF-8 corrupts all following `read` records

[`input_reader.py:329`](../../psh/builtins/input_reader.py#L329) pushes a
non-continuation byte into `_partial`, but the next call reads another byte
before consuming it. ASCII and record delimiters cascade into replacement
characters through EOF.

```sh
printf '\303A\nB\n' | psh -c 'read x; read y; printf "x=<%s> y=<%s>\n" "$x" "$y"'
```

**Correction:** use an explicit byte pushback deque or always consume pending
bytes before reading. Test malformed lead bytes before ASCII/newline through
`InputReader`, `read`, and `mapfile`.

### H17. `-i` sets flags but suppresses interactive initialization for `-ic`/scripts

Help promises that `-i` forces interactive mode and loads rc files at
[`__main__.py:56`](../../psh/__main__.py#L56). Yet
[`shell.py:288`](../../psh/shell.py#L288) excludes command/script modes from
`live_interactive`, so history, rc loading, editing, and history expansion are
disabled. This contradicts both the CLI contract and bash `-ic` behavior.

**Correction:** distinguish "interactive-family startup" from "read commands
from a REPL". `force_interactive` should control startup semantics while `-c` or
a script still controls the command source and eventual exit.

### H18. Locale behavior is process-global and not reactive to shell variables

Each `LocaleService` construction overwrites `_active` at
[`locale_service.py:252`](../../psh/core/locale_service.py#L252), and POSIX
classes consult it at
[`locale_service.py:412`](../../psh/core/locale_service.py#L412). Constructing a
second shell can change pattern results in the first. Runtime writes to
`LC_ALL`, `LC_CTYPE`, `LC_COLLATE`, or `LANG` do not rebuild matching state.

**Correction:** pass the owning locale service explicitly through glob/pattern
APIs and observe locale-variable mutations. If the implementation cannot provide
per-shell locale state, document and enforce a single-shell process invariant.

### H19. `disown -h` is a placeholder and detached children can become zombies

[`disown.py:107`](../../psh/builtins/disown.py#L107) dynamically attaches
`no_hup`, but no exit path reads it and no shell-exit HUP/CONT policy exists.
Removing a live job also removes its PID index while noninteractive mode lacks a
general reaper.

**Correction:** make hangup policy a typed `Job` field, implement exit-time
HUP/CONT, and separate child-reaping ownership from user-visible job-table
membership.

## Medium-severity findings

### Syntax, AST, and visitors

1. **Keyword normalization precedes word fusion and deliberately promotes
   prefixes.** [`lexer/__init__.py:61`](../../psh/lexer/__init__.py#L61) turns
   `then$x` into a keyword plus expansion before words are fused. The regression
   test at
   [`test_post_lex_fusion_order_b3.py:1`](../../tests/unit/lexer/test_post_lex_fusion_order_b3.py#L1)
   explicitly pins a bash syntax divergence. Fuse lexical shell words first,
   then classify the complete word in grammar context.
2. **Bare command-position `in` is treated as an external command.** The state
   logic in
   [`keyword_normalizer.py:107`](../../psh/lexer/keyword_normalizer.py#L107)
   suppresses the keyword outside pending loop/case contexts; bash/dash reject
   it syntactically. Preserve subject exceptions while rejecting the bare form.
3. **Lone `[[` operator tokens are reversed.** The primary logic in
   [`tests.py:121`](../../psh/parser/recursive_descent/parsers/tests.py#L121)
   rejects `[[ == ]]`, `[[ != ]]`, `[[ =~ ]]` as nonempty primaries but accepts
   `[[ < ]]` and `[[ > ]]`; bash does the opposite.
4. **Visitors silently omit valid regions.** `SecurityVisitor` returns before
   redirects at
   [`security_visitor.py:67`](../../psh/visitor/security_visitor.py#L67), while
   `ValidatorVisitor` rejects redirect-only commands at
   [`validator_visitor.py:139`](../../psh/visitor/validator_visitor.py#L139).
   [`traversal.py:46`](../../psh/visitor/traversal.py#L46) only descends direct
   `Word` children, missing substitutions in loop/case words, redirects, and
   arrays. Build one exhaustive structural walker and make analyses callbacks.
5. **AST contracts are not canonical.** `StatementList` promises
   `List[Statement]` at
   [`commands.py:50`](../../psh/ast_nodes/commands.py#L50), but a subshell-bodied
   function is inserted through a cast at
   [`functions.py:147`](../../psh/parser/recursive_descent/parsers/functions.py#L147).
   Case, loop, and array nodes keep parallel flat/structured fields. Make the
   structured representation authoritative and derive display/compatibility
   views.

### Expansion and redirection

6. **Created-file modes depend on backend.** Several external/permanent paths
   use `0o644` at
   [`file_redirect.py:252`](../../psh/io_redirect/file_redirect.py#L252) instead
   of POSIX `0666 & ~umask`; in-process builtin output happens to use the correct
   base. Normalize all file creation through one helper.
7. **`noclobber` is a check-then-open race.** The precheck at
   [`file_redirect.py:51`](../../psh/io_redirect/file_redirect.py#L51) is separate
   from later `O_TRUNC` opens. Use an atomic `O_EXCL` strategy with explicit
   treatment of existing non-regular targets.
8. **Unquoted heredocs use double-quote backslash rules.** Delegation at
   [`file_redirect.py:206`](../../psh/io_redirect/file_redirect.py#L206) removes
   `\"`, although `"` is not special in an unquoted heredoc. Add a dedicated
   heredoc expansion context.
9. **Smaller expansion gaps share the same representation problem:** empty
   unquoted `$@` under `IFS=''`, Unicode brace endpoints, empty `HOME`/`OLDPWD`,
   unset `{fd}>&-`, POSIX `${é}`, and alias timing/name policy. Relevant entry
   points include
   [`word_splitter.py:42`](../../psh/expansion/word_splitter.py#L42),
   [`brace_expansion.py:487`](../../psh/expansion/brace_expansion.py#L487),
   [`tilde.py:59`](../../psh/expansion/tilde.py#L59),
   [`file_redirect.py:305`](../../psh/io_redirect/file_redirect.py#L305), and
   [`param_parser.py:107`](../../psh/expansion/param_parser.py#L107).

### Builtins and execution contracts

10. **`eval` lacks option parsing.** [`eval_command.py:29`](../../psh/builtins/eval_command.py#L29)
    executes `--` as a command and turns invalid POSIX special-builtin options
    into lookup failures. Consume `--` and raise a typed status-2 usage error for
    other options.
11. **`.`/`source` PATH search is wrong.** [`source_command.py:125`](../../psh/builtins/source_command.py#L125)
    skips empty PATH components and always falls back to cwd. Preserve component
    ordering and disable the POSIX-dot fallback.
12. **Job builtin contracts are inconsistent.** `wait` option/identifier
    parsing, `jobs -p` pipeline output, `jobs -l` member rendering, and
    noninteractive `bg` differ from bash in
    [`job_control.py:69`](../../psh/builtins/job_control.py#L69) and
    [`job_control.py:244`](../../psh/builtins/job_control.py#L244). Centralize a
    typed job-option parser and render process-level records.
13. **`cd -L` trusts user-mutated `PWD`.** [`navigation.py:23`](../../psh/builtins/navigation.py#L23)
    can manufacture `/fake/sub` and retain `a/../b`. Validate that `PWD` denotes
    the actual directory, then lexically normalize logical components.
14. **Numeric operands use Python syntax.** Representative `int` paths at
    [`core.py:39`](../../psh/builtins/core.py#L39),
    [`positional.py:32`](../../psh/builtins/positional.py#L32), and
    [`test_command.py:433`](../../psh/builtins/test_command.py#L433) accept
    underscores, Unicode digits, and unlimited values. One ASCII decimal parser
    should provide command-specific sign/range policy; timeout parsing should
    reject non-finite floats.
15. **`test -v` does not evaluate indexed subscripts arithmetically.**
    [`test_command.py:21`](../../psh/builtins/test_command.py#L21) calls `int`
    directly, so `a[1+1]` is not resolved. Reuse the canonical array arithmetic
    evaluator.
16. **`printf -v` accepts invalid destinations.**
    [`io.py:164`](../../psh/builtins/io.py#L164) writes without identifier
    validation. Route every variable-writing builtin through the same validated
    assignment API.

### Interactive behavior

17. **The key decoder splits UTF-8 sequences across reads.**
    [`key_decoder.py:274`](../../psh/interactive/key_decoder.py#L274) decodes each
    raw chunk with `errors='replace'`; a split `é` becomes two replacement
    events. Use an incremental decoder and a `deque` (current `pop(0)` is also
    quadratic).
18. **Rendering counts code points, not terminal cells.**
    [`line_layout.py:34`](../../psh/interactive/line_layout.py#L34) and completion
    layout at
    [`line_renderer.py:233`](../../psh/interactive/line_renderer.py#L233) mishandle
    wide, combining, and emoji sequences. Introduce a grapheme/cell-width map
    using `wcwidth` semantics and index editing positions through it.
19. **Prompt cwd ignores logical shell state.**
    [`prompt.py:280`](../../psh/interactive/prompt.py#L280) uses `os.getcwd()` and
    naive string-prefix home abbreviation. Use shell `PWD`/`HOME`, validate
    directory boundaries, and retain logical symlink paths.
20. **History files use strict platform-default decoding.**
    [`history_manager.py:135`](../../psh/interactive/history_manager.py#L135) and
    [`history_manager.py:320`](../../psh/interactive/history_manager.py#L320) can
    raise `UnicodeDecodeError` on arbitrary history bytes. Use explicit UTF-8
    with `surrogateescape` consistently for reads and writes.
21. **RC safety and exception policy overpromise.**
    [`rc_loader.py:40`](../../psh/interactive/rc_loader.py#L40) permits
    group-writable files and has a stat/open race, while
    [`rc_loader.py:35`](../../psh/interactive/rc_loader.py#L35) and
    [`repl_loop.py:144`](../../psh/interactive/repl_loop.py#L144) catch all
    exceptions and present internal defects as user errors. Either remove the
    security claim or use `lstat`/`open`/`fstat` with group/world and parent
    checks; report unexpected exceptions through the strict internal-defect
    path.

## Architecture appraisal

### What is working

- `Shell` has an explicit construction sequence, child-clone path, and
  idempotent resource lifecycle.
- The parser is decomposed by production, uses iterative flat chains, and has
  strong source spans, diagnostics, and nesting guards.
- `Word` parts retain useful quote context; arithmetic has a real tokenizer,
  parser, and evaluator rather than `eval`-style shortcuts.
- `ProcessLauncher`, child policy, fd remapping, partial-pipeline rollback, and
  O(1) job PID/state indexes are strong systems code.
- `BuiltinContext`, stateless-builtin enforcement, option registries, variable
  attributes, and typed error categories are good teaching choices.
- The project documents design intent and known limitations more candidly than
  most codebases of this size.

### What prevents textbook quality

1. **The dependency graph is not layered.** Static package imports, including
   deferred/type-local imports, place `ast_nodes`, `builtins`, `core`, `executor`,
   `expansion`, `interactive`, `io_redirect`, `lexer`, `parser`, `scripting`,
   `utils`, and `visitor` in one strongly connected component. The construction
   at [`shell.py:195`](../../psh/shell.py#L195) passes the whole `Shell` to most
   major components. This makes local reasoning and independent testing harder.
2. **Canonical data stops too early.** The AST is structured at the top level,
   but heredoc specs, nested expression-bearing fields, expansion output, and
   command resolution fall back to strings, lists, flags, casts, or dynamic
   attributes.
3. **Two redirection universes duplicate semantics.** The 898-line I/O manager
   and 780-line file backend separately handle ordering, ownership, restoration,
   cursor behavior, and creation modes. Differences now leak into observable
   behavior.
4. **Complexity is concentrated in semantic choke points.** Examples include
   `ShellState.__init__` (272 lines), arithmetic tokenization (218 lines / 51
   branch nodes), pipeline execution (205 lines), command execution (190 lines),
   `ScopeManager.set_variable` (171 lines / 31 branch nodes), and history
   expansion (210 lines / 41 branch nodes). Long functions are not automatically
   wrong, but these functions mix policy selection, mutation, cleanup, and error
   translation.
5. **The type gate checks bodies more than contracts.** About 83% of functions
   have a return annotation, but
   [`pyproject.toml:98`](../../pyproject.toml#L98) globally permits untyped and
   incomplete definitions; only the lexer forbids them. `Any`, dynamic
   attributes, casts, and `getattr`/`hasattr` are prevalent precisely around
   lifecycle and AST boundaries.

### Target architecture

The highest-leverage refactor is a small set of canonical typed values:

- `HeredocSpec`: raw spelling, cooked delimiter, quote/strip policy, body;
- `ExpandedField`: ordered protected/unprotected segments plus provenance and
  field-boundary semantics;
- `RedirectOp`: source-ordered operation with typed target and owned resources;
- `ResolvedCommand`: one resolution result carrying kind, POSIX-special status,
  assignment policy, execution strategy, and permanent-redirection policy;
- `VariableLookup`: missing versus shadowed-unset versus value;
- exhaustive `walk_ast`: the only structural traversal used by visitors;
- narrow service protocols (`VariableAccess`, `ExpansionContext`, `JobRuntime`,
  `LocaleContext`) injected instead of the full `Shell` where practical.

These are not abstraction for its own sake. Each one removes duplicated
conditionals and fixes multiple verified defects at once.

## Test, tooling, and repository findings

### T1. The advertised whole suite excludes every performance test

[`pytest.ini:11`](../../pytest.ini#L11) globally sets
`--ignore=tests/performance`. The standard runner and nightly workflow inherit
that setting, yet
[`testing_source_of_truth.md:32`](../testing_source_of_truth.md#L32) calls the
standard tier the "whole suite" and says only quick deliberately omits
performance. The three performance modules therefore protect neither merges nor
nightlies.

**Correction:** remove the global ignore. Exclude performance explicitly in the
quick tier, run deterministic performance invariants in the standard gate, and
run broader benchmarks nightly with recorded baselines.

### T2. There is no automated PR gate

[`tests.yml:3`](../../.github/workflows/tests.yml#L3) is dispatch-only and
documents manual disablement; the source of truth confirms this at
[`testing_source_of_truth.md:7`](../testing_source_of_truth.md#L7). A local-only
gate cannot enforce Python/platform consistency or prevent an untested merge.

**Correction:** enable required PR checks for Ruff, mypy, and the deterministic
suite. Add Linux and macOS jobs and at least the claimed Python support edges
when runtime permits; leave expensive live-bash/coverage work nightly.

### T3. The canonical gate is non-hermetic

The audit's full run failed 18 cases that all passed in isolation. The failures
clustered in `/dev/stdout` under xdist capture, live-bash process substitution,
and fatal-signal tests after prior serial tests. The executor-focused audit also
found a comparison whose host process already ignored `SIGTTOU`.

**Correction:** snapshot/restore signal dispositions in an autouse fixture,
launch signal-oracle shells from a known disposition, isolate live-bash fd tests
in clean subprocesses, and avoid assertions that depend on pytest's inherited
capture fds. Bisect the serial predecessor that leaks fatal-signal state.

### T4. Some tests convert regressions into skips

[`test_arithmetic_integration.py:25`](../../tests/unit/expansion/test_arithmetic_integration.py#L25)
conditionally calls `pytest.skip` when implemented behavior is wrong, and
[`test_modular_lexer_integration.py:145`](../../tests/unit/lexer/test_modular_lexer_integration.py#L145)
catches any exception and skips. Current supported behavior should assert; truly
absent features should use explicit, strict `xfail` tied to a ledger item.

### T5. The documented dev install does not install all gate tools

[`pyproject.toml:30`](../../pyproject.toml#L30) includes pytest tooling but omits
Ruff and mypy, although both are required by the canonical gate.

**Correction:** include them in `.[dev]` (or a clearly documented `.[quality]`
extra consumed by CI) and pin compatible lower bounds.

### T6. Coverage reports are non-gating

Nightly coverage has no minimum and no changed-line policy. Coverage percentage
alone would not have found the semantic defects in this review, but a modest
floor plus branch coverage would prevent silent erosion in high-risk managers.

### T7. Workspace hygiene can exhaust the host

The ignored `tmp/` tree occupies approximately **76 GB**, including one 75 GB
probe artifact, on a filesystem that was 98% full during the audit. The worktree
also contains two pre-existing untracked probe-like files (` 1 ` and `b]y`).

**Correction:** make probe helpers use bounded output, sparse/temp files where
appropriate, per-run cleanup, and a size guard. Do not make cleanup destructive
by default; provide a reviewed command that enumerates exactly what will be
removed.

## Subsystem verdicts

| Subsystem | Grade | Main reason |
| --- | --- | --- |
| Lexer | **B** | Strong scanner decomposition and spans; keyword/fusion ordering and heredoc quote handling violate lexical word identity. |
| Recursive-descent parser | **B** | Clear production structure and diagnostics; function definitions and opaque nested syntax expose grammar/model gaps. |
| Combinator parser | **B-** | Valuable educational second implementation, but duplication increases parity burden and package coupling. |
| AST/visitors | **C+** | Useful top-level model; non-canonical parallel fields and incomplete independent traversals are unsafe. |
| Expansion | **C+** | Broad feature set and strong arithmetic; field/protection representation cannot express required semantics. |
| I/O redirection | **C+** | Excellent fd collision/rollback work; code/data reinterpretation, ordering, cursor, mode, and noclobber defects are fundamental. |
| Executor/processes | **B-** | Strong launcher and pipeline mechanics; resolution and job-lifecycle policy are not uniformly centralized. |
| Builtins | **B-** | Wide, generally disciplined implementation; shared parsing/validation contracts remain inconsistent. |
| Core state | **B** | Thoughtful variable attributes/options/child clone; environment fallback and global locale violate isolation. |
| Scripting | **C+** | Good source abstraction intent; eager reads, ordered-heredoc bug, and quadratic accumulation break streaming/scale. |
| Interactive | **B-** | Substantial custom editor and PTY tests; Unicode/cell layout, logical cwd, encoding, and exception policy need hardening. |
| CLI/orchestration | **B** | Explicit lifecycle and modes; forced-interactive semantics and broad service location remain misleading. |
| Tests/tooling | **B** | Exceptional breadth; hermeticity, performance inclusion, and automated enforcement lag behind the suite's size. |

## Prioritized improvement program

### Phase 0: Restore trust in the gate

1. Make the 18 order/environment-dependent failures reproducibly green in the
   full canonical run.
2. Remove skip-on-failure tests and put performance tests in an explicit tier.
3. Enable required PR checks and make `.[dev]` install the complete local gate.
4. Add every critical/high reproducer from this report as a differential
   regression before changing implementations.

### Phase 1: Re-establish code/data and ordering invariants

1. Stop process-substitution detection from expanded redirect strings (C1).
2. Introduce `HeredocSpec` and enforce ordered collection (H1/H3).
3. Normalize source-ordered `RedirectOp` execution with one shared cursor
   (H4/H8), correct creation modes, and atomic noclobber.
4. Resolve commands once with `ResolvedCommand` (H10).

### Phase 2: Replace the expansion representation

1. Define `ExpandedField`/protected segments and remove
   `Union[str, List[str]]` special paths.
2. Implement `$@`, affixes, splitting, and globbing as transformations over
   fields rather than strings.
3. Route all shell patterns through the iterative memoized engine.
4. Thread explicit locale context through expansion.

### Phase 3: Canonicalize syntax and traversal

1. Make every expression-bearing AST field structural and validate the full
   program before execution.
2. Put function definitions in the normal command grammar.
3. Fuse complete words before reserved-word classification.
4. Replace visitor-specific recursion with one exhaustive walker; delete flat
   duplicate AST fields after migrating consumers.

### Phase 4: Unify runtime lifecycle

1. Use one foreground-job transaction for commands, pipelines, and subshells.
2. Apply asynchronous signal policy to complete jobs.
3. Implement typed detach/HUP/reap ownership.
4. Replace environment fallback with tri-state variable lookup.
5. Make script input lazy and byte/encoding policy explicit.

### Phase 5: Finish the textbook pass

1. Decompose the measured choke-point functions around typed decisions and
   transactions, keeping cleanup adjacent to resource acquisition.
2. Introduce narrow component protocols and progressively break the package SCC.
3. Require complete signatures package by package; minimize casts, `Any`, and
   dynamic attributes at AST/runtime boundaries.
4. Make terminal editing grapheme/cell aware and all persistent text
   `surrogateescape` safe.
5. Update architecture documents with the final canonical representations and
   dependency direction; delete comments that justify known divergences once
   the divergences are removed.

## Final verdict

PSH is a serious, high-effort implementation with better documentation and test
breadth than many production interpreters. It earns **B-**, not because it lacks
features or polish, but because several core representations cannot preserve the
semantics they are meant to teach. The critical redirect issue, ordered
redirection/heredoc defects, field/protection loss, job/signal inconsistencies,
state leakage, and non-hermetic gate preclude a higher correctness grade.

The path to an A is coherent: preserve syntax as syntax, fields as structured
fields, redirections as ordered operations over owned resources, resolution as
one typed decision, and shell state as per-shell state. Those changes would both
fix the verified bugs and make the code shorter, easier to explain, and more
efficient.
