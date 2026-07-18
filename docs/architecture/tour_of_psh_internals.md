# A Tour of psh Internals: One Command, Start to Finish

**Audience**: anyone who wants to understand how psh works inside —
students reading the shell as a reference implementation, and
contributors who want a mental map before opening a subsystem.

This document traces ONE concrete command through the entire pipeline:

```bash
echo "Hello, $USER" | wc -c > out.txt
```

The defining property of this tour is that **every illustration is
reproducible**. Each stage's artifact comes from a real psh debug flag
(or a two-line Python snippet against the public API), and the exact
command to regenerate it is shown next to the output. Where output is
trimmed, the trim is marked. Run the commands yourself — your PIDs and
username will differ, the shapes will not.

Where this tour says "what", each subsystem's own `CLAUDE.md` says "how
to change it", and `docs/architecture/ast_data_flow.md` gives the
per-context expansion pointers. ARCHITECTURE.md's Quick Map is the
companion overview.

---

## 1. The journey at a glance

ARCHITECTURE.md's Execution Pipeline, one line per phase:

```
Input → Preprocessing → Tokenization → Keyword Normalization → Parsing → [Validation] → Expansion → Visitor Execution → Exit Status
```

Our command at each stage:

| Stage | Our command becomes |
|---|---|
| Input | the string `echo "Hello, $USER" \| wc -c > out.txt`, unchanged (no continuations, no history, no braces) |
| Tokenization | 8 tokens; the quoted string is ONE token carrying two sub-parts |
| Keyword normalization | unchanged (no word is at command position AND a reserved word) |
| Parsing | `Program → AndOrList → Pipeline → [SimpleCommand, SimpleCommand]`, with a `Redirect` hanging off the second command |
| Expansion | `$USER` → `pwilson` inside the double quotes — one field, no splitting |
| Execution | two forked children in one process group: `echo` (builtin, runs in-process in its child), `wc` (external, applies `> out.txt` then execs) |
| Exit status | `wc`'s status (0); `PIPESTATUS=(0 0)`; `out.txt` contains `      15` |

Verify the end state first, so the rest of the tour has a known
destination:

```bash
$ python -m psh -c 'echo "Hello, $USER" | wc -c > out.txt; echo "exit=$? pipestatus=${PIPESTATUS[@]}"; cat out.txt'
exit=0 pipestatus=0 0
      15
```

(15 = `Hello, pwilson\n` — your byte count tracks your username.)

---

## 2. Input processing

Before the lexer sees anything, three preprocessing concerns get a
chance at the raw line. Our command needs none of them, so this stage
is an identity function here — but each is one sentence away:

- **Line continuations** — `process_line_continuations()` in
  `psh/scripting/input_preprocessing.py` joins `echo "Hello, \`
  + newline + `$USER"` back into one logical line before tokenization.
- **History expansion** — interactively, `!!` or `!wc` would be
  rewritten from the history list first
  (`psh/interactive/history_expansion.py`); `-c` mode skips this.
- **Brace expansion** — `echo out.{txt,log}` would be expanded — but
  note that in psh this happens *after* tokenization, on the token
  stream (`TokenBraceExpander` in `psh/expansion/brace_expansion.py`),
  so generated text is never re-lexed and quote context is available.
  It is listed here because POSIX puts it first conceptually; the
  mechanism lives at the end of `tokenize()`.

The driver for all of this is `psh/scripting/source_processor.py`,
which reads input (from `-c`, a script, or the interactive editor) and
pushes each complete command into the lexer→parser→executor pipeline.
"Is this command complete, or are more lines needed?" (multi-line
constructs, heredoc bodies, unclosed quotes) is answered by ONE oracle
shared with the interactive PS2 loop —
`psh/scripting/command_accumulator.py` — which trial-parses the buffer
with the real lexer and parser and reports *why* more input is needed.

---

## 3. Tokenization

The lexer entry point is `tokenize()` (`psh/lexer/__init__.py`), which
runs three passes: `ModularLexer` → `KeywordNormalizer` →
`TokenBraceExpander`. See `psh/lexer/CLAUDE.md` for the recognizer
architecture; this section shows what comes out.

```bash
$ python -m psh --debug-tokens -c 'echo "Hello, $USER" | wc -c > out.txt'
=== Token Debug Output ===
  [  0] WORD                 'echo'
  [  1] STRING               'Hello, $USER'
  [  2] PIPE                 '|'
  [  3] WORD                 'wc'
  [  4] WORD                 '-c'
  [  5] REDIRECT_OUT         '>'
  [  6] WORD                 'out.txt'
  [  7] EOF                  ''
========================
Hello, pwilson
```

(The command still runs after the dump — debug flags observe, they
don't intercept. The formatter is `psh/lexer/token_formatter.py`.)

Three things are worth noticing.

**`"Hello, $USER"` is ONE token.** The lexer does not emit
quote-open / text / variable / quote-close as separate tokens. When
`ModularLexer` meets a `"`, it hands the whole quoted region to
`UnifiedQuoteParser` (`psh/lexer/quote_parser.py`), which consumes it
in a single step — so no cross-token quote state exists anywhere in
the lexer. The `$USER` inside is recognized by `ExpansionParser`
(`psh/lexer/expansion_parser.py`). The result is a `RichToken`
(`psh/lexer/token_parts.py`): a token whose `parts` list records each
literal/expansion segment with its own quote context. `--debug-tokens`
shows only type and value; to see the parts, ask the token directly:

```bash
$ python -c "
from psh.lexer import tokenize
for p in tokenize('echo \"Hello, \$USER\" | wc -c > out.txt')[1].parts:
    print(p)"
TokenPart(value='Hello, ', quote_type='"', is_variable=False, is_expansion=False, expansion_type=None, ...)
TokenPart(value='USER', quote_type='"', is_variable=True, is_expansion=True, expansion_type='variable', ...)
```

(Each `TokenPart` also carries `error_message`, `start_pos`, `end_pos`
fields, trimmed here.) This per-part structure — "the text `Hello, `
and the variable `USER`, both inside double quotes" — is the seed of
everything that follows: the parser turns it into the Word AST, and
the expander reads the quote context off each part to decide what
expands and what splits.

**`|` and `>` become operators, not text.** `OperatorRecognizer`
(`psh/lexer/recognizers/operator.py`) matches against its operator
table longest-first (so `>>` wins over `>`), producing `PIPE` and
`REDIRECT_OUT` tokens. Recognizers are tried in one explicit
registration order — process substitution before operators so `<(`
isn't read as `<`, operators before literals so `|` terminates the
word `-c` rather than joining it.

**The lexer tracks command position.** `LexicalState.command_position`
(`psh/lexer/state_context.py`) is true at the start of a command and
after `|`, `;`, `&&` — and false after a word. Our line toggles it:
true at `echo`, false at the string, true again at `wc` after the
pipe. Nothing in this command uses it visibly, but it is what makes
the next stage work. The vocabulary of which tokens reset command
position lives in `psh/lexer/command_position.py` — a good first file
to read in the whole lexer.

---

## 4. Keyword normalization

Why does `tokenize()` run a second pass at all? Because shell keywords
are contextual: `if` is a reserved word at command position and an
ordinary argument elsewhere. The lexer's recognizers emit every name
as a plain `WORD`; `KeywordNormalizer`
(`psh/lexer/keyword_normalizer.py`) then retypes WORD tokens that are
(a) reserved words and (b) at command position. Two lines show the
whole idea:

```bash
$ python -m psh --debug-tokens -c 'if true; then echo yes; fi' 2>&1 | head -3
=== Token Debug Output ===
  [  0] IF                   'if'
  [  1] WORD                 'true'

$ python -m psh --debug-tokens -c 'echo if' 2>&1 | head -3
=== Token Debug Output ===
  [  0] WORD                 'echo'
  [  1] WORD                 'if'
```

Same characters, different token types — the difference is purely the
command-position state. Our pipeline contains no reserved words, so
this pass returns the token list unchanged. (Matching is
case-sensitive, like bash: `IF` is always a plain WORD. The
keyword→TokenType table is `KEYWORD_TYPE_MAP` in
`psh/lexer/keyword_defs.py`.)

---

## 5. Parsing

The recursive descent parser (`psh/parser/recursive_descent/`; see
`psh/parser/CLAUDE.md`) turns the token list into an AST. The default
tree view shows the shape:

```bash
$ python -m psh --debug-ast -c 'echo "Hello, $USER" | wc -c > out.txt'
=== AST Debug Output (recursive_descent) ===
└── Program
    └── statements: [1 items]
        └── AndOrList
            └── pipelines: [1 items]
                └── Pipeline
                    ├── commands: [2 items]
                    │   ├── SimpleCommand
                    │   │   └── arguments: echo (literal), "Hello, $USER" (quoted, ")
                    │   └── SimpleCommand
                    │       ├── arguments: wc (literal), -c (literal)
                    │       └── redirects: [1 items]
                    │           └── Redirect
                    │               ├── target: "out.txt"
                    │               └── type: ">"
                    └── pipe_stderr: [1 items]
                        └── • false
======================
Hello, pwilson
```

The descent mirrors the grammar: `StatementParser.parse_and_or_list`
(`psh/parser/recursive_descent/parsers/statements.py`) looks for
`&&`/`||` chains (ours has none — one pipeline), `parse_pipeline()`
(`psh/parser/recursive_descent/parsers/commands.py`) collects
`|`-separated commands, and `parse_command()` builds each
`SimpleCommand`. Every parse yields a single `Program` root, and even a
lone `echo hi` gets the full `Program→AndOrList→Pipeline` wrapping (a
bare compound is not unwrapped) — uniformity is cheaper than special
cases, and the executor short-circuits single-command pipelines anyway
(§7).

Two details deserve a closer look, and for them
`--debug-ast=pretty` prints every field. Its output is one long
line per statement; trimmed to the two interesting fragments
(`...` marks trims):

```bash
$ python -m psh --debug-ast=pretty -c 'echo "Hello, $USER" | wc -c > out.txt'
SimpleCommand(args=['echo', 'Hello, $USER'], ...,
  words=[Word(parts=[LiteralPart(text='echo', quoted=False, quote_char=None)], quote_type=None),
         Word(parts=[LiteralPart(text='Hello, ', quoted=True, quote_char='"'),
                     ExpansionPart(expansion=VariableExpansion(name='USER'), quoted=True, quote_char='"')],
              quote_type='"')])
...
SimpleCommand(args=['wc', '-c'],
  redirects=[Redirect(type='>', target='out.txt', fd=None, dup_fd=None, heredoc_content=None,
                      quote_type=None, heredoc_quoted=False, combined=False)], ...)
```

**The Word AST.** Each argument is a `Word` (`psh/ast_nodes/words.py`)
whose parts carry per-part quote context — a direct translation of the
lexer's `TokenPart` list from §3. `WordBuilder`
(`psh/parser/recursive_descent/support/word_builder.py`) does that
translation: `CommandParser.parse_argument_as_word` hands it each
argument token, and `WordBuilder.build_word_from_token` decomposes the
RichToken's parts into `LiteralPart` / `ExpansionPart` nodes —
including parsing `$USER` into a structured
`VariableExpansion(name='USER')` rather than leaving a `$USER` string
for later re-scanning. Note `quoted=True, quote_char='"'` on the
expansion part: that single field is what will prevent word splitting
in §6. `Word.is_quoted` and friends are the semantic accessors;
`SimpleCommand.words` is the sole structural argument representation
(an architecture invariant — there are no parallel type strings to
drift out of sync).

**The redirect.** `> out.txt` does NOT become an argument of `wc`.
`_parse_command_elements()` recognizes redirect operators while
collecting arguments and routes them to `RedirectionParser`
(`psh/parser/recursive_descent/parsers/redirections.py`), which builds
a `Redirect(type='>', target='out.txt')` attached to the
`SimpleCommand`. The target stays a plain string by design — redirect
targets are a string-expansion context, not a Word context (see
`docs/architecture/ast_data_flow.md` §6) — with `quote_type`
metadata recording how it was quoted (here: not at all).

The AST is pure data: no behavior lives on the nodes. Everything from
here on is visitors walking it (`psh/visitor/CLAUDE.md`).

---

## 6. Expansion

Expansion runs at execution time, per command (for pipeline members,
inside each forked child — see §7). The orchestrator is
`ExpansionManager.expand_arguments` (`psh/expansion/manager.py`); the
engine that walks Word parts is `WordExpander.expand_to_word` (the
field IR producer; `WordExpander.materialize` is the IR→argv boundary)
(`psh/expansion/word_expander.py`). See `psh/expansion/CLAUDE.md` for
the subsystem and `docs/architecture/ast_data_flow.md` for every
context that feeds it.

```bash
$ python -m psh --debug-expansion -c 'echo "Hello, $USER" | wc -c > out.txt'
[EXPANSION] Expanding Word AST command: ['echo', '"Hello, $USER"']
[EXPANSION] Expanding Word AST command: ['wc', '-c']
[EXPANSION] Word AST Result: ['wc', '-c']
[EXPANSION] Word AST Result: ['echo', 'Hello, pwilson']
```

(The interleaving is real: the two pipeline children expand their
arguments concurrently, so the order of these four lines can vary
run to run.)

`$USER` expanded; the result stayed ONE field, `Hello, pwilson`,
spaces and all. Why no splitting? Two independent decisions compose:

1. **The policy says what the *context* permits.** Command arguments
   expand under the named policy `COMMAND_ARGUMENT` — from the policy
   table at the top of `psh/expansion/word_expander.py`:

   | Policy | split | glob | assignment_tilde |
   |---|---|---|---|
   | `COMMAND_ARGUMENT` | yes | yes | yes |
   | `LOOP_ITEM` | (alias of COMMAND_ARGUMENT) | | |
   | `DECLARATION_ASSIGNMENT` | no | no | yes |
   | `ARRAY_INIT_ELEMENT` | yes | yes | no |
   | `ASSOC_INIT_ELEMENT` | no | no | yes |

   So splitting is *permitted* here. (Other contexts differ:
   `declare v=$x` expands under `DECLARATION_ASSIGNMENT`, which never
   splits.)

2. **The part's quote context says what the *text* allows.** The
   walker splits only text that came from **unquoted** expansion
   parts (POSIX: quoted expansions are never field-split). Our
   `ExpansionPart` carries `quoted=True, quote_char='"'` from §5, so
   its result is excluded from the splittable set, and the word
   survives as one field.

The contrast, reproducible in one line — same policy, different quote
context:

```bash
$ python -m psh --debug-expansion -c 'greeting="Hello,   $USER"; echo "$greeting"; echo $greeting'
[EXPANSION] Expanding Word AST command: ['echo', '"$greeting"']
[EXPANSION] Word AST Result: ['echo', 'Hello,   pwilson']
Hello,   pwilson
[EXPANSION] Expanding Word AST command: ['echo', '$greeting']
[EXPANSION] Word AST Result: ['echo', 'Hello,', 'pwilson']
Hello, pwilson
```

Quoted: one argument, inner spaces preserved. Unquoted: IFS splitting
breaks it into two arguments, and the spacing is gone. Had the value
contained `*`, the unquoted form would also have hit pathname
expansion (the policy's `glob` axis) — quoting suppresses both, and
both suppressions are read off the same per-part `quoted` flag.

Note what does NOT happen here: `> out.txt` is not expanded in this
phase. Redirect targets are flat strings expanded at apply time by
`FileRedirector.expand_redirect_target`
(`psh/io_redirect/file_redirect.py`) — in this case inside `wc`'s
child, just before the file is opened (§7).

---

## 7. Execution

Execution is the visitor walk: `ExecutorVisitor`
(`psh/executor/core.py`) dispatches `visit_Pipeline` →
`PipelineExecutor` (`psh/executor/pipeline.py`), and each command
inside dispatches `visit_SimpleCommand` → `CommandExecutor`
(`psh/executor/command.py`). See `psh/executor/CLAUDE.md` and, for the
redirect side, `psh/io_redirect/CLAUDE.md`. The trace:

```bash
$ python -m psh --debug-exec -c 'echo "Hello, $USER" | wc -c > out.txt'
DEBUG: Not running on a terminal (stdin is not a TTY)
DEBUG source_processor: read line: 'echo "Hello, $USER" | wc -c > out.txt'
DEBUG Pipeline: Original terminal PGID: None
DEBUG ProcessLauncher: Child 93266 is pipeline leader
DEBUG ProcessLauncher: Parent set child 93267 to pgid 93266
DEBUG Pipeline: Process group synchronization complete, pgid=93266
DEBUG ProcessLauncher: Child 93267 synchronized, pgid=93266
DEBUG BuiltinStrategy: executing builtin 'echo' with args ['Hello, pwilson']
DEBUG BuiltinStrategy: in_pipeline=True, in_forked_child=True
DEBUG EchoBuiltin: in_forked_child=True
DEBUG EchoBuiltin: Writing text: 'Hello, pwilson\n'
DEBUG ExternalStrategy: Before exec - PID=93267, PGID=93266
DEBUG source_processor: read line: None
```

(PIDs vary per run; under a real terminal the `PGID: None` line shows
the shell's process group instead.) Reading it top to bottom:

**Pipes and forks.** `PipelineExecutor` creates one `os.pipe()` per
`|`, plus a *sync pipe*, then forks one child per command via the
single shared `ProcessLauncher` (`psh/executor/process_launcher.py`).
A one-command pipeline skips all of this and runs the command
directly — that's why a bare `echo hi` shows none of these lines.

**Process-group choreography.** The first child launches with role
`ProcessRole.PIPELINE_LEADER` and becomes its own process group
(`Child 93266 is pipeline leader`); job control signals (Ctrl-C,
Ctrl-Z) can then target the whole pipeline as a unit. Each later
child launches as `ProcessRole.PIPELINE_MEMBER` and **blocks on the
sync pipe** while the *parent* assigns it to the leader's group
(`Parent set child 93267 to pgid 93266`); only when the parent closes
the pipe do members proceed (`synchronized, pgid=93266`). This closes
the classic race where a member runs — or receives a signal — before
the group exists. The mechanics live in `ProcessLauncher.launch` and
`ProcessLauncher._child_setup_and_exec`.

**Every fork is hygienic.** The fork itself goes through
`fork_with_signal_window()` (`psh/executor/child_policy.py`), which
blocks termination signals across the fork so none can be swallowed
by an inherited Python handler and lost across exec; each child then
runs `apply_child_signal_policy()` — reset handlers to SIG_DFL,
unblock. `child_policy.py` is 200 lines and narrates the whole
problem; it is the recommended read on this stage.

**Strategy selection — why echo and wc take different paths.** Inside
each child, `CommandExecutor` expands the arguments (§6 — this is why
expansion of pipeline members happens post-fork) and tries execution
strategies in POSIX lookup order (`psh/executor/strategies.py`):
special builtins → functions → builtins → aliases → external.

- `echo` matches `BuiltinExecutionStrategy`: it runs as Python code
  *inside* the forked child — no exec. Because
  `state.in_forked_child` is set, `Builtin.write`
  (`psh/builtins/base.py`) writes with `os.write(1, ...)` at the fd
  level instead of `shell.stdout`, so the bytes go down the real
  pipe fd that the pipeline plumbing installed
  (`_setup_pipeline_redirections()` dup2'ed the pipe's write end onto
  fd 1 before the strategy ran).
- `wc` matches no builtin and falls through to
  `ExternalExecutionStrategy`. In a pipeline child it first applies
  the command's redirects via `IOManager.setup_child_redirections`
  (`psh/io_redirect/manager.py`): the target string `out.txt` is
  expanded (§6's deferred string context), the file is opened, and
  dup2'ed onto fd 1 — *replacing* the pipe-output plumbing for this
  child only; fd 0 keeps the pipe's read end. Then `exec_external()`
  calls `os.execvpe` with `shell.env` (`Before exec - PID=93267`) and
  the Python process becomes `wc`. If the binary were missing, the
  child would exit 127 without ever returning into shell code.

**Exit-status collection.** The parent registers the two PIDs as a
job (`JobManager`, `psh/executor/job_control.py`) and
`PipelineExecutor._wait_for_foreground_pipeline` waits for ALL
members via `JobManager.wait_for_job`, storing every status in
`ShellState.pipestatus` — that is the `pipestatus=0 0` from §1. The
pipeline's own status is the LAST command's (POSIX), or the rightmost
non-zero one under `set -o pipefail`. That integer propagates back up
the visitor returns — every execution path in psh returns an exit
status — and lands in `$?`.

The final picture, with the fds each process ends up holding:

```
psh (parent) ──fork──> child A (pgid L): echo builtin, fd1 = pipe write end
            └─fork──> child B (pgid L): fd0 = pipe read end, fd1 = out.txt, exec wc
            └─ waits for both → pipestatus=[0, 0] → $? = 0
```

---

## 8. Epilogue: now trace it yourself

Three variations, each one debug command away. Each exercises a
subsystem this command skipped.

**Command substitution.** Change the string to
`'echo "Today: $(date +%Y)" | wc -c > out.txt'` and rerun
`python -m psh --debug-exec -c '...'`. During §6's expansion — inside
echo's pipeline child — you'll see a *third* fork appear
(`Child ... is single command`) and a nested
`source_processor: read line: 'date +%Y'`: command substitution
(`psh/expansion/command_sub.py`) forks a child whose body is run by
the shared `run_child_shell()` runner in `psh/executor/child_policy.py`
(child Shell via `Shell.for_subshell`, exception→exit-code mapping,
stream flush, `os._exit`), captures its stdout through a pipe, and
splices the text into the word. Substitution children deliberately do
NOT go through `ProcessLauncher` — they are not jobs.

**Process substitution.** Run
`python -m psh --debug-expansion -c 'wc -c <(echo hi)'` and then the
same with `--debug-ast=pretty`. The AST shows the argument as a Word
containing
`ExpansionPart(expansion=ProcessSubstitution(direction='in', command='echo hi'))`
— procsub is an ordinary expansion part — and the expansion trace
shows the word becoming `/dev/fd/3`: `WordExpander` asked
`IOManager.create_process_substitution_for_expansion()`
(`psh/io_redirect/process_sub.py`) to fork the producer (again via
`run_child_shell()`) and hand back a path to the pipe. The
parent-side fd and child are owned by the enclosing
`process_sub_scope()` (`psh/io_redirect/manager.py`), which closes
and reaps them when the command finishes — note how ownership is a
*scope*, not a per-call cleanup.

**A for loop.** Run
`python -m psh --debug-tokens -c 'for f in a b; do echo "$f"; done'`
and watch §4 earn its keep: `FOR`, `IN`, `DO`, `DONE` arrive as
keyword tokens, while the same letters in `echo for` would stay
WORDs. Then add `--debug-ast`: the items become `ForLoop.item_words`
— real Words — and at execution
`ControlFlowExecutor._expand_loop_items()`
(`psh/executor/control_flow.py`) expands each under the `LOOP_ITEM`
policy from §6's table (an alias of `COMMAND_ARGUMENT`, because bash
treats loop items exactly like command arguments). One Word in the
list can become zero, one, or many iterations — the policy table says
why.

---

## Where to go next

| You want | Read |
|---|---|
| the full component map | ARCHITECTURE.md (Quick Map) |
| lexer internals (recognizers, quotes, RichToken) | `psh/lexer/CLAUDE.md` |
| parser internals (sub-parsers, WordBuilder) | `psh/parser/CLAUDE.md` |
| every expansion context and its policy | `docs/architecture/ast_data_flow.md`, `psh/expansion/CLAUDE.md` |
| execution, processes, signals, job control | `psh/executor/CLAUDE.md`, `psh/executor/child_policy.py` |
| redirections and the two I/O universes | `psh/io_redirect/CLAUDE.md` |
| state, scopes, variables | `psh/core/CLAUDE.md` |
| the visitor pattern itself | `psh/visitor/CLAUDE.md` |

Every pointer in this document is checked by the doc-pointer meta-test
(`tests/unit/tooling/test_doc_pointers.py`) — if the tour and the tree
ever disagree, the suite fails.
