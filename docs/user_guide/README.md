# PSH User's Guide

Welcome to the Python Shell (PSH) User's Guide. This comprehensive guide covers all features of PSH, an educational Unix shell implementation designed for learning shell internals and compiler/interpreter concepts.

## Table of Contents

1. [Introduction](01_introduction.md)
2. [Getting Started](02_getting_started.md)
3. [Basic Command Execution](03_basic_command_execution.md)
4. [Built-in Commands](04_builtin_commands.md)
5. [Variables and Parameters](05_variables_and_parameters.md)
6. [Expansions](06_expansions.md)
7. [Arithmetic](07_arithmetic.md)
8. [Quoting and Escaping](08_quoting_and_escaping.md)
9. [Input/Output Redirection](09_io_redirection.md)
10. [Pipelines and Lists](10_pipelines_and_lists.md)
11. [Control Structures](11_control_structures.md)
12. [Functions](12_functions.md)
13. [Shell Scripts](13_shell_scripts.md)
14. [Interactive Features](14_interactive_features.md)
15. [Job Control](15_job_control.md)
16. [Advanced Features](16_advanced_features.md)
17. [Differences from Bash](17_differences_from_bash.md)
18. [Troubleshooting](18_troubleshooting.md)

## Appendices

- [A. Quick Reference Card](appendix_a_quick_reference.md)
- [B. Example Scripts](appendix_b_example_scripts.md)
- [C. Regular Expression Reference](appendix_c_regex_reference.md)
- [D. ASCII Character Set](appendix_d_ascii_chart.md)
- [E. Glossary of Terms](appendix_e_glossary.md)

## How to Use This Guide

Each chapter builds upon previous concepts. Beginners should read chapters 1-5 sequentially, while experienced shell users can jump to specific topics of interest.

### Notation Conventions

- `$` indicates a shell prompt
- `...` indicates output has been truncated
- `[optional]` indicates optional elements
- `<required>` indicates required elements
- Code examples are shown in monospace font

### Version

This guide tracks the current PSH release (the canonical version lives in `psh/version.py`; run `psh --version` to check yours). PSH features a hand-written recursive descent parser, near-complete POSIX compliance (~98%), comprehensive signal handling via `trap`, arrays (indexed and associative), process substitution, and extensive debugging options.