# Architecture & Feature Review — psh v0.237.0

**Date**: 2026-06-09
**Method**: Seven parallel in-depth reviews — one per subsystem (lexer, parser, expansion,
executor, core+builtins, I/O+interactive) plus a 204-probe feature battery comparing
`python -m psh -c CMD` against `bash -c CMD` (bash 5.2). The six most severe findings were
independently re-verified before publication. The rerunnable probe harness is at
`tmp/featreview/probe.py` (results in `tmp/featreview/results.txt`).

> Line numbers are as of v0.237.0 (commit a0d79bf) and will drift.

---

## Executive Summary

The **architecture is genuinely good**: clean layering, no circular imports, no
cross-module private-attribute reaching (the v0.223–v0.236 cleanup paid off), and several
components are textbook quality — ProcessLauncher, WordSplitter, the recognizer registry,
JobManager, the Variable/scope model. Feature breadth is impressive: **169/204 probes
byte-identical to bash**, including `;;&`, nested command substitution, namerefs,
BASH_REMATCH, sparse arrays, and getopts.

However, the review found a cluster of **verified correctness defects** concentrated in
exactly the seams the test suite does not exercise: redirection fd save/restore, script-mode
`set -e` semantics, and quoted multi-field array expansion. Several are severe enough to be
release-blocking for the "POSIX compliance within reason" claim.

| Subsystem | Verdict | One-line summary |
|---|---|---|
| Lexer | ADEQUATE | Solid daily tokenization; heredoc re-lexing design unsound; much dead config |
| Parser | GOOD | Clean RD design; `&` (async list) handling violates POSIX grammar |
| Expansion | ADEQUATE | Scalars excellent; multi-field `"${arr[@]}"` semantics broken |
| Executor | ADEQUATE | Process/job mechanics solid; errexit/eval/subshell semantics wrong; one crash |
| Core + Builtins | ADEQUATE | Scoping/readonly/namerefs faithful; `local` injection bug; phantom DEBUG/ERR traps |
| I/O + Interactive | NEEDS WORK | Five reproducible redirection defects, incl. one that kills the shell's stdout |
| Feature conformance | GOOD | Broad parity; error-handling semantics are the weak axis |

### Critical defects (all re-verified with one-line repros)

1. **`true 2>&1; echo after` permanently breaks builtin output.**
   `restore_builtin_redirections` (`psh/io_redirect/manager.py:185-204`) closes the *real*
   stdout/stderr object after the stream swap; its only guard is for StringIO — which is
   precisely why `captured_shell` tests structurally cannot see it.
2. **`set -e` exempts nothing** (`psh/executor/core.py:113-157`): `if false; then :; fi`,
   `false && true`, `! true`, and `while` conditions all kill the script. Conversely
   `set -e; (false)` does *not* propagate because subshells don't inherit `state.options`
   or `$?` (`psh/shell.py:55-68`). Breaks the canonical `set -eu` strict-mode idiom; the
   user guide claims "Full support". Existing tests pass only because they use the
   interactive-mode fixture, which never reaches the script-mode `sys.exit` path.
3. **`"${arr[@]}"` collapses to one word** (`psh/expansion/manager.py:237-269`): only
   `$@` is special-cased inside double quotes. `a=(1 "2 3"); set -- "${a[@]}"; echo $#`
   → psh `1`, bash `2`. For-loops work only via a duplicate array path in the executor.
4. **External-command redirections applied twice** — parent (`psh/executor/command.py:521`)
   and child (`psh/executor/strategies.py:163,320,366`) both apply the list. Consequences:
   `cmd 2>&1 >f` puts stderr into `f` (bash: original stdout), and command substitutions in
   heredoc bodies / redirect targets **execute twice** (verified by side-effect counting).
5. **`local v='$(echo injected)'` re-expands the value** (`psh/builtins/shell_state.py:177-179`)
   — single-quoted text in `local` assignments passes through expansion a second time.
   Correctness *and* injection defect.
6. **`break N` past loop depth crashes** (`psh/executor/core.py:115,154`): a function-local
   `import sys` shadows the module import; the `except LoopBreak` handler then raises
   `UnboundLocalError`.
7. **Errors mid-redirection leak fds permanently**: setup happens outside the `try`
   (`psh/executor/command.py:544-546`, `psh/io_redirect/manager.py:30-40`) and restore
   iterates forward instead of `reversed()` (`psh/io_redirect/file_redirect.py:249-261`,
   contradicting `psh/io_redirect/CLAUDE.md:68-73`). `echo hi >a >/bad/x; echo AFTER`
   puts AFTER into `a`. Also: heredocs >~64KB deadlock (`file_redirect.py:68-77` writes the
   whole body into a pipe before any reader exists; bash uses a temp file).

---

## 1. Lexer (`psh/lexer/`) — ADEQUATE

The recognizer architecture is coherent and everyday tokenization matches bash impressively
well, but three confirmed correctness defects, measured quadratic scaling, and a large mass
of dead/misleading code undercut both POSIX compliance and educational clarity.

### Strengths
- Clean layering: no circular imports, no cross-module private-attribute reaching; consumed
  only via `tokenize()`/`tokenize_with_heredocs()`.
- `pure_helpers.py` is a genuinely good teaching artifact: stateless, documented, 58 unit
  tests, bash-accurate ANSI-C escapes (`\xHH`, 1-3 digit octal `& 0xFF`, `\u`/`\U`).
- ~35 adversarial probes (nested `$(...)` in quotes, backticks in double quotes,
  `[[ a < b ]]`, case glob patterns, fd-dups, `<<`/`<<-`/`<<<`, `;then`, `${x^^}`,
  line continuation) all matched bash exactly.
- `RecognizerRegistry.recognize` (registry.py:81-95) re-raises recognizer exceptions with
  context — no broad `except Exception` silencing anywhere in the subsystem.
- Two-pass command-position design documented in one shared place; keyword normalizer has
  golden-file tests.

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `pure_helpers.py:643-674` | `validate_brace_expansion` counts `{`/`}` with no quote/`$()` awareness: `echo ${x:-"}"}`, `${x:-'}'}`, `${x:-$(echo "}")}` all die with "Unclosed quote"; bash prints `}`. POSIX 2.6.2 violation. |
| HIGH | `lexer/__init__.py:83-123` | `tokenize_with_heredocs` omits the `TokenBraceExpander` pass that `tokenize()` performs (line 74). Any line with a heredoc loses brace expansion: `cat <<EOF; echo {a,b}` prints `{a,b}`. |
| HIGH | `heredoc_lexer.py:103-113` | `HeredocLexer._tokenize_line` re-lexes each physical line with a **fresh** ModularLexer, discarding cross-line state (open quotes, case/bracket depth). `cat <<EOF && echo "two\nwords"` → "Unclosed quote". Architecturally unsound. |
| MED | `pure_helpers.py:102-169` | `find_balanced_parentheses` can't handle case-pattern `)` inside `$(...)`: `echo "$(case a in a) echo inner;; esac)"` → parse error (bash: `inner`). |
| MED | `modular_lexer.py:353-418` | `_is_inside_potential_array_assignment` backward-scans on every `"`, `'`, `$` with logically unsound right-to-left quote tracking; with the position-setter tracker rebuild (96-105), lexing is quadratic (0.56s @ 2000 quoted words → 2.17s @ 4000). |
| MED | `quote_parser.py:43-47` | `QUOTE_RULES['"']` declares escape sequences (`'n': '\n'`, …) that are wrong per bash **and never used** (only tested for truthiness). Misleading documentation-as-code. |
| MED | `constants.py:28-64` | `OPERATORS_BY_LENGTH` is dead (live table is `OperatorRecognizer.OPERATORS`, recognizers/operator.py:18-59) and has drifted (lacks `&>` `&>>` `|&` `>|` `<>`; bogus `'2>&1'` entry). `psh/lexer/CLAUDE.md:106-115` instructs contributors to edit the dead table. |
| MED | various | Dead code mass: `RecoverableLexerError`/`LexerErrorHandler` (position.py:79-86, 299-342 — type-hints a nonexistent `StateMachineLexer`); ~20 never-read `LexerConfig` fields + unused factory methods; all `LexerState` members except `NORMAL`; ~7 `LexerContext` fields + ~14 methods never called; unused pure_helpers (`read_until_char`, `find_word_boundary`, `scan_whitespace`, `find_operator_match`); `quote_parser.parse_simple_quoted_string`. |
| MED | `scripting/source_processor.py:282-298` | Heredoc-containing commands tokenized **twice** (full `tokenize()` discarded, then `tokenize_with_heredocs()`); `strict=` conflates POSIX mode with batch/interactive lexer config. |
| MED | `recognizers/literal.py` (834 L) | Heuristic swamp: `_is_in_string_concatenation` (678-709) guesses by character class; `_parse_ansi_c_quote_inline` (638-676) duplicates quote_parser; quote-state tracking reimplemented ≥4× across the lexer. |
| LOW | `modular_lexer.py:272,315-351,568` | "Modular recognizer" story half-true: quotes/ANSI-C/`$`-expansions bypass the registry; `WhitespaceRecognizer` can never fire; `CommentRecognizer` wins by fragile implicit coupling and violates the declared return contract. |
| LOW | `modular_lexer.py:443` | PARAM_EXPANSION vs VARIABLE decided by substring scan missing bare `-` `+` `^` `,` `@`; harmless only because downstream re-parses both identically. |
| LOW | `keyword_normalizer.py:47,55` | `heredoc_already_collected` assigned in one branch, read in the next iteration's other branch — NameError-prone under refactoring. |
| LOW | `constants.py:67-75` | `break`/`continue`/`return` in `KEYWORDS`; bash treats them as builtins (`function break {...}` works in bash, rejected by psh). |
| LOW | `state_context.py:41-59` | `LexerContext.copy()` omits the case_depth fields — latent state-loss if ever used. |

### Test coverage
257 unit tests, strong on pure_helpers (87%), keyword normalizer (96%), ANSI-C. Gaps:
`heredoc_lexer.py`/`heredoc_collector.py` at **0%** unit coverage (where the HIGH bugs
live); `literal.py` 53%; `process_sub.py` 26%; no tests for quoted braces inside `${...}`,
multi-line-string + heredoc, or lexer performance regression.

---

## 2. Parser (`psh/parser/`) — GOOD

Well-organized, readable, broadly correct; carries verified POSIX defects around `&`,
line continuations after `|`, and function-body semantics, plus substantial dead
state-management machinery that CLAUDE.md misleadingly documents as core architecture.

### Strengths
- Clean delegating architecture: `Parser` (392 L) orchestrates 8 focused sub-parsers; all
  RD files <530 lines; no circular imports; combinators depend one-way on recursive_descent.
- Verified feature breadth: `;;`/`;&`/`;;&` with terminator captured, process substitution,
  C-style for (incl. `;;` form), multiple heredocs/command, quoted delimiters, dynamic
  fd-dup targets, `[[ ]]` precedence, redirect attachment after `fi`/`done`/`esac`, `|&`.
- Excellent error messages: position, line/column, caret, context, suggestions
  (context.py:263-289).
- Combinator parser in better sync than expected (full main suite at v0.171.0; shares
  WordBuilder so word-level features propagate automatically; 217 unit + 30 parity tests).
- Strong subsystem CLAUDE.md (sub-parser contract table, grammar flow).

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `recursive_descent/parsers/commands.py:117` | `&` consumed into `SimpleCommand.background` — backgrounds only the last simple command. `sleep 1.5 && echo b &` blocks in psh, immediate in bash. POSIX applies `&` to the whole list. Same in combinator parser. |
| HIGH | `control_structures.py:129,158,255,322,364,479` | Control structures cannot be backgrounded at all: `while ...; done &` and `if ...; fi &` are parse errors in BOTH parsers (subshell/brace groups do handle `&` — an inconsistency, not a design decision). |
| HIGH | `commands.py:281-287` | Newline after `|` rejected (no `skip_newlines()` after consuming PIPE); POSIX permits a linebreak after `|`. Both parsers. |
| HIGH | `scripting/source_processor.py:168-249` | Scripts ending a line with `&&` fail: `_is_incomplete_command` detects continuation by **string-matching ~40 error messages**, and "Expected command" lacks the required substring. Parser should signal incomplete-at-EOF structurally (e.g. `ParseError.at_eof`). |
| MED | `functions.py:80-84` | `f() ( ... )` unwraps SubshellGroup into a plain CommandList — subshell function bodies lose subshell semantics (`f() ( cd / ); f` leaks the cd; bash isolates). |
| MED | `functions.py:43-64` | `f() { ...; } > file` silently mis-parses as FunctionDef + separate empty command with a redirect (creates the file once at definition); bash applies the redirect at every call. |
| MED | `commands.py:421-469` + control_structures + arithmetic | Dead `execution_context` machinery: 7 constructs × `_parse_X_neutral`/`parse_X_statement`/`parse_X_command` triplets (~25 wrappers) solely to set `ExecutionContext.STATEMENT/PIPELINE` — **nothing reads it** (only an exclusion list in metrics_visitor.py:513), and it's set wrongly for nested constructs. Deletable. |
| MED | `context.py` (528 L) | ~Half dead: `in_test_expr`/`in_arithmetic`/`in_case_pattern`/`in_function_body` written, never read (the save/restore context manager at 456-474 is a no-op — yet CLAUDE.md documents it as a core pattern); `ParserProfiler` (~105 L) never enabled; `enter_rule`/`exit_rule` only called by tests; scope_stack/loop_depth/function_depth unused; ctx heredoc trackers only reached via the duplicate `Parser.parse_with_heredocs` that only regression tests call (production uses `support/utils.py:82`). |
| LOW | statements.py:96-101, parser.py:328-333, commands.py:325-331 | And-or chain parsing duplicated 3×; two `parse_with_heredocs` implementations; `_FD_DUP_RE` defined 3× with variations. |
| LOW | commands.py | psh accepts invalid `echo a & && echo b` (bash: syntax error) — side effect of `&` at SimpleCommand level. |
| LOW | `control_structures.py:270,375,434` | Case patterns / for-loop items flattened to strings (`''.join(str(p) ...)`), losing per-part quote context — inconsistent with the Word AST. |
| LOW | `commands.py:358-382`; `support/utils.py:20-80` | Hacky: previous-token backslash counting for `\$(`; `populate_heredoc_content` is hasattr-based duck traversal instead of the project's own visitor pattern; delimiter-suffix fallback can mismatch duplicate delimiters. |

Combinator credibility note: its hard parts are 100-190-line imperative functions
(`_build_if_statement` 192 L, conditionals.py:47; `parse_array_element_assignment` 174 L,
special_commands.py:402), undercutting the functional-parsing teaching narrative; `core.py`
itself is clean and educational.

### Test coverage
335 RD + 217 combinator + 30 parity unit tests. Gaps: no parser-level unit tests for
redirections, control structures, case items, or function definitions (only indirect via
execution); nothing tests `&` on lists/control structures or newline-after-`|` — exactly
where the defects are; `test_parser_context.py` spends effort on the dead profiler.

---

## 3. Expansion (`psh/expansion/`) — ADEQUATE

Architecture and scalar parameter expansion are genuinely good and well-tested (741 unit
tests), but field-production semantics are broken in several HIGH-severity ways.

### Strengths
- Clean orchestration: ExpansionManager delegates to single-purpose expanders; the Word AST
  path (`_expand_word`, manager.py:88-235) uses structural quote context, with clear inline
  rationale.
- `WordSplitter` is a pure, dependency-free, excellent POSIX 2.6.5 implementation —
  verified correct for `IFS=:`, `IFS=' :'`, `IFS=`, unset IFS, empty-field retention.
- Recent features mostly match bash: `@Q/@U/@u/@L/@E/@a/@A`, `${arr[-1]}`, arithmetic
  offsets incl. `${x:0:-2}` errors, non-colon operators via `_param_is_set`, IFS-aware `$*`.
- `_expand_at_with_affixes` (manager.py:271-355) correctly distributes `pre"$@"post`
  incl. multiple `$@` and empty params — a hard case many toy shells miss.
- High educational clarity in manager.py, word_splitter.py, evaluator.py.

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `manager.py:237-269` | Only `VariableExpansion(name='@')` produces multiple fields in double quotes: `"${arr[@]}"`, `"${@:2}"`, `"${arr[@]:1:2}"`, `"${arr[@]@Q}"` all join into ONE word. The duplicate for-loop path (executor/control_flow.py:498 via `is_array_expansion`/`expand_array_to_list`, variable.py:1042/1083) is itself the cause of the inconsistency. |
| HIGH | `manager.py:69-73` | When any arg is a process substitution, ALL words are rebuilt via `Word.from_string(a)`, discarding quote info — a quoted `"*"` then glob-expands. Also mutates `command.args`/`command.words` in place. |
| HIGH | `variable.py:753-758` | `${!prefix*}`/`${!prefix@}` pass `operand` (always `''`) instead of `var_name` as the prefix → matches every shell+env variable; `match_variable_names(quoted=True)` (parameter_expansion.py:316-318) also emits literal `"` characters. |
| HIGH | `manager.py:260-269,350-355` | `"$@"` with zero positional params yields one empty argument instead of zero fields (`set --; set -- "$@"; echo $#` → psh 1, bash 0). |
| HIGH | `variable.py:279-281` | Unquoted `$@`/`$*` joined with a space then IFS-split as one string, losing parameter boundaries (`set -- "a b" c; IFS=:; printf '[%s]' $@` → psh `[a b c]`, bash `[a b][c]`). |
| MED | `parameter_expansion.py:240-250` | Replacement passed raw to `re.sub`: `${x/b/\1}` aborts "invalid group reference" (bash: `a1c`). Needs a literal-replacement lambda. |
| MED | `variable.py:639-685` | Operand quote removal missing: `${u:-"quoted def"}` prints the literal quotes. |
| MED | `variable.py:533-537` | `_expand_tilde_in_operand` expands unconditionally — wrong inside double quotes (`"${x:-~}"`) and wrong when `~` came from an expansion. |
| MED | `tilde.py:25` | Uses `os.environ['HOME']`, ignoring the shell variable: `HOME=/xyz; echo ~` prints the real home. Layering: should read `state.get_variable('HOME')`. |
| MED | `variable.py:515-531` | `${!n}` fails for positional names (`n=2; echo ${!n}` → empty) and array-element names (`ref='a[1]'`); `${!n@Q}` empty — final lookup uses `state.get_variable()` instead of `_get_var_or_positional()`. |
| MED | `manager.py:666-673` | `_expand_vars_in_arithmetic` coerces non-integer values to `'0'`: `x=1+2; echo $(($x))` → 0 (bash 3), while `$((x))` works. |
| MED | `word_splitter.py:61-65` | Backslash in expansion results treated as an escape during field splitting (`x='a\ b'; printf '[%s]' $x` → 1 field, bash 2). POSIX field splitting has no backslash processing; docstring admits it compensates for downstream escape handling. |
| LOW | `variable.py:77,297` | Doubled `psh: psh: $undef: unbound variable` under `set -u`; exit 1 vs bash 127. |
| LOW | `variable.py:67-68`; `manager.py:510-514` | Broad except swallowing `parse_expansion` failures / falling back to `str(expansion)`. |
| LOW | `variable.py` (1172 L) | Array-subscript resolution reimplemented ~6× (105-130, 234-259, 314-337, 350-383, 489-505, 612-629); pattern/replacement split-join round-trip (parameter_expansion.py:110-126 ↔ variable.py:1152); dozens of repeated inline imports. |
| LOW | — | Missing: bash 5.2 patsub `&`, `${x~}` case-toggle, `@K`/`@k`; glob results byte-sorted vs locale order. |
| LOW | `tests/conformance/differences/psh_bash_differences.json:8` | Mischaracterizes `V=hello echo $V` — claims bash has a bug, but POSIX expands `$V` before the assignment takes effect; bash is correct (psh prints `world` in the `V=world echo $V` case, bash `hello`). |

### Verified divergences (cmd → psh | bash)
```
a=(1 "2 3" 4); printf "[%s]" "${a[@]}"     → [1 2 3 4]            | [1][2 3][4]
set -- x y z; printf "[%s]" "${@:2}"       → [y z]                | [y][z]
a=(1 "2 3"); set -- "${a[@]}"; echo $#     → 1                    | 2
set --; set -- "$@"; echo $#               → 1                    | 0
set -- "a b" c; IFS=:; printf "[%s]" $@    → [a b c]              | [a b][c]
abc=1; abd=2; echo ${!ab@}                 → all vars, quoted     | abc abd
echo "*" <(echo hi)                        → glob-expanded        | * /dev/fd/63
x=abc; echo "${x/b/\1}"                    → exit 1, regex error  | a1c
u=; echo ${u:-"quoted def"}                → "quoted def"         | quoted def
echo "${x:-~}"                             → /Users/pwilson       | ~
HOME=/xyz; echo ~                          → real home            | /xyz
n=2; set -- a b c; echo ${!n}              → (empty)              | b
x=1+2; echo $(($x))                        → 0                    | 3
x='a\ b'; printf "[%s]" $x                 → [a\ b]               | [a\][b]
set -u; echo $undef                        → rc 1, doubled prefix | rc 127
```

### Test coverage
741 tests pass in ~3s; excellent breadth on arithmetic, parameter operators, transforms,
word splitter, brace/extglob/glob. Gaps: no test asserts the *field count* of quoted
`"${arr[@]}"`/`"${@:2}"` outside for-loops; `${!prefix*}` integration tests use weak
`in`-assertions that mask the prefix bug; no tests for replacement backslashes, operand
quote removal, unquoted `$@` + custom IFS, empty-`"$@"` field count, indirection through
positionals, process-substitution/quoting interplay.

---

## 4. Executor (`psh/executor/`) — ADEQUATE

The architecture (visitor + strategies + unified ProcessLauncher) is genuinely clean and
process/job-control mechanics are solid, but errexit/subshell/eval semantics diverge from
bash in script mode in ways that break real scripts, and one confirmed crash exists.

### Strengths
- ProcessLauncher really is the single fork path; all 5 fork sites use
  `apply_child_signal_policy()` — one source of truth, with a well-reasoned
  `is_shell_process` SIGTTOU distinction.
- Correct pipeline process-group mechanics: sync-pipe synchronization (pipeline.py:155-223),
  both parent and child `setpgid`, terminal control transferred before wait and restored via
  `finish_foreground_job`. `pipefail` correct; `|&` supported; signal deaths → 128+N.
- Clean delegation: ExecutorVisitor (313 L) is a thin dispatcher; no god object; all files
  <650 lines; ExecutionContext replaces scattered flags.
- Correct POSIX lookup order (special builtins > functions > builtins > aliases > external)
  with alias-recursion guard and `\cmd` bypass.
- Loop break/continue levels correct per loop type, incl. C-style `for` continue→update.

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `core.py:113-117,149-157` | errexit fires inside condition contexts — no suppression for if/while conditions, `&&`/`||` non-final commands, `!` negation. Five verified divergences. Tests pass only via the interactive fixture (script-mode `sys.exit` path untested). |
| HIGH | `shell.py:55-68` (used by subshell.py:146-151) | `Shell(parent_shell=...)` copies env/vars/functions/aliases/positionals but **not** `state.options` or `last_exit_code`: `set -e; (false; echo no)` prints; `false; (echo $?)` → 0. Outbound isolation is correct (real fork). |
| HIGH | `strategies.py:75,136`; `shell.py:151-158` | `break`/`continue` inside `eval` swallowed: eval's `run_command` builds a fresh visitor with `loop_depth=0`, and the `except Exception` guards re-raise only FunctionReturn — LoopBreak/LoopContinue (plain Exception subclasses, core/exceptions.py:3-9) are converted to exit 1. Also swallows UnboundVariableError from builtins. (command.py:188-195 gets this right.) |
| HIGH | `core.py:115,154` | Function-local `import sys` shadows module import → `except LoopBreak` handler crashes with UnboundLocalError on `break N` beyond depth. Trivial fix: delete the two local imports. |
| MED-HIGH | `command.py:174,587-623` | `exec missing_cmd` doesn't exit the shell (POSIX: non-interactive exits 127); prints error and continues, rc 0. The `cmd_name == 'exec'` special case also bypasses the strategy pattern. |
| MED | `command.py:188-217` | `set -u` doesn't exit in script mode; doubled "psh: psh:" prefix; rc 1 vs bash 127. |
| MED | pipeline.py:79-80, subshell.py:40-41, strategies.py:154-155,356-357 | `ProcessLauncher(state, job_manager, io_manager, shell.interactive_manager.signal_manager)` built ad hoc 4× — executor→interactive layering reach; should be one shared `shell.process_launcher`. |
| MED | pipeline.py:142, strategies.py:348, subshell.py:108, command.py:563-570 | Test-environment awareness in production: `'pytest' in sys.modules` gates terminal-control logic; StringIO special-cases. Tested paths differ from production paths exactly where job control is trickiest. |
| MED | `process_launcher.py:287-343` | Dead `launch_job` (zero callers) with a fragile `command_str.split()` re-parse. Delete. |
| LOW | `strategies.py:205-209` | `f &` rejected ("functions cannot be run in background"); bash forks a subshell. |
| LOW | `strategies.py:263-265` | Alias fallback path re-tokenizes already-expanded args via `' '.join(args)`. |
| LOW | `control_flow.py:301-303,577-621` | Case expr expanded only when `'$' in expr` (misses backticks); `_convert_case_pattern_for_fnmatch` guesses tokenizer-stripped escapes — fix belongs in lexer/Word AST. |
| LOW | misc | `psh/executor/test_evaluator.py` violates the project's own naming rule; executor CLAUDE.md:59-65 documents strategy order wrongly (Builtin-before-Function); break/continue messages split between `shell.stderr` and `sys.stderr`; no "Terminated"/"Killed" job-death notices; `VAR=v :` persists assignment (intentional POSIX rule — should be a documented difference). |

### Verified divergences
```
set -e; if false; then echo t; fi; echo after  → no output rc=1     | after rc=0
set -e; false && true; echo after              → rc=1               | after rc=0
set -e; ! true; echo after                     → rc=1               | after rc=0
set -e; while false; do :; done; echo after    → rc=1               | after rc=0
set -e; f(){ false; }; if f; then :; fi; ...   → rc=1               | after rc=0
set -e; (false; echo no); echo after           → both lines rc=0    | rc=1, nothing
for i in 1 2 3; do eval break; echo $i; done   → errors + 1 2 3     | (empty)
while true; do break 2; done; echo $?          → internal crash     | 0
exec nonexistent; echo after                   → after, rc=0        | rc=127
set -u; echo $UNDEF; echo after                → doubled msg, after | rc=127
false; (echo $?)                               → 0                  | 1
```
Verified identical: `! false`, pipeline status, pipefail (incl. `!`), `wait $!`, subshell
outbound isolation, temp-export, function return codes, `break 2` nested, `(exit 3)`,
`$(exec echo sub)`.

### Test coverage
94 unit tests pass. Gaps: errexit/nounset tested only via interactive-mode fixture, never
`psh -c` subprocess; no tests for `eval break/continue`, `break N` overflow, `exec` failure
semantics, subshell option/`$?` inheritance; `is_pytest` branches make the terminal-control
code structurally untestable by the current suite.

---

## 5. Core + Builtins (`psh/core/`, `psh/builtins/`) — ADEQUATE

The core/state architecture is genuinely clean and readonly/scoping semantics are largely
bash-faithful, but several user-visible defects (a crash, a double-expansion injection in
`local`, never-dispatched DEBUG/ERR traps, missing `+=`/`umask`/`times`) and substantial
copy-paste duplication across builtins.

### Strengths
- Clean layered core: state.py 353 L, scope_enhanced.py 518 L, variables.py 255 L.
  `VarAttributes` Flag enum + `Variable` dataclass + sparse insertion-ordered arrays is
  textbook-quality. Only one broad `except Exception` in the whole core+builtins surface
  (trap_manager.py:173).
- Readonly enforcement comprehensive: verified on 10 write paths, all via a single
  `ReadonlyVariableError` in `EnhancedScopeManager.set_variable`.
- Dynamic scoping + UNSET tombstones match bash (verified incl. local shadowing visibility
  from callees and unset-of-local).
- Nameref core paths solid: cycle detection in resolve, write-through, late binding,
  `declare -n x=x` self-reference error — all match bash.
- Registration right-sized: `@builtin` decorator + 63-line registry with alias support;
  `mapfile` is a model builtin (clustered flags, `-d ''` NUL, usage rc 2).

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `builtins/shell_state.py:177-179,217-222` | `local` double-expands already-expanded values incl. command substitution: `local v='$(echo injected)'` → runs it. Injection defect. |
| HIGH | `core/trap_manager.py:244-256` | DEBUG and ERR traps stored, documented in `trap` help (signal_handling.py:54-55), **never dispatched** (zero call sites for `execute_debug_trap`/`execute_err_trap`). Silent no-op of an advertised feature. |
| HIGH | parser-level | Scalar `+=` unsupported: `x=a; x+=b` → "command not found" rc 127 (also makes `RO+=x` report not-found instead of readonly). `arr+=(b c)` works. |
| HIGH | `builtins/source_command.py`; `function_support.py:820-824` | `return` in a sourced script doesn't return — prints "can only return..." and keeps executing (bash: stops, rc from return). Check only consults `function_stack`. |
| MED | `builtins/signal_handling.py:105-113` | `trap -- 'cmd' INT` takes `--` as the action → "invalid signal specification". Standard defensive idiom broken. |
| MED | `builtins/environment.py:319-323,348-360,258` | `set` returns 0 after the first `-o`/`+o` → `set -o errexit -o pipefail` silently drops pipefail. `set -o vi` prints to stdout (bash silent); bare `set` emits non-bash `edit_mode=` line. |
| MED | `builtins/environment.py:205-230` | `export` has zero option parsing/validation: `export -p` creates an env var named `-p`; `export 1bad=x` succeeds rc 0 (bash: invalid identifier, rc 1). |
| MED | `core/scope_enhanced.py:408-421` | UNSET tombstones leak into `get_all_variables()`: `f(){ unset HOME; set \| grep -c '^HOME='; }` → 1 (bash 0). Loop must skip `var.is_unset`. |
| MED | `core/scope_enhanced.py:101-119` | Cross-declare nameref cycles not rejected at write time: `declare -n a=b; declare -n b=a; a=5` silently rewrites b's target (bash: "circular name reference", fails). |
| MED | registry | `umask` missing (POSIX-required; on macOS the /usr/bin/umask shadow makes it a silent no-op — `umask 077` has no effect); `times` missing (rc 127); `ulimit`, `hash`, `builtin`, `caller` absent. |
| MED | non-interactive fatality | `set -u` violations and readonly assignment continue script execution (bash aborts). Same class as executor issue. |
| MED | `interactive/signal_manager.py:127` | Trap actions execute synchronously inside the Python signal handler (`execute_trap` → `shell.run_command`), re-entering parser/executor mid-command; bash defers to command boundaries. Combined with trap_manager.py:173's broad except, control-flow exceptions raised by trap actions are swallowed. |
| LOW | `trap_manager.py:153-158` | Dead: `if not action: return` makes `if action == ''` unreachable. |
| LOW | `trap_manager.py:41-45` | Signal probing by temporarily installing SIG_DFL for 1-31 at startup; use `signal.valid_signals()`. |
| LOW | `function_support.py:537-559`; shell_state.py:296 | `DeclareBuiltin._apply_attributes` dead (never called); third copy of the transform logic. |
| LOW | `scope_enhanced.py:499-501` | `declare -l x=ABC; declare -u x` retroactively re-transforms stored value (bash affects future assignments only). |
| LOW | various | Usage-error exit codes 1 where bash/CLAUDE.md say 2 (`declare -z`, `set -q`, `return abc`); `unset` no-args rc 1 (bash 0); ReturnBuiltin prints to raw sys.stderr. |
| LOW | all builtins | Ad-hoc hand-rolled flag parsing everywhere (worst: `set` env ladder, declare's 95-line dict parser, `'-f' in args` scans); three divergent array-literal parsers (declare's naive split() mishandles `(a "b c")`). |
| LOW | 36 sites / 9 sites | `shell.stdout if hasattr(...)` duplicated 36×; `in_forked_child → os.write(1,...)` dance 9× across 4 files — should be one helper on `Builtin`. |
| LOW | `variables.py:107-113`; environment.py:56 | `Variable.copy()` shallow for arrays; in-process `Shell(parent_shell=)` (env builtin) shares live array objects. |
| LOW | `shell.py:122-147` | `__getattr__`/`__setattr__` delegation shim hides attribute provenance; `_state_properties` manually synced. ShellState itself is *not* a god object. |

### Test coverage
28 builtin test files, strong on echo/printf/read/test/type/mapfile/let/getopts. Gaps: no
dedicated unit tests for `set` (`-o` parsing — where the bug is), `export`/`unset`, `local`
(the injection bug), `source`, `kill`, `wait`, `help`. `tests/unit/core/` contains **only**
test_nameref.py — EnhancedScopeManager (tombstones, attribute merge, export sync) has no
direct unit tests, which is why the tombstone leak survived. `test_getopts_builtin_broken.py`
naming suggests a quarantined suite worth revisiting.

---

## 6. I/O Redirection + Interactive (`psh/io_redirect/`, `psh/interactive/`, `psh/line_editor.py`) — NEEDS WORK

Architecture and breadth are genuinely good (self-pipe signals, unified job control,
per-type redirect helpers), but five reproducible correctness defects exist in everyday
redirection idioms — clustered exactly where test coverage is absent.

### Strengths
- Textbook async-signal-safe design: SignalNotifier self-pipe, non-blocking ends, promotion
  to fds ≥64 to dodge `exec 3>file`, CLOEXEC (`psh/utils/signal_utils.py:39-74`); SIGCHLD
  handler only writes a byte, reaping deferred to the REPL loop.
- JobManager clean and centralized: single source of truth for `tcsetpgrp`
  (job_control.py:273-315), per-job terminal-mode save/restore, bash-compatible jobspecs.
- Redirect dispatch well factored: per-type `_redirect_*` helpers; dynamic `>&$fd` via
  non-mutating AST copy (file_redirect.py:103-129) is elegant.
- Feature breadth with correct single-path semantics: `<>`, `>|`, `&>`, `&>>`, `|&`,
  fd-close, high fds, noclobber, heredoc quoted/unquoted, here-strings, process
  substitution — verified (`>file 2>&1` ordering correct when single-applied).
- Small readable REPL (repl_loop.py, 94 L) with EIO handling, EXIT trap on Ctrl-D, history
  save; rc-file permission check.

### Issues
| Sev | Location | Issue |
|---|---|---|
| HIGH | `io_redirect/manager.py:131-136,185-204` | `builtin 2>&1`/`1>&2` closes the real stdout/stderr: stream swap (`sys.stderr = sys.stdout`) then restore closes "the redirected stream" guarding only StringIO. `echo hi 2>&1; echo again` → "I/O operation on closed file". Breaks the session permanently. The StringIO guard means `captured_shell` tests structurally cannot detect it. |
| HIGH | `executor/command.py:521` + `strategies.py:163,320,366`, `process_launcher.py:322` | Redirections applied twice for externals (parent `with_redirections` + child `setup_child_redirections`): (a) `ls /x 2>&1 >f` puts stderr into f (bash: original stdout); (b) command substitutions in heredoc bodies and redirect targets execute **twice** (verified). |
| HIGH | `command.py:544-546`; `manager.py:30-40,139,172` | Error path leaks redirections permanently: setup outside the `try`; failing second redirect loses all backups (`echo hi >a >/bad/x; echo AFTER` → AFTER in a; shell stdout hijacked). Instance-level `_saved_fds_list` partially populated then "restored" by the *next* builtin. |
| HIGH | `file_redirect.py:249-261` | `restore_redirections` iterates **forward** though io_redirect/CLAUDE.md:68-73 documents `reversed()`: `{ /bin/echo hi; } >e >f; echo A` → A in e. Builtin variant: `stdout_backup` overwritten by second redirect (manager.py:117-124). |
| HIGH | `file_redirect.py:68-77` | Heredocs >~64KB deadlock: whole body written into a pipe before any reader exists. Bash uses a temp file. Verified hang at 130KB. |
| MED | `keybindings.py:129-198`; `line_editor.py:301-376,916-926,1176-1209` | vi mode mostly façade: ~25 bound actions (`undo`/`redo`, `dd`/`cc`/`yy`/`p`/`P`/`r`/`D`/`C`, `e`/`E`/`W`/`B`/`^`, `/`/`?`/`n`/`N`, visual, `.`) never dispatched by `_execute_action` — silent no-ops; `LineEditor.undo`/`redo` dead; `key_handler.mode` never synced with `LineEditor.mode`; multi-char bindings unreachable. Dead state: vi_pending_motion, vi_registers, vi_last_change, vi_mark_start, kill_ring_pos. |
| MED | `line_editor.py:464-478,1155-1162` | Single-row rendering model: raw `\b` + `\033[K` redraws corrupt display once input wraps past terminal width; only SIGWINCH redraw is wrap-aware. (Challenges the "cohesive" assessment: rendering interleaved with buffer mutation in every method is why only buffer-level unit tests exist.) |
| MED | `signal_manager.py:111-127` | Traps run inside signal-handler context (contradicts the file's own self-pipe philosophy); can re-enter the executor mid-fd-swap. |
| LOW | `repl_loop.py:87`; `process_sub.py:77` | Broad `except Exception` catches LoopBreak/LoopContinue and genuine bugs; process-sub child catches Exception not BaseException (escaping BaseException unwinds into the forked parent stack copy). |
| LOW | `line_editor.py:262-266` vs `history_manager.py:12-20` | Dual history appenders with different dedup policies; vestigial readline usage. |
| LOW | `prompt.py:110-111`; `line_editor.py:944-946` | `\[`/`\]` → `\001`/`\002` counted as visible by `_visible_length` → cursor math off for colored prompts. DSR `ESC[6n` each prompt stalls 0.1s on non-answering terminals (line_editor.py:201). |
| LOW | `builtins/job_control.py:31`; `line_editor.py:1052,1067` | `jobs -l` is a TODO; tab completion path-only; LineEditor reaches into `CompletionEngine._find_word_start` (private). |

### Test coverage
`tests/unit/io_redirect/` has just 6 predicate tests; `tests/integration/redirection/` has
76 tests but **zero** for `2>&1 >file` ordering, same-fd-twice, redirect error paths, or
large heredocs — precisely the five verified defects. PTY suites
(test_pty_line_editing.py, test_pty_job_control.py) are nearly all blanket-`xfail`, so
interactive job control and line editing are effectively unverified in CI. LineEditor: 22
unit tests cover buffer ops; the read_line select loop, CSI parsing, CPR drain, resize
redraw, and vi normal dispatch are untested.

---

## 7. Feature Conformance (204-probe battery vs bash 5.2) — GOOD

**169/204 probes byte-identical.** Full parity verified for: all common parameter-expansion
operators (incl. `@Q @U @L @u`, substrings with negative offsets, indirect `${!x}` scalar),
indexed + associative arrays (init, keys, slices, `+=`, negative indices, mapfile), the full
arithmetic surface (ternary, comma, bases, `**`, `(( ))` status, `let`), brace expansion,
`[[ ]]` incl. `=~`/BASH_REMATCH/`-v`, extglob (prior-line enable), process/command
substitution (nested, backticks), heredocs/herestrings, getopts, read `-r -a -d -n`,
printf `%q %b %c`, declare flags + namerefs, pipefail/noclobber, trap EXIT/signals,
select, functions (recursion, >255 wrap, FUNCNAME[0]), `$RANDOM $SECONDS $LINENO $$ $!
SHLVL`, `$@`/`$*` IFS edges, exit codes 126/127/128+n, `;&`/`;;&`, C-style for, pushd/popd.

### Undocumented divergences (doc claims "Full support" for the first group)
| Feature | psh | bash |
|---|---|---|
| `set -e` exemptions (&&-lists, conditions, subshells) | wrong (see §4) | correct |
| `set -u` fatality | warns, continues, rc 0 | aborts rc 127 |
| readonly violation fatality | warns, continues | aborts rc 1 |
| `builtin 2>&1` | breaks shell stdout | fine |
| `${0##*/}` | empty | `bash` |
| Quoted regex in `=~` (`[[ abc =~ "a.c" ]]`) | treated as regex (matches) | literal (no match) |
| `printf -v var fmt` | prints `-v`, var empty | sets var |
| `printf '%(fmt)T'` | literal output | strftime |
| `PIPESTATUS` | empty | populated |
| `$PPID $UID $EUID $EPOCHSECONDS $EPOCHREALTIME` | empty | populated |
| `$_` | python path, never updates | last arg |
| `builtin` builtin | rc 127 (function wrappers infinite-loop) | works |
| `export -f` | child rc 127 | child runs function |
| Alias expansion non-interactive | on by default; `shopt expand_aliases` invalid | opt-in |
| `$"..."` locale string | literal `$localized` | `localized` |
| `${x@P}` | doesn't prompt-expand | expands |
| `wait` after `kill %1` | rc 143 | rc 0 |
| `type -t if` | empty rc 1 | `keyword` |
| minor | `$-` lacks `c`/`h`; `read -p` prompt not suppressed w/o tty; shopt `lastpipe`, `history -s`, `bind` absent | |

### Documented divergences (doc verified accurate)
coproc; DEBUG/ERR/RETURN traps; `wait -n`; `caller`; `complete`/`compgen`; history
expansion; `read -u`; `time` keyword; `BASH_VERSION`/`BASH_SOURCE`/`BASH_LINENO`/
`FUNCNAME[1+]`; `${!prefix@}` listing all variables; `set -euo` combined flags; extglob
same-line limit; `@K`/`@k`. (One doc error: psh_bash_differences.json:8 inverts the POSIX
verdict on `V=hello echo $V` — bash is the conformant one.)

### Conformance suite assessment
217 tests (posix/ 70, bash/ 147) vs 3,613 in the main suite. Strong: parameter expansion,
arithmetic, globbing, quoting, BASH_REMATCH. Thin/absent: **errexit (0 tests)**, traps (1),
getopts (0), heredocs (1), job control (1), select (0), fd-dup edge cases (one probe would
have caught the `2>&1` crash). The project's own rule — user-guide conformance claims must
be backed by conformance tests — is violated for the `set -e`/`set -u` "Full support"
claims.

---

## Prioritized Remediation Plan

Each fix must land with regression tests pinned to bash behavior (subprocess-style
`psh -c` tests for anything involving script-mode exits or fd state, per the parallel-safety
rules in CLAUDE.md).

### Tier 0 — surgical fixes, low risk, do now
1. **`import sys` shadow crash** — delete the two function-local imports
   (`executor/core.py:115,154`). Fixes the `break N` crash.
2. **`local` double-expansion injection** — remove the re-expansion in LocalBuiltin
   (`shell_state.py:177-179`); the executor already expanded the args.
3. **`${!prefix@}` wrong argument** — pass `var_name` not `operand`, drop the literal
   quotes (`variable.py:753-758`, `parameter_expansion.py:316-318`); tighten the weak
   integration assertions that masked it.
4. **Tombstone leak** — skip `var.is_unset` in `get_all_variables`/
   `all_variables_with_attributes` (`scope_enhanced.py:408-433`).
5. **`set -o a -o b` drops the second option** (`environment.py:319-360`); also silence
   `set -o vi` and drop the non-bash `edit_mode=` line from bare `set`.
6. **`export` validation** — reject non-identifiers, implement/route `-p`/`-n`
   (`environment.py:205-230`).
7. **`trap --` handling** (`signal_handling.py:105-113`).
8. **Brace expansion lost with heredocs** — add the `TokenBraceExpander` pass to
   `tokenize_with_heredocs` (`lexer/__init__.py:83-123`).
9. **Exception transparency** — re-raise LoopBreak/LoopContinue/UnboundVariableError in
   `strategies.py:75,136` (consider deriving control-flow exceptions from BaseException so
   broad excepts can never eat them).
10. **Restore order** — iterate `reversed()` in `restore_redirections`
    (`file_redirect.py:249-261`) and stop overwriting stream backups
    (`manager.py:117-124`).
11. **Doubled `psh: psh:` prefix** under `set -u` (`variable.py:77,297` /
    `command.py:188-217`).

### Tier 1 — high-impact, day-scale projects
1. **Transactional builtin redirection** (fixes the shell-killing `2>&1`, same-fd-twice,
   and error-path leaks together): track exactly the file objects psh opened and close only
   those; move setup inside the `try` with rollback of partial state; make `_saved_fds_list`
   per-call, not instance state (`io_redirect/manager.py`, `executor/command.py:544`).
2. **Apply external-command redirections exactly once, in the child** — drop the
   parent-level `with_redirections` for ExternalExecutionStrategy. Fixes `2>&1 >f` ordering
   and double-executed command substitutions in one change.
3. **errexit as a context-aware policy**: condition-context flag in ExecutionContext set
   around if/while/until conditions, `&&`/`||` non-final, and `!`; centralize the exit
   decision (currently in 5 places); make subshells inherit `state.options` +
   `last_exit_code` (`shell.py:55-68`); make `set -u` and readonly violations fatal
   non-interactively. Add `psh -c` conformance tests for every divergence in §4/§7 —
   currently zero errexit conformance tests.
4. **Multi-field expansion**: let the evaluator/`_expand_double_quoted_word` return a list
   of fields for `$@`, `${arr[@]}`, `${@:n}`, `${arr[@]@Q}` (zero fields for empty `"$@"`),
   reusing `_expand_at_with_affixes`; delete the duplicate for-loop array path
   (`control_flow.py:498`, `variable.py:1042/1083`).
5. **Small semantic fixes**: `exec` failure exits 127; `return` works in sourced files;
   `eval` preserves loop context (share the caller's visitor or thread loop_depth);
   heredoc >64KB via temp file.

### Tier 2 — medium projects
1. **`&` at the list level** per POSIX grammar (incl. control structures, reject `& &&`)
   + `skip_newlines()` after `|`; structural `ParseError.at_eof` flag to replace the
   ~40-pattern string matching in `source_processor.py:168-249`.
2. **Heredoc lexing redesign**: whole-input lexing + post-hoc body extraction, replacing
   per-line re-lexing; removes the double tokenization in source_processor too.
3. **Missing builtins/variables**: `umask` (currently a silent no-op on macOS!), `times`,
   `builtin`, scalar `+=` (parser), `PIPESTATUS`, `$PPID`/`$UID`/`$EUID`/`$EPOCHSECONDS`,
   `printf -v`, `printf %(fmt)T`, quoted-regex-as-literal in `=~`.
4. **DEBUG/ERR traps**: either wire `execute_debug_trap`/`execute_err_trap` into the
   executor or remove them from trap's accepted conditions and help text; defer trap
   execution to command boundaries (self-pipe pattern already exists).
5. **Dead-code purge** (continues the §1.4 theme): parser context machinery +
   execution_context triplets (~500 lines), lexer config fiction + dead operator table +
   wrong QUOTE_RULES escapes, phantom vi keybindings (implement or remove), dead
   `launch_job`, `_apply_attributes`; fix the lexer/executor CLAUDE.md errors found
   (dead operator table instructions, wrong strategy order, reversed() claim).
6. **Builtin infrastructure**: shared flag-parsing helper + `Builtin.write()` output helper
   (collapses 36 routing expressions + 9 forked-child dances); standardize usage errors to
   rc 2; consolidate the three array-literal parsers.

### Tier 3 — larger/architectural
- Single shared `shell.process_launcher` (removes the executor→interactive reach ×4).
- Remove `is_pytest` test-awareness from production terminal-control paths; replace
  blanket-xfail PTY suites with a small passing pexpect smoke set.
- Multi-row-aware line-editor rendering (wrap support).
- Quote-state consolidation in the lexer (one QuoteState; kill the quadratic backward scan);
  shrink `recognizers/literal.py`.
- Conformance suite expansion: errexit/nounset, traps, getopts, heredocs, fd-dup edges,
  select — and a CI rule that "Full support" claims in the user guide map to conformance
  tests (the project's own stated principle).
