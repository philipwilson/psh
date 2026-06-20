# Learning Path: Reading PSH

PSH is an educational Unix shell. This is the recommended route through the
codebase and docs — from "what is it" to "how does every stage work" — so you
don't have to guess which document to read next.

Work top to bottom; each step builds on the last. Everything links to a file
that exists in this repo.

## 1. Orientation — what PSH is

- [`README.md`](../README.md) — overview, feature set, install, and the CLI
  analysis tools (`--metrics`, `--security`, `--lint`, `--format`).

Install it, then run something.

## 2. Run it and look inside

Run the curated example scripts and watch the shell think:

- [`examples/`](../examples/) — five small, runnable, commented scripts; see
  [`examples/README.md`](../examples/README.md) for what each one teaches.

```bash
psh examples/shell_basics.sh            # everyday expansion, run it
psh --debug-tokens -c 'echo "hi $USER"' # 1) lexing: the token stream
psh --debug-ast    examples/control_structures.sh  # 2) parsing: the AST
psh --metrics      examples/fibonacci.sh           # a visitor over that AST
```

Those three flags map onto the three stages you'll read about next.

## 3. The big picture

- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — start with the **Quick Map** at the
  top, then the component overview. This is the mental model: input →
  line-continuation → tokenize → parse → expand → execute.

## 4. One command, end to end

- [`docs/architecture/tour_of_psh_internals.md`](architecture/tour_of_psh_internals.md)
  — a narrative that traces a single command through every stage, with output
  regenerated from the real debug flags (you can reproduce each illustration).
  This is the best single document for seeing how the pieces connect.

## 5. The data model that makes it all work

- [`docs/architecture/ast_data_flow.md`](architecture/ast_data_flow.md) — how
  the `Word` AST carries quote/expansion structure, and how expansion contexts
  (command argument vs. assignment vs. loop item) are named rather than guessed.
  Understanding `Word` is the key that unlocks the expansion and executor code.

## 6. Go deep, one subsystem at a time

Each subsystem has a focused `CLAUDE.md`. These are written as
contributor/agent guidance, but they double as the deepest per-area reference.
Read the ones for the area you're studying:

| Subsystem | Doc | Covers |
|-----------|-----|--------|
| Lexer | [`psh/lexer/CLAUDE.md`](../psh/lexer/CLAUDE.md) | tokenization, recognizers, quote/expansion parsing |
| Parser | [`psh/parser/CLAUDE.md`](../psh/parser/CLAUDE.md) | recursive-descent parsing, AST construction |
| Expansion | [`psh/expansion/CLAUDE.md`](../psh/expansion/CLAUDE.md) | variable/command/arithmetic/glob expansion, word splitting |
| Executor | [`psh/executor/CLAUDE.md`](../psh/executor/CLAUDE.md) | command execution, pipelines, process & signal policy |
| I/O redirection | [`psh/io_redirect/CLAUDE.md`](../psh/io_redirect/CLAUDE.md) | redirections, heredocs, process substitution |
| Core/state | [`psh/core/CLAUDE.md`](../psh/core/CLAUDE.md) | shell state, variables, scopes, options |
| Builtins | [`psh/builtins/CLAUDE.md`](../psh/builtins/CLAUDE.md) | built-in commands, registration |
| Visitor | [`psh/visitor/CLAUDE.md`](../psh/visitor/CLAUDE.md) | the visitor pattern over the AST (executor + analysis tools) |
| Interactive | [`psh/interactive/CLAUDE.md`](../psh/interactive/CLAUDE.md) | REPL, line editing, history, job control |

There are two deliberate parser implementations — the production
recursive-descent parser and an educational parser-combinator alternative; the
parser docs explain why, and let you compare imperative vs. functional parsing.

## 7. Compatibility and behavior

- [`docs/user_guide/`](user_guide/) — feature-by-feature behavior and the
  POSIX/bash compatibility tables.
- Conformance tests in `tests/conformance/` prove the documented behavior
  against live bash; see the "Development Principles" in the root
  [`CLAUDE.md`](../CLAUDE.md).

## 8. Contributing / running the tests

- [`docs/testing_source_of_truth.md`](testing_source_of_truth.md) — the
  canonical test commands and the (local) release gate.
- [`tests/README.md`](../tests/README.md) — the test-suite layout.
- The root [`CLAUDE.md`](../CLAUDE.md) — workflow, conventions, and the
  subsystem map.

## Where NOT to start

[`docs/reviews/`](reviews/) holds development-history audits and design notes.
They are point-in-time artifacts, not a tutorial — see
[`docs/reviews/README.md`](reviews/README.md) for which (few) are live
references. You do not need them to learn PSH; this page is the route.
