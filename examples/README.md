# PSH Examples

A small, curated set of shell scripts used throughout the PSH
documentation. Each one is runnable under `psh` and doubles as input for
PSH's built-in analysis tools (`--metrics`, `--validate`, `--security`,
`--lint`, `--format`, `--debug-ast`).

Run any example from the repository root:

```bash
psh examples/fibonacci.sh 10
python -m psh examples/fibonacci.sh 10   # if psh is not on your PATH
```

## The scripts

| Script | Demonstrates | Try it with |
|--------|--------------|-------------|
| [`shell_basics.sh`](shell_basics.sh) | Variables, quoting, parameter/arithmetic expansion, command substitution, pipelines, word splitting | `psh --format`, `psh --debug-tokens -c …` |
| [`fibonacci.sh`](fibonacci.sh) | Functions, recursion vs. iteration, arithmetic, loops | `psh --metrics`, `psh --validate` |
| [`control_structures.sh`](control_structures.sh) | `if`/`while`/`for`/`case`, `break`/`continue`, nesting | `psh --debug-ast`, `psh --metrics` |
| [`text_stats.sh`](text_stats.sh) | A realistic utility: `getopts`, functions, `read` loops, `set -u`, formatted output | `psh --metrics`, `psh --lint` |
| [`security_demo.sh`](security_demo.sh) | **Intentionally insecure** anti-patterns | `psh --security`, `psh --lint` |

> ⚠️ **`security_demo.sh` is deliberately vulnerable.** It exists only so the
> analyzers have something to flag. Do not run it against real paths and do
> not copy its patterns.

## Analyzing a script

The analysis tools read a script, parse it, and report without executing it:

```bash
# Complexity and command counts
psh --metrics examples/fibonacci.sh

# Static validation (parse + AST checks), no execution
psh --validate examples/fibonacci.sh

# Security scan — exits non-zero when issues are found
psh --security examples/security_demo.sh

# Style and robustness suggestions
psh --lint examples/text_stats.sh

# Inspect the parsed syntax tree
psh --debug-ast examples/control_structures.sh
```

A note on the validators: `--validate`, `--lint`, and `--security` are
conservative static analyzers. They sometimes flag intentional, correct
patterns (for example, the deliberate word-splitting `set -- $line` in
`text_stats.sh`) — a reminder that static analysis trades precision for
catching whole classes of mistake.

## Where to go next

These scripts are referenced from the project [`README.md`](../README.md)
and pair well with the architecture tour in
[`docs/architecture/tour_of_psh_internals.md`](../docs/architecture/tour_of_psh_internals.md),
which traces a single command through the lexer, parser, and executor.
