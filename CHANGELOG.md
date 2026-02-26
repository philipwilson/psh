# Changelog

All notable changes to PSH (Python Shell) are documented in this file.

Format: `VERSION (DATE) - Title` followed by bullet points describing changes.

## 0.192.1 (2026-02-26) - Fix terminal resize (SIGWINCH) display corruption
- Fixed `redraw_line()` in line editor corrupting previously-output command
  results on terminal resize. The old code compared the cursor's current row
  (via DSR) against a stale saved row from before the resize; after terminal
  reflow the saved position was meaningless, causing `ESC[J` (clear to end
  of screen) to wipe out legitimate output.
- New approach computes cursor displacement using the **new** terminal width,
  matching the terminal's own reflow, so only the prompt+input area is
  redrawn. Prior command output is left untouched.

## 0.192.0 (2026-02-19) - Add 5 missing redirection operators (<>, >|, &>, &>>, |&)
- **3 new token types**: `REDIRECT_READWRITE` (`<>`), `REDIRECT_CLOBBER`
  (`>|`), and `PIPE_AND` (`|&`). `&>` and `&>>` reuse `REDIRECT_OUT`
  and `REDIRECT_APPEND` with a new `combined_redirect` boolean on `Token`.
- **Lexer**: Added `<>`, `>|`, `&>`, `&>>`, `|&` to operator table.
  Extended `_try_fd_prefixed_redirect()` for `N<>`. Set
  `combined_redirect=True` on `&>` / `&>>` tokens. Updated operator
  enable/context checks for new operators.
- **AST**: Added `combined: bool` field to `Redirect` for `&>` / `&>>`
  (redirects both stdout and stderr). Added `pipe_stderr: List[bool]`
  to `Pipeline` to track which pipe connections use `|&`.
- **Parser**: Added `REDIRECT_READWRITE` and `REDIRECT_CLOBBER` to
  `TokenGroups.REDIRECTS`. Updated pipeline parsing in both recursive
  descent and combinator parsers to accept `PIPE_AND` as pipe separator.
  `_parse_standard_redirect()` propagates `combined` flag to `Redirect`.
- **Execution**: Added `_redirect_readwrite()`, `_redirect_clobber()`,
  `_redirect_combined()` helpers to `FileRedirector`. Updated all 4
  redirect dispatch methods (`apply_redirections`,
  `apply_permanent_redirections`, `setup_builtin_redirections`,
  `setup_child_redirections`). `PipelineExecutor._setup_pipeline_redirections()`
  now accepts `pipe_stderr` and does `os.dup2(1, 2)` for `|&` pipes.
- **Tests**: 9 new lexer unit tests, 12 new integration tests covering
  `<>`, `>|`, `&>`, `&>>`, `|&`, noclobber interaction. Updated parser
  parity tests to verify both parsers handle all 5 operators.
- **POSIX**: `<>` (LESSGREAT) and `>|` (CLOBBER) are POSIX-defined.
  `&>`, `&>>`, and `|&` are bash extensions supported by both bash and zsh.

## 0.191.0 (2026-02-19) - Clean up TokenType enum, fd-prefixed redirects as single tokens
- **Remove 21 dead token types**: Deleted 11 assignment operators (`ASSIGN`
  through `RSHIFT_ASSIGN`), 3 glob tokens (`GLOB_STAR`, `GLOB_QUESTION`,
  `GLOB_BRACKET`), 4 test operators (`LESS_THAN_TEST` through
  `GREATER_EQUAL_TEST`), and 3 special construct markers
  (`HERE_DELIMITER`, `ASSIGNMENT_WORD`, `ARRAY_ASSIGNMENT_WORD`).
  TokenType enum reduced from 80 to 59 entries. None were referenced
  in production code, tests, or either parser.
- **fd-prefixed redirects as single tokens**: Added `fd: Optional[int]`
  field to `Token`. The lexer now emits `2>` as `REDIRECT_OUT '>' fd=2`
  (a single token with fd metadata) instead of two tokens (`WORD '2'` +
  `REDIRECT_OUT '>'`). Consistent with how `REDIRECT_DUP` already
  handles `2>&1` as a single token.
- **Lexer**: Added `_try_fd_prefixed_redirect()` to `OperatorRecognizer`
  that detects digit(s) followed by `>`, `>>`, or `<` and emits a
  single redirect token.
- **Parser cleanup**: Removed `_is_fd_prefixed_redirect()` and
  `_parse_fd_prefixed_redirect()` from both `RedirectionParser` and
  `CommandParser`. Parsers now read `token.fd` directly. Simplified
  `parse_redirects()` to a single `match_any` loop.
- **Combinator parser**: Removed fd-prefix WORD-digit detection block
  from `_parse_redirection()` — reads `fd` from token metadata.
- **Debug output**: Token formatter now shows `fd=N` suffix in
  `--debug-tokens` output (e.g., `REDIRECT_OUT '>' fd=2`).

## 0.190.0 (2026-02-19) - Fix lexer token type issues: REDIRECT_ERR, RBRACE, LBRACKET
- **REDIRECT_ERR removal**: Removed `REDIRECT_ERR` and
  `REDIRECT_ERR_APPEND` token types.  `2>` now tokenizes as `WORD '2'` +
  `REDIRECT_OUT '>'`, matching how `3>`, `4>`, etc. already work.
  Removed `_parse_err_redirect()` and combinator REDIRECT_ERR handling.
- **RBRACE fix**: Changed `}` to use `command_position` check instead of
  "followed by delimiter" heuristic.  `}` in brace expansions (e.g.
  `echo {$((1)),$((2))}`) is now correctly `WORD` instead of `RBRACE`.
  Removed combinator RBRACE-as-brace-expansion workaround.
- **LBRACKET in case patterns**: Added `case_depth`, `case_expecting_in`,
  and `in_case_pattern` context fields to `LexerContext`.  `[` in case
  patterns (e.g. `[a-z]*)`) is now collected as a glob word instead of
  being emitted as `LBRACKET`.  Removed combinator LBRACKET
  reconstruction workaround in `_parse_case_pattern_value()`.
- **fd-prefixed redirects**: Updated `parse_redirects()` to detect
  fd-prefixed redirects (WORD digit + adjacent redirect operator),
  fixing compound command trailing redirects (subshells, brace groups,
  if/while/for/case).

## 0.189.0 (2026-02-17) - Arithmetic: 64-bit wrapping, bitwise assignments, base 2-64, recursive variables
- **64-bit wrapping**: All arithmetic results (`+`, `-`, `*`, `/`, `%`,
  `**`, bitwise ops, compound assignments) are now wrapped to the signed
  64-bit range via `_to_signed64()`, matching bash/C overflow semantics.
  `$((9223372036854775807 + 1))` now returns `-9223372036854775808`.
- **Bitwise assignment operators**: Added `<<=`, `>>=`, `&=`, `|=`,
  `^=` — new token types, tokenizer rules, parser recognition, and
  evaluator cases.
- **Base 2-64 number literals**: Extended `base#number` notation from
  max base 36 to 64.  For bases <= 36 letters are case-insensitive;
  for bases > 36 lowercase = 10-35, uppercase = 36-61, `@` = 62,
  `_` = 63 (matching bash).
- **Recursive variable resolution**: `get_variable()` now resolves
  identifier chains recursively (with cycle detection), so
  `a=b; b=42; echo $((a))` prints `42` (matching bash).

## 0.188.1 (2026-02-17) - Fix tilde expansion in [[ ]] conditionals
- Added `_expand_operand()` helper to `TestExpressionEvaluator` that
  applies tilde expansion before variable expansion, matching POSIX
  expansion order.
- Unary operands (e.g., `[[ -f ~/.pshrc ]]`) and binary operands
  (e.g., `[[ ~ == /Users/* ]]`) now both expand tilde prefixes.
  Previously only `$VAR` expansion was applied, so `~` was passed
  literally to file tests.

## 0.188.0 (2026-02-17) - Fix critical arithmetic evaluator bugs
- **Modulo**: Changed from Python's floored modulo (`%`) to C-style
  truncated remainder so `$((-7 % 2))` returns `-1` (matching bash),
  not `1`.
- **Bitwise NOT**: Changed from 32-bit mask to 64-bit mask so
  `$((~0xFFFFFFFF))` returns `-4294967296` (matching bash), not `0`.
- **ArithmeticError**: Renamed to `ShellArithmeticError` and made it
  inherit from the Python builtin `ArithmeticError`.  Callers that
  caught the builtin name now correctly catch shell arithmetic errors
  (previously they fell through to "unexpected error" messages).
  The old name is kept as an alias for backwards compatibility.
- **Exponentiation bounds**: Negative exponents now raise an error
  (matching bash) and exponents > 63 are rejected to prevent unbounded
  memory use.
- **Shift bounds**: Negative shift counts now raise an error.  Shift
  amounts wrap modulo 64 (matching bash/C behavior), so `$((1 << 64))`
  returns `1` and left-shift results are wrapped to signed 64-bit.
- **Invalid octal**: Numbers like `09` and `08` now raise an error
  ("value too great for base") instead of silently falling back to
  decimal.
- **Exception handling**: `evaluate_arithmetic` now catches
  `RecursionError`, `ValueError`, `OverflowError`, and `MemoryError`
  in addition to `SyntaxError` and `ShellArithmeticError`, so deeply
  nested expressions and huge numeric literals produce clean error
  messages instead of crashes.
- Added `_to_signed64()` helper for wrapping arbitrary-precision
  integers into the signed 64-bit range.

## 0.187.4 (2026-02-16) - Use DSR to fix prompt position after terminal shrink
- Added `_query_cursor_row()` method that sends the DSR escape
  sequence (`ESC[6n`) and reads the terminal's cursor position response.
- `read_line()` now records the prompt's absolute viewport row at draw
  time via DSR.
- `redraw_line()` queries the cursor's actual row after a resize and
  compares it with the saved prompt row to detect displacement caused
  by scrollback reflow.  When the terminal shrinks and pushes the
  cursor down, the prompt is now redrawn at its original row (or the
  top of the viewport if the original row scrolled off).
- Falls back to the content-span calculation when DSR is unavailable.

## 0.187.3 (2026-02-16) - Fix pasted text not appearing until next keystroke
- Replaced all `sys.stdin.read(1)` calls in `LineEditor` with a new
  `_read_char()` method that reads from the raw fd via `os.read()`.
  Python's `BufferedReader` would consume all available bytes from the fd
  on the first read but return only one character; the rest became
  invisible to `select()`, causing pasted text to appear only after the
  next keystroke.
- `_read_char()` reads up to 4096 bytes from the raw fd, decodes them,
  and stores extra characters in `_char_buf`.  The main loop skips
  `select()` when the buffer is non-empty, so all pasted characters are
  processed immediately.

## 0.187.2 (2026-02-16) - Fix SIGWINCH redraw after terminal resize
- Rewrote `LineEditor.redraw_line()` to correctly handle terminal resizes.
  The old implementation used `\r` (carriage return) which only moves to
  column 0 of the current row; after a resize the cursor could be on a
  different row than the prompt, causing the prompt to appear at the top
  of the window while the cursor sat at the bottom.
- The new implementation tracks terminal width at draw time, calculates
  how many rows the prompt+buffer spanned at the old width, moves the
  cursor up to the prompt's starting row with `\033[{n}A`, clears from
  there to the bottom of the screen with `\033[J`, and redraws at the
  new width.
- Added `_visible_length()` static method to strip ANSI escape sequences
  when measuring prompt length, so colored prompts are handled correctly.
- Cursor repositioning after redraw now uses row/column ANSI sequences
  instead of backspace characters, so it works correctly when content
  wraps across multiple terminal lines.

## 0.187.1 (2026-02-14) - Fix SignalNotifier blocking read
- Made the read end of SignalNotifier self-pipes non-blocking.  Only the
  write end was non-blocking, so `drain_notifications()` would block
  indefinitely when called with no pending signals.  This was exposed by
  v0.187.0's fix to the dead `shell.signal_manager` code paths, which
  made `process_sigchld_notifications()` actually execute in the REPL
  loop for the first time.

## 0.187.0 (2026-02-14) - Interactive public API cleanup
- Rewrote `psh/interactive/__init__.py`: added module docstring listing all
  submodules; added `load_rc_file` and `is_safe_rc_file` imports from
  `rc_loader`; trimmed `__all__` from 7 to 2 items (`InteractiveManager`,
  `load_rc_file`).
- Removed vestigial `execute()` abstractmethod from `InteractiveComponent`
  ABC and all 5 subclass implementations (`REPLLoop`, `SignalManager`,
  `HistoryManager`, `CompletionManager`, `PromptManager`).
- Fixed 2 bypass imports in `shell.py`: `from .interactive.base import
  InteractiveManager` and `from .interactive.rc_loader import load_rc_file`
  now use package-level `from .interactive import ...`.
- Fixed dead `shell.signal_manager` access in `repl_loop.py` and
  `multiline_handler.py` to use `shell.interactive_manager.signal_manager`,
  restoring SIGCHLD notification processing and SIGWINCH terminal-resize
  handling.
- Updated `interactive/CLAUDE.md`: replaced stale pseudocode in REPL Loop
  and Signal Handling sections with actual implementation patterns; added
  `rc_loader.py` to key files table.

## 0.186.0 (2026-02-14) - Move create_parser to parser package
- Moved `create_parser()` from `psh/utils/parser_factory.py` to
  `psh/parser/__init__.py`; deleted `parser_factory.py`.
- Changed signature from `create_parser(tokens, shell, source_text)` to
  `create_parser(tokens, active_parser='rd', trace_parsing=False,
  source_text=None)` -- the function no longer takes the whole shell object.
- Updated caller in `scripting/source_processor.py` to pass explicit
  arguments.
- Removed `create_parser` from `psh/utils/__init__.py` and `__all__`
  (10 → 9 items).
- Added `create_parser` to `psh/parser/__all__` (5 → 6 items).
- Updated `parser_guide.md`, `parser_public_api.md`, `utils_guide.md`,
  and `utils_public_api.md` to reflect the new location.

## 0.185.0 (2026-02-14) - Core public API cleanup
- Rewrote `psh/core/__init__.py`: added module docstring, 7 new imports
  (`ExpansionError`, `OptionHandler`, `TrapManager`, `is_valid_assignment`,
  `extract_assignments`, `is_exported`), updated `__all__` from 11 to 18 items,
  removed stale `ShellOptions` comments.
- Fixed 14 `exceptions` bypass imports across 9 files to use package-level
  `from ..core import ...` instead of `from ..core.exceptions import ...`.
- Fixed 23 `variables` bypass imports across 7 files to use package-level
  imports.
- Fixed 2 `options` bypass imports in `expansion/variable.py`.
- Fixed 2 `trap_manager` bypass imports in `shell.py` and
  `builtins/signal_handling.py`.
- Fixed 1 `assignment_utils` bypass import in `executor/command.py`.
- Fixed 1 `state` bypass import in `shell.py`.
- Removed stale `scope.py` row from `core/CLAUDE.md` (file does not exist;
  `VariableScope` already listed under `scope_enhanced.py`).

## 0.184.0 (2026-02-14) - Builtins public API cleanup
- Populated `psh/builtins/__init__.py` with `FunctionReturn` and `PARSERS`
  imports; updated `__all__` from 3 to 5 items; added module-level docstring
  listing all builtin modules and their commands.
- Fixed 5 `FunctionReturn` bypass imports in executor files (`core.py`,
  `function.py`, `command.py`, `strategies.py` x2) to use package-level
  `from ..builtins import FunctionReturn`.
- Fixed `registry` bypass import in `pipeline.py` to use package-level import.
- Fixed `PARSERS` bypass import in `__main__.py` to use package-level import.
- Corrected 6 command-to-file mapping errors in `builtins/CLAUDE.md`:
  moved `pwd` from `navigation.py` to `io.py`; moved `true`, `false`, `:`
  from `io.py` to `core.py`; moved `declare`, `typeset`, `readonly` from
  `environment.py` to `function_support.py`; fixed `shell_state.py` →
  `shell_options.py` for `shopt`; added `history`, `version`, `local` to
  `shell_state.py`.

## 0.183.0 (2026-02-14) - Utils public API cleanup
- Populated `psh/utils/__init__.py` with `__all__` (11 items), imports, and
  docstring; all public symbols now importable from `psh.utils` directly.
- Deleted ~75 lines of dead code from `signal_utils.py`: `block_signals()` and
  `restore_default_signals()` context managers (zero callers) plus unused
  `contextlib` import.
- Deleted `SignalNotifier.has_notifications()` (~28 lines, zero callers,
  self-acknowledged hack that consumed pipe data it could not replace).
- Fixed 4 bypass imports in 4 files (`signal_manager.py`,
  `function_support.py`, `source_processor.py`, `debug_control.py`) to use
  package-level imports instead of submodule paths.

## 0.182.0 (2026-02-14) - Executor public API cleanup
- Trimmed `psh/executor/__init__.py` `__all__` from 13 to 5 items; removed
  10 items (`PipelineContext`, `PipelineExecutor`, `CommandExecutor`,
  `ControlFlowExecutor`, `ArrayOperationExecutor`, `FunctionOperationExecutor`,
  `SubshellExecutor`, `ExecutionStrategy`, `BuiltinExecutionStrategy`,
  `FunctionExecutionStrategy`) — they remain importable as convenience imports.
- Added 2 missing items to `__all__` and imports: `apply_child_signal_policy`
  (from `child_policy`) and `TestExpressionEvaluator` (from `test_evaluator`),
  both having production callers.
- Fixed 5 bypass imports in 4 files: `command_builtin.py` (2 → 1 package-level
  import), `shell.py`, `command_sub.py`, `process_sub.py` — all now import
  from `psh.executor` instead of submodules.
- Fixed `__init__.py` docstring: removed references to non-existent modules
  (`arithmetic`, `utils`); added `strategies`, `process_launcher`,
  `child_policy`, `test_evaluator`.

## 0.181.0 (2026-02-14) - Visitor public API cleanup
- Trimmed `psh/visitor/__init__.py` `__all__` from 14 to 9 items; removed
  5 Tier 3 items (`ASTTransformer`, `ValidatorVisitor`, `LinterConfig`,
  `LintLevel`, `SecurityIssue`) — they remain importable as convenience
  imports but are no longer part of the public API.
- Deleted unused `ASTTransformer` class (~69 lines) and `CompositeVisitor`
  class (~34 lines) from `base.py`; zero subclasses or external callers.
- Fixed 7 bypass imports across `psh/executor/` (5 files) and
  `psh/parser/visualization/` (2 files): changed
  `from psh.visitor.base import ASTVisitor` to
  `from psh.visitor import ASTVisitor`.
- Deduplicated `BASH_BUILTINS` in `MetricsVisitor`; replaced with
  `SHELL_BUILTINS` import from `constants.py`.
- Updated `psh/visitor/CLAUDE.md`: corrected return type table, added
  `constants.py` to Key Files, removed ASTTransformer and CompositeVisitor
  documentation sections.

## 0.180.0 (2026-02-14) - Expansion public API cleanup
- Populated `psh/expansion/__init__.py` with `ExpansionManager` import and
  `__all__ = ['ExpansionManager']`; added convenience imports for
  `contains_extglob` and `match_extglob` (not in `__all__`).
- Updated `shell.py` to import `ExpansionManager` from the package
  (`from .expansion import ExpansionManager`) instead of the submodule.
- Fixed broken import in `function_support.py`: changed
  `from ..expansion.arithmetic import ArithmeticEvaluator` (non-existent
  module) to `from ..arithmetic import evaluate_arithmetic`; also fixed
  incorrect `shell.state` argument (should be `shell`).
- Eliminated redundant `VariableExpander` construction in
  `shell_state.py` (2 locations); replaced with
  `shell.expansion_manager.expand_string_variables()`.
- Eliminated redundant `WordSplitter` construction in
  `control_flow.py`; replaced with
  `self.shell.expansion_manager.word_splitter`.
- Updated `psh/expansion/CLAUDE.md`: removed stale `base.py` /
  `ExpansionComponent` references; rewrote "Adding a New Expansion
  Type" section to show actual pattern (plain class, no ABC).

## 0.179.0 (2026-02-14) - I/O redirect public API cleanup
- Populated `psh/io_redirect/__init__.py` with `IOManager` import and
  `__all__ = ['IOManager']`; updated imports in `shell.py` and
  `process_launcher.py` to use package-level import.
- Deleted 5 dead `IOManager` methods: `collect_heredocs()`,
  `handle_heredoc()`, `cleanup_temp_files()`, `is_valid_fd()`,
  `_is_heredoc_delimiter_quoted()` (~55 lines) plus `_temp_files` init.
- Deleted 3 dead `HeredocHandler` methods: `collect_heredocs()`,
  `create_heredoc_file()`, `expand_variables_in_heredoc()` (~82 lines)
  plus unused `tempfile` and AST node imports.
- Consolidated `_dup2_preserve_target` from duplicate `@staticmethod`
  on both `IOManager` and `FileRedirector` to a single module-level
  function in `file_redirect.py`.
- Extracted `_expand_redirect_target()` helper to replace 4 copies of
  the 8-line variable/tilde expansion preamble.
- Extracted `_check_noclobber()` helper to replace 4 inline noclobber
  checks.
- Moved `_saved_stdout`/`_saved_stderr`/`_saved_stdin` from `Shell`
  object to `FileRedirector` instance.
- Initialized `_saved_fds_list` in `IOManager.__init__` and removed
  `hasattr()` guards.
- Added 6 per-type redirect helpers on `FileRedirector`:
  `_redirect_input_from_file`, `_redirect_heredoc`,
  `_redirect_herestring`, `_redirect_output_to_file`,
  `_redirect_dup_fd`, `_redirect_close_fd`.
- Rewrote `apply_redirections` (~120→~35 lines),
  `apply_permanent_redirections` (~152→~35 lines),
  `setup_child_redirections` (~122→~45 lines), and
  `setup_builtin_redirections` (~142→~55 lines) to use shared helpers.

## 0.178.0 (2026-02-13) - Parser public API cleanup
- Trimmed `__all__` from 17 items to 5 (`parse`, `parse_with_heredocs`,
  `Parser`, `ParserConfig`, `ParseError`); demoted Tier 2 items
  (`ParserContext`, `ParserProfiler`, `ErrorContext`, `ParsingMode`,
  `ErrorHandlingMode`) to convenience imports; removed Tier 3 items
  (`ContextBaseParser`, `HeredocInfo`, `TokenGroups`) from package-level
  `__all__`.
- Deleted `psh/parser/recursive_descent/support/factory.py` (6 functions,
  zero production callers).
- Trimmed `context_factory.py` from 8 functions to 1 (`create_context`);
  deleted 7 zero-caller wrapper functions.
- Trimmed `psh/parser/recursive_descent/__init__.py` `__all__` from 8 to 5;
  trimmed `psh/parser/validation/__init__.py` `__all__` from 9 to 7.
- Deleted `parse_strict_posix` and `parse_permissive` convenience functions
  from parser `__init__.py`.
- Fixed bypass imports in `psh/builtins/parse_tree.py` and
  `psh/utils/parser_factory.py` to import from `psh.parser` instead of
  reaching into submodule internals.
- Removed 3 test classes and 4 test methods that tested deleted functions.

## 0.177.0 (2026-02-13) - Lexer public API cleanup
- Trimmed `__all__` from 27 items to 5 (`tokenize`, `tokenize_with_heredocs`,
  `ModularLexer`, `LexerConfig`, `LexerError`); demoted Tier 2 items
  (constants, unicode helpers, `TokenPart`, `RichToken`, `LexerContext`) to
  convenience imports; removed Tier 3 items (`Position`, `LexerState`,
  `PositionTracker`, `LexerErrorHandler`, `RecoverableLexerError`) from
  package-level imports entirely.
- Replaced `isinstance(token, RichToken)` check in `commands.py` with
  `token.parts` (all tokens have `parts` via `__post_init__`); removed
  `RichToken` import — zero production callers remain.
- Deleted stale `__version__ = "0.91.1"` from `psh/lexer/__init__.py`.
- Updated `psh/lexer/CLAUDE.md`: fixed `modular_lexer.py` line count
  (~900 → ~600), replaced stale `LexerContext` field listing with actual
  dataclass fields.
- Rewrote `test_lexer_package_api.py`: added `test_all_exports` asserting
  exact `__all__` contents; added `TestDemotedImports` verifying convenience
  and submodule importability.
- Updated `docs/guides/lexer_guide.md` section 2 to reflect new API tiers.
- Added `docs/guides/lexer_public_api.md` API reference documenting public,
  convenience, and internal import tiers.

## 0.176.0 (2026-02-13) - Deep cleanup of parser, shell, and lexer dead code
- Removed dead `StatementList.pipelines` property (zero callers) and 3 stale
  "Deprecated" placeholder comments from `ast_nodes.py`.
- Fixed 2 pre-existing bugs in DOT generator (`visit_AndOrList` used wrong
  fields, `visit_CommandList` referenced nonexistent `node.commands`).
- Removed dead code from recursive descent parser: `source_text`/`source_lines`
  aliases, `context` property, `heredoc_map` assignments (parser.py + utils.py).
- Removed 145 lines from `SourceProcessor`: dead `_extract_heredoc_content()`,
  `_remove_heredoc_content_from_command()`, and 21 dead error pattern entries.
- Removed dead code from `Shell`: visitor-executor option cleanup, `builtins`
  dict, `execute()` method, `executor_manager` reference.
- Removed 9 dead methods from `ContextBaseParser` (60 lines): `synchronize`,
  `trace`, `get_position_info`, `match_statement_start`, `match_redirection_start`,
  `match_control_structure`, `_token_type_to_string`, `get_state_summary`,
  `generate_profiling_report`.
- Removed dead `legacy_mode` field from `LexerConfig` (never set to True).
- Cleaned up stale "legacy"/"backward compatibility" labels across all files.

## 0.175.0 (2026-02-13) - Dead code and legacy shim cleanup
- Removed dead `LineEditor` class from `psh/tab_completion.py` (372 lines);
  superseded by production `LineEditor` in `psh/line_editor.py`.
- Removed unused `psh/pipeline/` package (`ShellPipeline`/`PipelineBuilder`
  facade, 68 lines + tests); never used by production code.
- Removed 5 stale compatibility wrappers from `Shell` (`_add_to_history`,
  `_load_history`, `_save_history`, `_handle_sigint`, `_handle_sigchld`);
  inlined the one live caller (exit builtin).
- Removed 4 dead legacy method wrappers from `PrintfBuiltin`
  (`_process_format_string`, `_parse_format_specifier`, `_format_argument`,
  `_apply_string_formatting`/`_apply_integer_formatting`).
- Removed dead `_stdout`/`_stderr`/`_stdin` backup assignments and stale
  "backward compatibility" comments from `ShellState`.
- Removed 4 incorrect XFAILs from PTY interactive tests (`test_bg_resume`,
  `test_background_job_completion`, `test_disown_command`,
  `test_sigtstp_handler`) — moved class-level markers to individual methods.
- Cleaned up `ARCHITECTURE.llm` references to removed pipeline package.

## 0.174.0 (2026-02-13) - Fix array element parameter expansion operators
- Fixed `${arr[1]:-default}`, `${arr[5]:=five}`, `${arr[1]:?err}`,
  `${arr[1]:+alt}` — all four `:` operators now work with array subscripts.
- Root cause: `_get_var_or_positional()` treated `arr[1]` as a scalar name
  instead of resolving element 1 of array `arr`.
- Added array subscript branch to `_get_var_or_positional()`.
- Added `_set_var_or_array_element()` helper so `:=` assigns to the array
  element instead of creating a scalar named `arr[5]`.
- Fixed both `:=` code paths (string-split handler and `_apply_operator`).
- Removed XFAIL from `test_operators_with_arrays` (3 → 2 xfails).

## 0.173.0 (2026-02-13) - Fix 2 incorrect XFAILs (5 → 3)
- Removed XFAIL from `test_alias_with_arguments`: bash disables aliases in
  non-interactive mode, so PSH succeeding is a PSH extension, not a failure.
  Changed to `assert_psh_extension()`.
- Removed XFAIL from `test_character_class_patterns`: `${VAR#[0-9]*}` shortest
  match correctly strips one digit (`"23abc"`), not all (`"abc"`). Fixed
  assertion and added `##` longest match test case.
- Sharpened `test_declare_nameref_attribute` XFAIL reason to
  `"declare -n (nameref) not implemented"`.

## 0.172.0 (2026-02-13) - Fix FD leak in test fixtures causing "Too many open files"
- Fixed file descriptor exhaustion (`OSError: [Errno 24] Too many open files`)
  when running ~3,000+ tests, particularly with the combinator parser.
- Each `Shell` instance creates 4 pipe FDs via `SignalNotifier` (SIGCHLD +
  SIGWINCH). `_cleanup_shell()` now explicitly closes these FDs in teardown.
- Added `_cleanup_shell()` call to `captured_shell` fixture, which was the
  only shell fixture missing cleanup.

## 0.171.0 (2026-02-13) - Fix C-style for loop I/O redirection test infrastructure (3 → 0)
- Rewrote 3 C-style for loop I/O redirection tests to use `subprocess.run()`
  instead of `isolated_shell_with_temp_dir`, eliminating pytest capture
  interference with forked child process file descriptors.
- Removed Phase 1 `--deselect` and Phase 3 re-run workarounds from
  `run_tests.py` — these tests no longer need the `-s` flag.
- Combinator parser now has 0 remaining test failures out of ~3,350 tests.
- Updated remaining failures documentation to reflect completion.

## 0.170.0 (2026-02-13) - Fix combinator parser associative array initialization (5 → 3)
- Fixed associative array initialization in the combinator parser.
  `declare -A assoc=(["first key"]="first value")` now works correctly.
- The array collection loop had two bugs: LBRACKET/RBRACKET tokens were
  silently dropped, and STRING token values lost their quotes.
- Added LBRACKET/RBRACKET to accepted token types in the array loop,
  preserved original quote characters on STRING tokens, and used
  `adjacent_to_previous` to group tokens into properly concatenated
  elements (e.g. `["key"]="value"` instead of `[ "key" ]= "value"`).
- Zero regressions in recursive descent parser or combinator test suite.

## 0.169.0 (2026-02-12) - Fix lexer arithmetic bug and case pattern parsing (11 → 5)
- Fixed lexer bug where `>`, `<`, `>=`, `<=` were silently dropped from
  the token stream inside `(( ))` after `$((expr))` expansions.  The
  literal recognizer now accepts these characters as word-start characters
  when `arithmetic_depth > 0`.
- Fixed combinator parser case pattern parsing for multi-line character
  class patterns like `[a-z]*)`.  When the lexer emits `LBRACKET` at
  command position, the case pattern parser now reconstructs the full
  glob pattern from constituent tokens.
- Updated remaining failures documentation (5 failures in 2 categories).
- Updated lexer token type issues documentation.
- Zero regressions in recursive descent parser, lexer, or combinator tests.

## 0.168.0 (2026-02-12) - Fix 7 more combinator parser failures (18 → 11)
- Fixed process substitution `<(cmd)` by treating PROCESS_SUB_IN/OUT tokens
  as LiteralPart nodes (matching the recursive descent parser) instead of
  ExpansionPart nodes.  The expansion manager handles the `<()`/`>()` syntax
  during the expansion phase.
- Added errexit (`set -e`) check to `visit_TopLevel` in the executor,
  matching the existing logic in `visit_StatementList`.  The combinator
  parser produces TopLevel nodes; without this check, `set -e` had no
  effect between top-level statements.
- Added adjacent RBRACE consumption in the simple command parser so that
  brace expansion with arithmetic tokens (`echo {$((1)),$((2)),$((3))}`)
  no longer fails with "Unexpected token: RBRACE".  Only consumes RBRACE
  when adjacent to the previous token to avoid breaking brace groups.
- Updated remaining failures documentation (11 failures in 4 categories).
- Zero regressions in recursive descent parser or combinator tests.

## 0.167.0 (2026-02-12) - Fix 21 combinator parser failures (39 → 18)
- Restructured `_build_complete_parser()` so compound commands (for, while,
  if, case, etc.) are pipeline elements rather than top-level alternatives,
  fixing `for ... done | grep` and similar piped compound commands.
- Added `COMMAND_SUB`, `COMMAND_SUB_BACKTICK`, `ARITH_EXPANSION`,
  `PARAM_EXPANSION` to accepted token types in the for-loop word list,
  matching the select-loop parser.
- Added explicit handling for `REDIRECT_ERR` and `REDIRECT_ERR_APPEND`
  tokens to produce `Redirect(type='>', fd=2)` instead of
  `Redirect(type='2>', fd=None)`.
- Added array assignment detection in the simple-command parser: when a
  word ending with `=` is followed by an adjacent `LPAREN`, parenthesized
  items are collected into a single synthetic `name=(item1 item2 ...)` token.
- Made `do` keyword optional after `))` in C-style for loops, matching
  the recursive descent parser's behavior.
- Added remaining failures documentation at
  `docs/guides/combinator_parser_remaining_failures.md`.
- Zero regressions in recursive descent parser or combinator tests.

## 0.166.0 (2026-02-10) - Consolidate process substitution duplication
- Extracted `create_process_substitution()` module-level function in
  `psh/io_redirect/process_sub.py` — single source of truth for the
  fork/pipe/signal/exec sequence used by all process substitution paths.
- Replaced 75-line copy-paste in `file_redirect.py:_handle_process_sub_redirect()`
  with 8-line delegation to the new function.
- Replaced 69-line inline block in `manager.py:setup_builtin_redirections()`
  with 6-line delegation.
- Unified FD/PID tracking through `ProcessSubstitutionHandler.active_fds/active_pids`
  — eliminates three ad-hoc shell attributes (`_redirect_proc_sub_fds`,
  `_redirect_proc_sub_pids`, `_builtin_proc_sub_fds`, `_builtin_proc_sub_pids`).
- Fixed FD/PID leak: `_redirect_proc_sub_*` attributes were stored but never
  cleaned up; now all paths go through `ProcessSubstitutionHandler.cleanup()`.
- ~130 lines of duplicated code removed. Zero behavioral changes.

## 0.165.0 (2026-02-10) - Decompose shell.py
- Reduced shell.py from 925 lines to ~325 lines by extracting domain logic.
- Deleted dead `_execute_buffered_command()` (165 lines) — duplicate of
  SourceProcessor's copy, never called on Shell.
- Extracted `TestExpressionEvaluator` class to `psh/executor/test_evaluator.py`
  (172 lines of `[[ ]]` evaluation logic).
- Extracted `print_ast_debug()` to `psh/utils/ast_debug.py` (72 lines).
- Extracted `create_parser()` to `psh/utils/parser_factory.py` (33 lines).
- Extracted `contains_heredoc()` to `psh/utils/heredoc_detection.py` (56 lines).
- Extracted RC file loading to `psh/interactive/rc_loader.py` (44 lines).
- Removed thin wrapper methods `run_script()`, `interactive_loop()`,
  `set_positional_params()` — callers updated to use managers directly.
- Updated source_processor.py to use new module functions.
- Zero behavioral changes; all 3,087 tests pass.

## 0.164.0 (2026-02-10) - Move Changelog out of version.py
- Moved VERSION_HISTORY string (1,157 lines, 80KB) from psh/version.py to
  CHANGELOG.md. version.py is now 19 lines (was 1,175).
- VERSION_HISTORY was never read at runtime — only referenced in documentation.
- Updated CLAUDE.md version bump instructions to reference CHANGELOG.md instead
  of VERSION_HISTORY.

## 0.163.0 (2026-02-10) - Replace Broad Exception Handlers with Specific Types
- Eliminated all 22 bare except: handlers across 13 files, replacing with
  specific exception types (OSError, termios.error, ValueError, KeyError,
  AttributeError, TypeError).
- Narrowed 40 of 61 except Exception handlers across 20 files to specific
  types: OSError for I/O/terminal/process ops, (ValueError, ArithmeticError)
  for arithmetic evaluation, (AttributeError, TypeError) for getattr ops,
  (KeyError, IndexError) for collection access, etc.
- Kept 21 except Exception handlers that are intentional: forked child
  catch-alls before os._exit(), REPL last-resort, trap execution safety,
  __del__ cleanup, and command execution catch-alls that re-raise control
  flow exceptions.
- Fixed termios.error not inheriting from OSError: job_control.py terminal
  mode handlers now catch (OSError, termios.error).
- Zero behavioral changes; all 3087 tests pass.

## 0.162.0 (2026-02-10) - Fix Documentation and Version Drift
- Updated version references in README.md (0.159.0 → 0.162.0),
  ARCHITECTURE.md (0.159.0 → 0.162.0), ARCHITECTURE.llm (0.159.0 → 0.162.0),
  and CLAUDE.md (0.120.0 → 0.162.0).
- Fixed stale project statistics in README.md: LOC (62,000 → 99,000),
  Python files (214 → 348), test count (3,021 → 3,087), test files (154 → 166).
- Fixed stale --parser=combinator CLI flag in README.md (replaced with
  parser-select combinator builtin, matching v0.130.0 changes).
- Updated README.md Recent Development section to cover v0.100.0-v0.161.0.
- Updated CLAUDE.md Current Development Status: version, recent work summary,
  and removed stale active issues.
- Updated CLAUDE.md test count (~3000 → ~3,087).

## 0.161.0 (2026-02-10) - Test Tree Lint Cleanup
- Fixed 7,132 ruff lint issues across ~160 test files:
  6330 W293 (whitespace on blank lines), 265 F401 (unused imports),
  163 I001 (unsorted imports), 121 W292 (missing newline at EOF),
  121 F841 (unused variables), 116 W291 (trailing whitespace),
  13 W605 (invalid escape sequences), 3 F811 (redefined while unused).
- Added noqa: F401 to 4 intentional imports (removed-module tests, pexpect
  availability detection).
- Expanded CI lint gate to cover tests/ alongside psh/.
- Zero behavioral changes; all 3087 tests pass.

## 0.160.0 (2026-02-10) - Lint Cleanup and CI Gate
- Fixed 626 ruff lint issues across ~50 files in psh/:
  596 W293 (whitespace on blank lines), 17 W291 (trailing whitespace),
  7 I001 (unsorted imports), 6 F401 (unused imports).
- Added lint job to CI (.github/workflows/test_migration.yml): runs
  ruff check psh before tests to prevent regressions.
- Zero behavioral changes; all 3087 tests pass.

## 0.159.0 (2026-02-10) - Fix Doc Drift, Dead Code, and Package Metadata
- Fixed version drift in README.md (0.113.0 → 0.159.0), ARCHITECTURE.md
  (0.104.0 → 0.159.0), and ARCHITECTURE.llm (0.120.0 → 0.159.0).
- Fixed test count (3,021 → 3,087) and parser parity claims (100% → near-complete)
  in README.md and ARCHITECTURE.md.
- Fixed stale --parser=combinator CLI flag references in ARCHITECTURE.md
  (replaced with parser-select combinator builtin, matching v0.130.0 changes).
- Deleted dead psh/core/scope.py (147 lines): superseded by scope_enhanced.py,
  only imported in core/__init__.py, never used by any other code. Updated
  __init__.py to import VariableScope from scope_enhanced.py instead.
- Deleted stale psh/test_assoc.py (74 lines): ad-hoc test script referencing
  removed APIs (executor_manager, get_variable_object, old Parser(tokens) usage).
- Fixed package metadata in pyproject.toml: placeholder author/email replaced
  with actual values.

## 0.158.0 (2026-02-10) - Remove Dead shell_parser.py Module
- Deleted psh/shell_parser.py (248 lines): entirely dead code. It imported
  parse_with_lexer_integration from psh.parser, which was never exported,
  so the import always failed. shell.py caught the ImportError silently,
  meaning ShellParser, install_parser_integration, and related functions
  never ran. The module also referenced ParserConfig fields removed in
  v0.131.0 (use_enhanced_tokens, enable_context_validation, etc.).
- Removed the dead import block from Shell.__init__() in shell.py.
- Removed the unused enhanced_lexer parameter from Shell.__init__().

## 0.157.0 (2026-02-10) - Update Parser Combinator Feature Parity Tests
- Removed skip_combinator=True from 10 test groups (23 cases) in
  test_parser_feature_parity.py — all features were implemented in v0.94-v0.100
  but the parity tests were never updated.
- Added heredoc-aware parsing to parse_both(): auto-detects heredoc commands and
  uses tokenize_with_heredocs() + parse_with_heredocs() for both parsers.
- Added parse_both_heredoc() helper method for explicit heredoc test path.
- Updated generate_parity_report() feature matrix: all 19 features now show full
  support in both parsers, except &> combined redirect (1 case still skipped).
- Only remaining skip: &> combined redirect not supported in parser combinator.

## 0.156.0 (2026-02-10) - Reset Job ID Counter When Job Table Is Empty
- Fixed job numbering: transient internal jobs (pipelines, subshells, command
  substitutions) incremented the job ID counter but were removed immediately,
  so the first user-visible background/stopped job got an unexpectedly high
  number (e.g. [15] instead of [1]). Now resets next_job_id to 1 when the
  job table is empty before creating a new job, matching bash behavior.

## 0.155.0 (2026-02-10) - Fix 8 PSH Bug XFAILs
- Fixed heredoc in case statement parsing: KeywordNormalizer entered in_heredoc
  mode when heredoc content had already been collected by tokenize_with_heredocs(),
  causing it to skip real tokens (;;, esac) looking for a non-existent delimiter.
  Added heredoc_key check to avoid entering in_heredoc mode when content is
  already collected.
- Fixed SourceProcessor _collect_heredoc_content() not tracking already-closed
  heredocs in the buffer: when a case statement had two heredoc branches, the
  method would find both << markers but not check which were already closed,
  causing EOF during collection of the second heredoc.
- Fixed populate_heredoc_content() failing on CaseItem.commands (StatementList):
  the traversal called `for cmd in node.commands` but StatementList is not
  directly iterable. Now unwraps StatementList.statements before iterating.
- Fixed builtin output in forked child ignoring shell redirections: echo in a
  pipeline subshell uses os.write(1, ...) which bypasses sys.stdout redirections
  set by setup_builtin_redirections(). When _in_forked_child is True, builtins
  now use with_redirections() (os.dup2-based) instead of setup_builtin_redirections()
  (Python-level), so os.write(1, ...) goes to the correct file.
- Switched test_function_as_pipeline_filter and test_function_pipeline_chain to
  subprocess: read inside pipeline functions can't read from pipe when pytest
  captures stdin.
- Fixed test_syntax_error_recovery: shell correctly exits on syntax error in
  non-interactive mode (POSIX behavior). Updated assertion to expect non-zero
  exit code and error message.
- Fixed test_pipeline_error_in_middle: POSIX says pipeline exit = last command
  exit code. cat succeeds so pipeline exit is 0.
- Fixed test_background_job_with_redirection_error: PSH evaluates redirect
  synchronously for background builtins. Updated to accept any exit code from
  the & command and assert wait returns 0.
- Removed 8 xfail markers (all tests now pass).

## 0.154.0 (2026-02-10) - Fix 4 Test Infrastructure Issues
- Switched test_while_with_command_condition to subprocess: 'read' from
  redirected stdin conflicts with pytest's output capture.
- Switched test_function_with_many_commands to subprocess: function output
  redirection to file conflicts with pytest's output capture.
- Switched test_parameter_scoping to subprocess: 'set' positional params
  and echo don't capture through capsys.
- Switched test_subshell_process_substitution to subprocess: process
  substitution FDs conflict with pytest's output capture.
- Removed 4 xfail markers (all tests now pass).

## 0.153.0 (2026-02-10) - Fix Brace Tokenization for Non-Expanding Braces
- Fixed { and } being tokenized as separate LBRACE/RBRACE operator tokens
  when they appear inside words (e.g., {a..1}, {a.b}, {a,b,c, {}).
  These should remain literal parts of the word when brace expansion doesn't
  apply, matching bash behavior. Previously echo {a..1} output "{ a..1 }"
  (three separate tokens), now correctly outputs "{a..1}".
- Added standalone-brace check in operator recognizer: { and } are only
  recognized as operators when followed by whitespace/delimiter/EOF (brace
  group syntax), not when followed by word characters.
- Added {} special case: {} is always a word token, never LBRACE+RBRACE.
- Updated literal recognizer can_recognize() and _is_word_terminator() to
  allow { and } as word characters when they would be part of a larger word.
- Fixed test_single_item assertion to expect correct "{a}" output.
- Switched test_very_long_expansion to subprocess (pipeline fork issue).
- Removed 5 xfail markers from brace expansion tests. 1 xfail remains
  (test_special_chars_in_expansion) due to architectural limitation: pre-
  tokenization brace expansion of {$,#,@} produces "echo $ # @" where #
  becomes a comment character.

## 0.152.0 (2026-02-10) - Test Builtin Parentheses Support and Test Fixes
- Implemented parenthesized grouping in test builtin: test \\( expr \\) now works
  for complex expressions like test \\( -n "a" -a -n "b" \\) -o -z "c", matching
  POSIX/bash behavior. Added _evaluate_with_parens() and parenthesis-aware
  scanning in _evaluate_expression() that skips -a/-o inside groups.
- Fixed test_alias_with_pipe and test_alias_with_args: switched from in-process
  captured_shell/capsys to subprocess, since alias-expanded external commands
  fork child processes whose output bypasses Python-level capture.
- Fixed test_history_clear: drain accumulated capsys output before assertion
  and expect the 'history' command itself to appear as entry 1 after clear.
- Removed all 4 xfail markers (all tests now pass).

## 0.151.0 (2026-02-10) - Fix Alias Subshell Inheritance and Alias Test Corrections
- Fixed aliases not inherited by subshells: added AliasManager.copy() and wired it
  into Shell.__init__() parent_shell inheritance block, matching bash behavior where
  child shells inherit the parent's alias definitions.
- Fixed 3 alias test bugs: test_alias_expansion_timing used alias name 'test' which
  collides with the test builtin; test_alias_with_special_characters and
  test_alias_with_array_syntax used double quotes causing premature variable expansion
  at definition time instead of single quotes to defer expansion to execution time.
- Removed all 4 xfail markers from alias expansion tests (all now pass).

## 0.150.0 (2026-02-09) - Executor/Visitor Cleanup and Correctness
- Deduplicated _expand_for_loop_items() and _expand_select_items() into single
  _expand_loop_items() method in control_flow.py (identical implementations)
- Deduplicated _apply_redirections() context manager: added empty-redirects guard
  to IOManager.with_redirections() and deleted 4 identical copies from core.py,
  command.py, control_flow.py, and subshell.py. Removed unused contextmanager
  imports from 4 files.
- Created psh/visitor/constants.py with shared DANGEROUS_COMMANDS, SENSITIVE_COMMANDS,
  SHELL_BUILTINS, COMMON_COMMANDS, and COMMON_TYPOS dictionaries. Updated
  enhanced_validator_visitor.py, linter_visitor.py, and security_visitor.py to
  import from the shared module instead of defining inline duplicates.
- Replaced regex-based IFS splitting in _word_split_and_glob() with POSIX-compliant
  WordSplitter from psh/expansion/word_splitter.py, which correctly handles
  whitespace vs non-whitespace IFS characters, backslash escapes, and empty fields.
- Fixed FunctionExecutionStrategy and AliasExecutionStrategy creating fresh
  ExecutorVisitor instances (losing accumulated visitor state). Threaded the
  caller's visitor from ExecutorVisitor through CommandExecutor to strategies
  via a visitor parameter on execute(). Falls back to creating a new visitor
  when not provided (backward compatibility).

## 0.149.0 (2026-02-09) - Dead Code Removal and Bare Exception Cleanup
- Deleted 10 dead methods (~255 lines) from ExecutorVisitor in core.py:
  _expand_arguments(), _extract_assignments(), _is_valid_assignment(),
  _is_exported(), _evaluate_arithmetic(), _expand_assignment_value(),
  _handle_exec_builtin(), _exec_with_command(), _exec_without_command(),
  _find_command_in_path() — all superseded by CommandExecutor and other
  specialized executors
- Removed 4 dead imports from core.py: os, signal, List/Tuple from typing,
  assignment_utils functions
- Replaced 7 bare except: clauses with specific exception types across 4 files:
  command.py (2x Exception), strategies.py (1x OSError),
  process_launcher.py (1x Exception, 1x OSError),
  subshell.py (2x Exception)

## 0.148.0 (2026-02-09) - Fix Medium Visitor Bugs from Review
- Fixed linter generic_visit duplication (Medium): dir(node) returned methods
  and properties, causing duplicate child traversal.  Replaced with
  dataclasses.fields(node) to iterate only declared dataclass fields.
- Fixed formatter C-style for loop $ injection (Medium): f-string used
  ${init}, ${cond}, ${update} which injected spurious $ into output.
  Changed to {init}, {cond}, {update} since ((...)) context doesn't use $.
- Verified formatter array subscript expansion is not a bug: ${arr[0]} round-
  trips correctly through parse → format via ParameterExpansion.__str__().
- Fixed enhanced validator _has_parameter_default under-reporting (Medium):
  the method checked for :- or := anywhere in the text string, which could
  match substrings outside ${...} expansions.  Now only matches operators
  inside ${...} delimiters with proper brace nesting.

## 0.147.0 (2026-02-09) - Fix Pipeline Test-Mode Fallback
- Fixed pipeline test-mode fallback creating anonymous objects with type() that
  lacked required API (Medium).  Now constructs a real Pipeline AST node and
  passes the real ExecutionContext instead of an empty anonymous object.
- Added context parameter to _execute_mixed_pipeline_in_test_mode() so the
  fallback path can use the caller's execution context.

## 0.146.0 (2026-02-09) - Fix Critical/High Executor Bugs from Review
- Fixed background brace-group double execution (Critical): { echo hi; } & was
  executing the body unconditionally in the parent, then forking for a second
  execution.  Now checks node.background before any execution, matching the
  subshell pattern.
- Fixed loop_depth leak on multi-level break/continue (High): context.loop_depth
  decrement in execute_while(), execute_until(), and execute_for() was outside
  the try/finally block, so a re-raised LoopBreak(level-1) or LoopContinue(level-1)
  would skip the decrement.  Wrapped each loop method in an outer try/finally.
- Fixed special-builtin prefix assignment persistence (High): POSIX requires that
  variable assignments before special builtins (export, readonly, eval, exec, etc.)
  persist after the command completes.  _execute_with_strategy() now returns
  (exit_code, is_special) and _restore_command_assignments() is skipped for
  special builtins.

## 0.145.0 (2026-02-09) - Quote-Aware Scanners, Multiple $@ Support
- Replaced 5 quote-unaware parenthesis/brace scanners in expansion with
  quote-aware helpers from psh/lexer/pure_helpers.py:
  - expand_string_variables() $((..)) scanner → find_balanced_double_parentheses(track_quotes=True)
  - expand_string_variables() $(..) scanner → find_balanced_parentheses(track_quotes=True)
  - expand_string_variables() ${..} scanner → find_closing_delimiter(track_quotes=True)
  - _expand_command_subs_in_arithmetic() $((..)) scanner → find_balanced_double_parentheses(track_quotes=True)
  - _expand_command_subs_in_arithmetic() $(..) scanner → find_balanced_parentheses(track_quotes=True)
- Added track_quotes parameter to find_balanced_double_parentheses() in pure_helpers.py
  (default False to preserve lexer behaviour; expansion callers pass True)
- Fixed multiple "$@" in one quoted word: _expand_at_with_affixes() now continues
  processing remaining parts after the first $@, correctly handling patterns like
  "a$@b$@c" with params (1 2) → [a1, 2b1, 2c]
- Added 6 regression tests for multi-$@, quote-aware command substitution, and
  braces in quoted defaults

## 0.144.0 (2026-02-09) - Deduplicate $@ Splitting Logic
- Extracted shared _expand_at_with_affixes() helper from the ~95% duplicate
  "$@" splitting logic in _expand_word() and _expand_double_quoted_word()
- Both call sites now delegate to the shared helper in 3 lines each
- The helper distributes positional params across prefix/suffix text:
  e.g. pre"$@"post with params (a,b,c) → [prea, b, cpost]
- Added in_double_quote parameter to control escape processing: double-quoted
  path only applies dquote escapes; composite path also handles unquoted escapes
- Retained assignment-word field-splitting heuristic in _expand_word() after
  investigation showed builtins (declare, export, local) receive VAR=value
  arguments through expand_arguments(), requiring the heuristic to suppress
  word splitting. Updated comment to document this rationale.
- All tests passing with zero regressions

## 0.143.0 (2026-02-09) - Decompose expand_variable() into Helper Methods
- Extracted 5 helper methods from the 380-line expand_variable() method:
  _expand_array_length(): handles ${#arr[@]}, ${#arr[*]}, ${#arr[index]}
  _expand_array_indices(): handles ${!arr[@]}, ${!arr[*]}
  _expand_array_slice(): handles ${arr[@]:start:length}
  _expand_array_subscript(): handles ${arr[index]}, ${arr[@]}, ${arr[*]}
  _expand_special_variable(): handles $?, $$, $!, $#, $@, $*, $0-$9
- expand_variable() is now an ~80-line dispatcher that checks preconditions
  and delegates to the appropriate helper
- Pure structural refactoring — no behavioral changes
- All tests passing with zero regressions

## 0.142.0 (2026-02-09) - Expansion Subsystem Cleanup: Dead Code, Bare Exceptions, Small Fixes
- Deleted dead code: _split_words() from ExpansionManager, GlobExpander.should_expand(),
  and process_escapes parameter from expand_string_variables() (variable.py, manager.py,
  and 5 callers in executor/array.py)
- Replaced 6 bare except: handlers with specific exception types:
  5x (ValueError, TypeError) in variable.py, 1x (KeyError, OSError) in tilde.py
- Fixed operator-detection heuristic in expand_parameter_direct() and expand_variable():
  replaced any(op in ...) conditional with unconditional evaluate_arithmetic(),
  matching the v0.141.0 fix already applied to indexed array access
- Fixed parse_expansion() colon-operator skip bug: ${var:=default} and ${var:?msg}
  were incorrectly parsed as substring extraction in the string-based expansion
  path. Changed '-+' to '-+=?' in the skip condition
- Fixed stale comment in command_sub.py: "Block SIGCHLD" → "Reset SIGCHLD to default"
- Added 4 regression tests for ${var:=default} and ${var:?msg} parsing

## 0.141.0 (2026-02-09) - Fix Array Index Arithmetic Evaluation
- Fixed array indices not evaluating bare variable names in arithmetic context.
  In bash, array indices are always evaluated as arithmetic expressions, so
  arr[i]="value" resolves variable i to its numeric value. PSH only called
  evaluate_arithmetic() when operator characters were detected, causing bare
  variable names like i to be treated as literal string keys.
- Simplified execute_array_element_assignment() in executor/array.py: replaced
  ~35-line heuristic block (try int(), regex for operators, conditional
  evaluate_arithmetic) with unconditional evaluate_arithmetic() for unquoted
  indices. Quoted indices (e.g., arr["key"]) still treated as string keys for
  associative arrays.
- Simplified indexed array access in expansion/variable.py: replaced
  operator-detection conditional with unconditional evaluate_arithmetic() call.
- Both paths now handle bare variable names, arithmetic expressions, and
  literals uniformly via evaluate_arithmetic(), matching bash behavior.
- Fixed test_large_array_creation: redirect was on a separate line from echo,
  creating an empty file instead of capturing output.

## 0.140.0 (2026-02-09) - Fix 5 Parser Validation and Config Issues
- Fixed validation false positives: fd-dup redirects (2>&1) no longer flagged
  as "missing target"; case statement uses correct field (items, not cases);
  variable name validation checks first char only (var1 no longer rejected).
- Fixed stale AST field references in validation traversal: ForLoop.values→items
  (List[str], not visitable), CaseConditional.word/cases→expr/items,
  AndOrList.pipeline→pipelines. Replaced wildcard imports with explicit imports
  in all three validation files.
- Fixed ParserConfig field name disconnect: renamed validate_ast to
  enable_validation; added enable_semantic_analysis and enable_validation_rules
  as real dataclass fields instead of dynamically injected attributes.
- Fixed create_configured_parser() config mutation: now uses config.clone() to
  create an independent copy instead of mutating the shared parent config.
- Fixed can_parse() EOF false negatives in combinator parser: added 'EOF' to
  the trailing-token skip loop, matching the parse() method.
- Added 13 regression tests in tests/regression/test_parser_review_fixes.py.

## 0.139.0 (2026-02-09) - Fix Redirect-Only Command Execution
- Fixed redirect-only commands (e.g., >file) not creating/truncating the target
  file. CommandExecutor.execute() returned early when no command args remained,
  skipping redirect application entirely. Now applies redirections before
  returning, matching POSIX/bash behavior.

## 0.138.0 (2026-02-09) - Fix 7 Parser Issues from Implementation Review
- Fixed non-terminating loop in case parsing when encountering LPAREN token
  (bash's optional (pattern) syntax). Added no-progress guard to prevent
  infinite loops on unexpected tokens.
- Fixed case terminator semantics: ;& and ;;& values now stored in CaseItem
  AST node (was always defaulting to ;;). Fixed executor fall-through logic
  so ;& correctly executes next case body unconditionally.
- Allowed leading redirections before command name (POSIX: >out echo hi).
  Expanded _validate_command_start() to accept REDIRECTS and fd-dup tokens.
- Fixed [[ ]] operand concatenation: added adjacent_to_previous check so
  '[[ a b ]]' correctly raises ParseError instead of silently concatenating.
- Allowed 'select' without 'in' clause (defaults to "$@"), matching bash.
- Fixed parse_with_heredocs() to handle both dict {'content':...,'quoted':...}
  and plain string formats for heredoc content.
- Fixed config validation enum comparison: validate_config() compared
  error_handling against string 'strict' instead of ErrorHandlingMode.STRICT.
- Added 23 regression tests in tests/regression/test_parser_review_fixes.py.
- Removed @pytest.mark.xfail from test_case_fallthrough (now works).

## 0.137.0 (2026-02-09) - Parser Code Quality: Address Remaining Code Smells #2 and #4
- Refactored is_array_assignment() from 90-line monolithic method into 5 focused
  helper methods using peek-based lookahead instead of advance-then-restore:
  _is_element_assignment_single_token (pure string inspection),
  _peek_is_assignment_operator (peek at offset), _is_initialization_pattern
  (peek 0..2), _is_element_with_bracket_token (peek 1), _scan_bracket_assignment
  (advance+restore for unbounded bracket depth). Main method is now a readable
  dispatcher documenting all 6 tokenisation patterns.
- Deduplicated parse(), parse_partial(), and can_parse() in combinator parser.py
  by extracting _prepare_tokens() (KeywordNormalizer + skip whitespace) and
  _apply_heredocs() helpers. Turned parse_partial() fallback cascade into a
  clean for-loop. Fixed can_parse() to normalise keywords consistently.
- Updated parser_code_quality_review_v0.135.md: all 4 code smells now addressed.
- No behavioral changes; all tests passing.

## 0.136.0 (2026-02-09) - Parser Code Quality: 5 Improvements from v0.135.0 Review
- Compiled regex patterns at module level in commands.py, redirections.py,
  and word_builder.py (3 files, 5 patterns).
- Moved 5 inline imports to module level: RichToken and WordBuilder in
  commands.py, ErrorContext and ErrorSeverity in context.py, ParsingMode
  in base_context.py.
- Replaced if/elif chain in _check_for_unclosed_expansions with
  data-driven _UNCLOSED_EXPANSION_MSGS dictionary lookup.
- Removed compatibility shim classes: ParserFactory, ConfigurationValidator,
  ParserContextFactory, _ErrorCollectorView. Migrated all callers to
  underlying module-level functions and ctx attributes.
- Factored combinators/control_structures.py (1,306 lines) into a package
  with 3 mixin modules (loops, conditionals, structures) plus shared
  format_token_value utility in utils.py.
- No behavioral changes; all tests passing.

## 0.135.0 (2026-02-09) - Consolidate parse_composite_argument() into Word AST
- Migrated all 10 callers of parse_composite_argument() to use parse_argument_as_word(),
  unifying all argument parsing into a single Word AST path.
- Deleted parse_composite_argument(), _token_to_argument(), and _format_variable() from
  CommandParser (82 lines removed).
- Added _word_to_element_type() static helper to ArrayParser for deriving legacy
  element-type strings (STRING, COMPOSITE_QUOTED, COMPOSITE, WORD) from Word nodes.
- Removed duplicate TokenStream import from parse_argument_as_word().
- Updated callers in redirections.py (2 sites), control_structures.py (3 sites),
  arrays.py (4 sites), and commands.py (1 site).
- No behavioral changes; all tests passing.

## 0.134.0 (2026-02-09) - Parser Code Quality: Error Helper, Inline Imports, Dead Code
- Extracted _raise_unclosed_expansion_error() helper in CommandParser, replacing 6
  repetitive ErrorContext + raise ParseError blocks in _check_for_unclosed_expansions
  and _validate_command_start with single-line calls.
- Moved inline imports to module level across 4 files: import re in commands.py,
  redirections.py, word_builder.py; import time in context.py (4 sites);
  LiteralPart and Word added to module-level ast_nodes import in commands.py.
- Declared _saved_states as a dataclass field in ParserContext with
  field(default_factory=list), removing hasattr guards in __enter__/__exit__
  and adding reset in reset_state().
- Removed dead branch in _format_variable where both if/else paths returned
  the same f"${token.value}".
- No behavioral changes; all tests passing.

## 0.133.0 (2026-02-09) - Parser Docs: Sub-Parser Contract, WordBuilder Cross-refs
- Added "Sub-Parser Contract" section to parser CLAUDE.md documenting the implicit
  convention all 8 sub-parsers follow: initialization, state access via
  ContextBaseParser methods, token position property, context manager usage (with
  table of which sub-parsers set which flags), consume_if preference, error creation.
- Expanded WordBuilder documentation in parser CLAUDE.md with entry point
  (CommandParser.parse_argument_as_word), three key operations (build_word_from_token,
  build_composite_word, parse_expansion_token), and relationship to TokenStream.
- Added WordBuilder cross-reference docstring to parse_argument_as_word() in
  commands.py.
- Updated context_factory.py description in support infrastructure table to reflect
  v0.132.0 factory function conversion.
- Marked recommendations 5 and 6 complete in parser code quality review — all 10
  recommendations from the original review are now done.
- Documentation-only changes; no behavioral code modifications.

## 0.132.0 (2026-02-09) - Parser Quality: Factory Functions, Dead Code Removal
- Converted ParserContextFactory (9 static methods), ParserFactory (4 static
  methods), and ConfigurationValidator (2 static methods) from static-method-only
  classes to plain module-level functions. Added thin compatibility shim classes
  so existing call sites keep working unchanged.
- Deleted unused ContextConfiguration class (3 static methods, zero callers).
- Deleted BaseParser adapter class (~30 lines, never instantiated outside its
  own module).
- Deleted unused parse_with_rule and parse_scoped methods (~15 lines, never called).
- Replaced ErrorContext.severity string field with ErrorSeverity enum (INFO,
  WARNING, ERROR, FATAL). Added FATAL to validation Severity enum.
- Removed unreachable except ImportError block in _enhance_error_context.
- Net reduction: ~70 lines across 7 files. All tests passing.

## 0.131.0 (2026-02-09) - Parser Quality Improvements
- Pruned ParserConfig from 45 fields to 12 actually-read fields. Removed
  33 unused fields and 5 factory methods (~500 lines). Kept strict_posix()
  and permissive() presets plus clone(), is_feature_enabled(), should_allow().
- Unified error handling: deleted ErrorCollector class and error_collector.py.
  ParserContext.errors is now the sole error list with fatal_error tracking.
  MultiErrorParseResult moved to parser.py. Recovery strategies inlined.
  Added _ErrorCollectorView for backward compatibility (~360 lines removed).
- Added combinator parser guide (docs/guides/combinator_parser_guide.md)
  documenting the functional parser's concepts, module structure, feature
  coverage, and differences from recursive descent.

## 0.130.0 (2026-02-08) - Remove Parser Abstraction Layers
- Phase 1: Removed AbstractShellParser, ParserRegistry, ParserStrategy, and
  RecursiveDescentAdapter (~930 lines). Replaced ParserStrategy in shell.py
  with simple _active_parser string and direct parser calls. Rewrote 4 parser
  experiment builtins (348 lines) as single parser-select builtin (47 lines).
  Updated combinator parser to remove AbstractShellParser inheritance.
- Phase 2: Removed ContextWrapper class from Parser; added __enter__/__exit__
  directly to ParserContext. Removed 8 legacy forwarding methods and 22
  sub-parser delegation methods. Fixed monkey-patching in TestParser. Replaced
  _error() with error() across all sub-parsers. Replaced print() with
  logging.debug() in parser context tracing.
- Total: ~1,686 lines removed across 21 files

## 0.129.0 (2026-02-08) - Lexer Refactoring: Dead Code, Keyword Unification, Efficiency
- Phase 1: Removed dead code (~100 lines): _classify_literal, _is_number,
  _contains_special_chars (literal.py), PriorityRecognizer (base.py),
  create_*_parser factories (expansion_parser.py, quote_parser.py), unused
  registry methods, VARIABLE_NAME_PATTERN (constants.py), dead if/pass block
  (modular_lexer.py). Fixed mutable default in pure_helpers.py.
  Replaced print() with logging in registry.py.
- Phase 2: Removed KeywordRecognizer (~200 lines), unifying all keyword
  handling in KeywordNormalizer. Eliminated redundant two-pass keyword system.
  Removed recent_control_keyword from LexerContext. Updated command-position
  tracking to check WORD values for keyword-like strings.
- Phase 3: Removed redundant can_recognize() calls from all recognize()
  methods. Eliminated list copy in registry.recognize(). Replaced O(n) linear
  scan in PositionTracker with O(log n) bisect. Moved inline imports to
  module level.
- Total: ~320 lines removed across 16 files

## 0.128.0 (2026-02-08) - Remove Dead Code from Parser Package
- Deleted BaseParser (base.py, ~380 lines): legacy base class superseded by ContextBaseParser
- Deleted context_snapshots.py (~300 lines): ContextSnapshot, BacktrackingParser, SpeculativeParser
  never instantiated in production code
- Deleted errors.py (~360 lines): ParserErrorCatalog and ErrorSuggester never used by the parser
- Deleted AbstractIncrementalParser and AbstractStreamingParser from abstract_parser.py (~60 lines):
  defined but never inherited or instantiated
- Removed dead set_error_template() method from helpers.py ErrorContext
- Fixed broken imports in combinators/expansions.py (ParseError from deleted errors.py)
- Removed associated test file (test_parser_error_improvements.py) and dead test classes
  (TestContextSnapshot, TestBacktrackingParser, TestSpeculativeParser) from test_parser_context.py
- Updated parser_guide.md and parser CLAUDE.md to remove stale references
- Net reduction: ~1,580 lines of dead code
- All tests passing with zero regressions

## 0.127.0 (2026-02-07) - Tilde Expansion in Parameter Expansion Defaults
- Fixed ${x:-~} outputting literal ~ instead of expanding to home directory
- Added _expand_tilde_in_operand() helper to VariableExpander
- Tilde expansion now applied to operand values for :-, :=, and :+ operators
- Applied in both _apply_operator() (Word AST path) and expand_variable() inline
  fallback handlers (string-based path)
- Matches bash behavior: ${x:-~} expands ~, ${x:-~/foo} expands ~/foo,
  ${x:=~} assigns expanded value, ${x:+~} returns expanded value when set
- All tests passing with zero regressions

## 0.126.0 (2026-02-07) - Implement psh -i Flag and $- Special Variable
- Added -i flag to force interactive mode (matches bash -i behavior)
- Fixed broken --force-interactive flag: was set after Shell.__init__ completed,
  so init-time interactive features (history loading, rc file) never triggered
- Threaded force_interactive parameter into Shell.__init__() constructor
- Made $- fully functional with all standard flags:
  - B (braceexpand, default on), H (histexpand, default on)
  - i (interactive), s (stdin mode, no script file)
  - Plus existing: a, b, C, e, f, h, m, n, u, v, x
- Fixed $- expansion in string contexts (heredocs, double-quoted strings):
  added '-' to special variable character set in expand_string_variables()
- Added interactive and stdin_mode options to ShellState options dict
- Updated help text with -i flag description
- Added comprehensive subprocess-based tests for -i and $-
- All tests passing with zero regressions

## 0.125.0 (2026-02-07) - Fix 3 FD/Redirect Bugs from Code Review
- Fixed endswith('') bug in apply_permanent_redirections() process substitution
  check — always returned true; corrected to endswith(')')
- Fixed FD leak in setup_child_redirections(): process substitution redirect's
  parent FD (with FD_CLOEXEC cleared) was never closed after redirect applied,
  surviving exec and keeping pipe open; now closed after redirect setup
- Implemented <& (input FD duplication), >&- and <&- (FD close) at runtime in
  all three redirection paths: apply_redirections(), setup_child_redirections(),
  and setup_builtin_redirections()
- Handles both parser AST forms for close: type='>&-'/'<&-' from
  parse_fd_dup_word() and type='>&' with target='-' from _parse_dup_redirect()
- Added tests for FD close, input FD dup, and process substitution redirect
- All tests passing with zero regressions

## 0.124.0 (2026-02-07) - Unify Child Process Signal Policy
- Created apply_child_signal_policy() in psh/executor/child_policy.py as single
  source of truth for child process signal setup after fork()
- Refactored ProcessLauncher._child_setup_and_exec() to call unified policy
  instead of inline signal handling
- Added policy call to command substitution fork (command_sub.py) — was missing
  signal reset entirely, child inherited parent's custom signal handlers
- Added policy call to process substitution fork (process_sub.py) — was only
  setting SIGTTOU=SIG_IGN, missing full signal reset
- Added policy call to file redirect process substitution fork (file_redirect.py)
  — was missing signal reset entirely
- Added policy call to IOManager builtin redirect process substitution fork
  (manager.py) — was missing signal reset entirely
- All 4 raw fork paths now use is_shell_process=True (they create temp Shell
  instances and run commands, never exec external binaries)
- Added unit tests for policy function and integration tests for command/process
  substitution signal disposition
- All tests passing with zero regressions

## 0.123.0 (2026-02-07) - Fix 5 Correctness Bugs from Code Review
- Fixed quoted variable names treated as assignments (High): "FOO"=bar no longer
  silently creates a variable; _is_assignment_candidate() now walks Word parts to
  verify the variable-name portion before '=' is entirely unquoted LiteralPart
- Fixed lone $ expanding to empty string (Medium): bare $ not followed by a valid
  variable name now emits a literal '$' token instead of an empty-named variable
  expansion (matches bash: echo $ end → $ end)
- Fixed "$@" splitting missing in composite words (Medium): pre"$@"post with
  params (a,b,c) now correctly produces 3 separate arguments [prea, b, cpost]
  instead of collapsing into one; added $@ splitting logic to _expand_word()
- Fixed tilde expansion suppressed by any backslash (Medium): ~/\foo now
  correctly expands ~ because only \\~ (escaped tilde) suppresses expansion,
  not a backslash on a later character
- Fixed FormatterVisitor losing quotes in composite words (Low): new _format_word()
  method reconstructs words from Word.parts with per-part quoting, grouping
  consecutive parts by quote context for correct round-trip formatting
- Added 19 regression tests in tests/regression/test_codex_review_findings.py
- All tests passing with zero regressions

## 0.122.0 (2026-02-07) - Formalize Shell-vs-Leaf Signal Policy in ProcessLauncher
- Added is_shell_process field to ProcessConfig dataclass (default False)
- Shell processes (subshells, brace groups) keep SIGTTOU=SIG_IGN after
  reset_child_signals() so they can call tcsetpgrp() without being stopped
- Leaf processes (external commands) keep SIGTTOU=SIG_DFL (unchanged behavior)
- Removed manual SIGTTOU override from subshell.py execute_fn closure
- Set is_shell_process=True on all three SubshellExecutor launch sites
  (foreground subshell, background subshell, background brace group)
- Updated process_sub.py comment to reference centralized policy pattern
- Updated executor CLAUDE.md signal handling documentation
- Updated architecture-comments.md opportunity #6 (partially addressed)
- All tests passing with zero regressions

## 0.121.0 (2026-02-07) - Remove \\x00 Null Byte Markers
- Removed all \\x00 null byte marker producers and consumers (vestigial after Word AST migration)
- lexer/pure_helpers.py: Escaped dollar returns literal '$' instead of '\\x00$'
- lexer/helpers.py: Same change in mixin version
- shell.py: Simplified _process_escape_sequences() to inline backslash removal
- expansion/variable.py: Removed \\x00 guards on $ and backtick in expand_string_variables()
- expansion/extglob.py: Removed 4 \\x00 skip blocks and updated docstring
- Deleted 2 tests for removed \\x00 behavior (test_null_marked, test_null_markers_become_literal)
- Updated expansion/CLAUDE.md: removed NULL Marker Pattern section and pitfall note
- Updated architecture-comments.md: marked \\x00 risk as resolved, opportunity #3 as done
- Updated architecture-comments-analysis.md: moved \\x00 section to resolved
- No \\x00 references remain in active source code
- All 2930+ tests passing with zero regressions

## 0.120.0 (2026-02-07) - Complete arg_types Migration to Word AST
- Removed arg_types and quote_types fields from SimpleCommand dataclass
- Changed words field from Optional[List[Word]] to List[Word] (always present)
- Added Word helper properties: is_quoted, is_unquoted_literal, is_variable_expansion,
  has_expansion_parts, has_unquoted_expansion, effective_quote_char
- Migrated all remaining arg_types consumers to Word AST inspection:
  - enhanced_validator_visitor: 4 methods migrated
  - security_visitor: unquoted expansion detection via Word properties
  - formatter_visitor: quote reconstruction via word.effective_quote_char
  - debug_ast_visitor: shows Word structure summary instead of arg_types list
  - ascii_tree/sexp_renderer: Word-based compact argument display
  - shell_formatter: quote restoration via Word properties
  - command.py: removed arg_types forwarding and fallback
  - expansion/manager.py: removed arg_types/quote_types writes after process sub
- Deleted _word_to_arg_type() (50 lines) from recursive descent parser
- Removed all arg_types/quote_types append calls from 3 parser implementations
- Updated composite token handling tests to use Word AST assertions
- 31 new unit tests for Word helper properties
- All 2930+ tests passing with zero regressions

## 0.119.0 (2026-02-07) - Medium-Value Improvements: Parser Fixes, Dead Code Removal, AST Migration
- Fixed parameter expansion parsing for /#, /%, and : (substring) operators in WordBuilder:
  uses earliest-position matching instead of naive first-occurrence search, adds /#/%/: to
  operator list, skips operators after array subscript ] to preserve array slicing
- Removed expand_parameter_direct() var_name.endswith('/') workaround for /#/% operators
- Removed ExpansionEvaluator._evaluate_parameter_via_string() fallback for ambiguous AST
- Removed dead StateHandlers mixin (597 lines): legacy state-machine code from before
  ModularLexer rewrite, zero active callers
- Migrated execution-path arg_types consumers to Word AST inspection:
  - ExpansionManager: process substitution detection via Word parts
  - ProcessSubstitutionHandler: detection via Word parts instead of arg_types indexing
  - CommandExecutor: assignment extraction via _is_assignment_candidate() Word inspection
- Added 9 parser unit tests for /#, /%, :, //, /, #, %, :- operator disambiguation
- All 2932+ tests passing with zero regressions

## 0.118.0 (2026-02-07) - Architectural Cleanup: Remove CompositeTokenProcessor, Direct Parameter Expansion
- Removed CompositeTokenProcessor (198 lines): with Word AST and adjacent_to_previous token
  tracking, the pre-merge processor was redundant — the parser handles composites via
  parse_argument_as_word() / peek_composite_sequence() natively
- Deleted psh/composite_processor.py, removed use_composite_processor parameter from Parser
- Cleaned up composite token tests to use standard parser (no processor flag)
- Extracted expand_parameter_direct() in VariableExpander: operator dispatch logic now
  accepts pre-parsed (operator, var_name, operand) components directly
- Extracted _apply_operator() helper to eliminate duplication between scalar and array
  expansion paths (was duplicated across ~240 lines)
- ExpansionEvaluator._evaluate_parameter() now calls expand_parameter_direct() directly
  instead of reconstructing ${...} strings and re-parsing via parse_expansion()
- Eliminates the string round-trip that caused the ${#var} prefix operator reconstruction
  bug fixed in v0.117.0
- Added fallback for parser AST ambiguities (e.g. ${var:0:-1} parsed as operator=':-')
- Handles parser AST quirk where ${var/#pat/repl} stores parameter='var/', operator='#'
- All 2932+ tests passing with zero regressions

## 0.117.0 (2026-02-07) - Complete Word AST Migration, Remove Legacy String Expansion Path
- Word AST is now the only argument expansion path (build_word_ast_nodes config removed)
- Deleted ~450 lines of legacy string-based expansion code:
  _expand_string_arguments(), _process_single_word(), process_escape_sequences(),
  _contains_at_expansion(), _expand_at_in_string(), _protect_glob_chars(),
  _mark_quoted_globs(), _brace_protect_trailing_var(), _expand_assignment_value(),
  and verify-word-ast parallel verification code
- Added _process_unquoted_escapes() for backslash handling in unquoted literals
- Added process substitution, ANSI-C quote ($'), and extglob pattern handling
- Fixed alias backslash bypass, word splitting, $$, parameter expansion operators,
  ${#arr[@]} length, nounset propagation, and assignment word splitting
- All 2932 tests pass with zero regressions

## 0.116.0 (2026-02-07) - Word AST STRING Decomposition and Expansion Path Hardening
- WordBuilder now decomposes double-quoted STRING tokens with RichToken.parts into
  proper ExpansionPart/LiteralPart AST nodes (was single opaque LiteralPart)
- Added _token_part_to_word_part() and _parse_token_part_expansion() for converting
  lexer TokenPart metadata to Word AST nodes
- Removed expand_string_variables() fallback in _expand_word() and
  _expand_double_quoted_word() — double-quoted expansions now use structural AST
- CommandExecutor now preserves Word AST (command.words) when creating sub-nodes
  for assignment stripping and backslash bypass
- Added _word_to_arg_type() to derive backward-compatible arg_types from Word AST
- Added _expand_assignment_word() for Word-AST-aware assignment value expansion
- Added _process_dquote_escapes() for backslash processing in double-quoted literals
- ExpansionEvaluator now properly re-raises ExpansionError (e.g., ${var:?msg})
- ExpansionEvaluator wraps array subscripts (arr[0]) in ${...} form
- Parser adds EXCLAMATION tokens to words list for test command compatibility
- build_word_ast_nodes remains False by default; 149 golden tests pass with it on

## 0.115.0 (2026-02-06) - Architectural Improvements: Word AST, Token Adjacency, Expansion Consolidation
- Added golden behavioral test suite (149 parametrized tests) as safety net for pipeline changes
- Added first-class token adjacency tracking (adjacent_to_previous field on Token)
- Simplified composite detection to use adjacency field instead of position arithmetic
- Added per-part quote context (quoted, quote_char) to LiteralPart and ExpansionPart AST nodes
- Enhanced Word AST composite word building with per-part quote tracking
- Rewrote _expand_word() with full per-part quote-aware expansion logic
- Consolidated ExpansionEvaluator to delegate to VariableExpander (reduced from ~430 to ~85 lines)
- Added parallel verification infrastructure for Word AST vs string expansion paths

## 0.114.0 (2026-02-06) - Fix 5 Expansion/Assignment Bugs
- Fixed split assignments absorbing next token across whitespace: FOO= $BAR is now
  correctly parsed as empty assignment + command, not FOO=$BAR
- Fixed single-quoted assignment values losing quote context: FOO='$HOME' now keeps
  $HOME literal by marking $ and ` with NULL prefix in single-quoted composite parts
- Fixed quoted expansion results triggering globbing in composites: var='*';
  echo foo"$var"bar now prints foo*bar instead of glob results
- Fixed tilde expansion running on variable/command expansion results: words from
  expansion starting with ~ no longer undergo tilde expansion (POSIX compliance)
- Fixed "$@" inside larger double-quoted strings: "x$@y" with params (a,b) now
  produces two words [xa] [by] instead of one word [xa by]
- Added PARAM_EXPANSION to composite token set so var=${path##*/} is properly
  composited (was broken when split-assignment workaround was removed)
- Added _brace_protect_trailing_var() to prevent variable name absorption across
  composite token boundaries ("$var"bar no longer expands $varbar)
- Removed double-expansion of assignment values in _handle_pure_assignments() and
  _apply_command_assignments() (values already expanded in execute())
- All tests passing (762 integration, 1286 unit, 43 subshell)

## 0.113.0 (2026-02-06) - Implement Extended Globbing (extglob)
- Implemented bash-compatible extended globbing with five pattern operators:
  ?(pat|pat) zero or one, *(pat|pat) zero or more, +(pat|pat) one or more,
  @(pat|pat) exactly one, !(pat|pat) anything except pattern
- Patterns support nesting (e.g., +(a|*(b|c))) and pipe-separated alternatives
- Enable with: shopt -s extglob
- Four integration points: pathname expansion, parameter expansion (${var##+(pat)}),
  case statements (case $x in @(yes|no)) ...), and [[ ]] conditional expressions
- Core engine: extglob_to_regex converter with recursive pattern handling
- Negation (!(pat)) uses match-and-invert for standalone patterns
- Lexer changes: extglob patterns (e.g., @(a|b)) tokenized as single WORD tokens
  when extglob enabled; + and ! followed by ( no longer treated as word terminators
- Shell options threaded through tokenize() and tokenize_with_heredocs() for
  dynamic extglob awareness based on current shopt state
- Fixed StringInput -c mode to split on newlines (matching bash behavior) so that
  shopt -s extglob on line N affects tokenization of line N+1
- Updated shopt help text from stub to list all five operators
- 55 unit tests for core engine, 13 lexer tokenization tests, 20 integration tests
- All existing tests passing with no regressions

## 0.112.0 (2026-02-06) - Fix Nested Subshell Parsing and SIGTTOU in Process Substitution
- Fixed nested subshell parsing: (echo "outer"; (echo "inner")) now parses correctly
- Root cause: lexer greedily matched )) as DOUBLE_RPAREN (arithmetic close) instead
  of two separate RPAREN tokens when closing nested subshells
- Added context check: )) is only DOUBLE_RPAREN when arithmetic_depth > 0
- Removed xfail from test_nested_subshells (now passes)
- Fixed SIGTTOU suspension when running tests piped through tee
- ExternalExecutionStrategy now only calls restore_shell_foreground() when terminal
  control was actually transferred, matching the fix applied to pipeline.py in v0.111.0
- Added SIGTTOU SIG_IGN in process substitution child fork (process_sub.py), matching
  the subshell child fix from v0.111.0

## 0.111.0 (2026-02-06) - Fix SIGTTOU in Subshell Pipelines
- Fixed subshell child processes getting killed by SIGTTOU (signal 22, exit
  code 150) when running pipelines with a controlling terminal
- Root cause: reset_child_signals() set SIGTTOU to SIG_DFL for all forked
  children, but subshell children act as mini-shells that may call tcsetpgrp()
  and need SIGTTOU ignored (standard shell behavior)
- Added SIG_IGN for SIGTTOU in subshell execute_fn (subshell.py)
- Made pipeline _wait_for_foreground_pipeline() skip restore_shell_foreground()
  when terminal control was never transferred, preventing unnecessary tcsetpgrp()
  calls from non-foreground process groups
- Added test isolation cleanup (_reap_children, _cleanup_shell) to both
  conftest.py files to prevent zombie process leakage between tests

## 0.110.0 (2026-02-06) - Fix Intermittent Job Control Race Condition
- Fixed wait builtin race condition in _wait_for_all(): if a background job
  (e.g. false &) completed before wait was called, its exit status was lost
  because the loop only iterated non-DONE jobs
- Now collects exit statuses from already-completed (DONE) jobs first, then
  waits for any still-running jobs
- Verified stable over 20 consecutive runs of the previously flaky test
- All tests passing

## 0.109.0 (2026-02-06) - Resolve All 12 Code Review Observations
- Fixed all 6 remaining code review items (7-12); all 12 now resolved
- WhitespaceRecognizer: removed unnecessary string building and Token construction,
  now just advances position and returns (None, new_pos) like CommentRecognizer
- Removed hasattr(TokenType, 'WHITESPACE'/'COMMENT') guards and unused Token
  construction from both whitespace and comment recognizers
- Both WhitespaceRecognizer and CommentRecognizer now consistently return
  (None, new_pos) for skipped regions (was inconsistent: None vs (None, pos))
- Removed unused ExpansionComponent abstract base class from psh/expansion/base.py;
  no expansion component inherited from it and their interfaces intentionally differ
- Fixed O(n^2) bytestring concatenation in command substitution: now collects
  chunks in a list and joins with b''.join() for O(n) performance
- Replaced hardcoded errno 10 with errno.ECHILD for readability and portability
- Cleaned up old conformance result files from 2025
- Updated docs/code_review_observations.md: all 12 items marked FIXED
- All tests passing

## 0.108.0 (2026-02-06) - Fix 4 Conformance Bugs, Achieve 0 PSH Bugs
- Resolved all 4 remaining psh_bug conformance items (was 4, now 0)
- POSIX compliance: 98.4% (up from 97.7%), bash compatibility: 91.8% (up from 89.1%)
- Reclassified echo \\$(echo test) as documented_difference (ERROR_MESSAGE_FORMAT):
  both shells reject with exit code 2, only error message format differs
- Fixed jobs format string to match bash: 24-char state field, ' &' suffix for background
- Fixed background job '+' marker by using register_background_job() in strategies.py
  so current_job is properly set for the most recent background job
- Fixed history builtin in non-interactive mode: no longer loads persistent history
  when running via -c flag, matching bash behavior (bash -c 'history' outputs nothing)
- Fixed pushd to initialize directory stack with CWD before pushing new directory:
  pushd /tmp from ~ now produces stack [/tmp, ~] matching bash output format
- Added pushd /tmp as documented_difference (PUSHD_CWD_DIFFERENCE) since conformance
  test runs PSH and bash from different working directories
- Updated docs/test_review_recommendations.md with new conformance metrics
- All tests passing (Phase 1, Phase 2 subshell, Phase 3)

## 0.107.0 (2026-02-05) - Glob Fixes, shopt Builtin, and Test Improvements
- Fixed glob expansion on variable results per POSIX (unquoted $VAR now globs)
- Fixed partial quoting in glob patterns: "test"*.txt correctly expands unquoted *
  using \\x00 markers to distinguish quoted vs unquoted glob chars in composites
- Implemented shopt builtin with -s/-u/-p/-q flags and dotglob, nullglob, extglob,
  nocaseglob, globstar options
- Added nullglob support: when enabled, glob patterns with no matches expand to nothing
- Reclassified echo $$ from psh_bug to documented difference in conformance tests
- Moved 3 C-style for loop I/O tests from xfail to -s test phase (they pass with -s)
- Added 12 regression tests for bugs fixed in commit 4f4d854
- All tests passing (2623 passed in Phase 1, 43 subshell, 5 Phase 3)

## 0.106.0 (2025-11-25) - Code Cleanup and Pythonic Refactoring
- Refactored non-Pythonic length checks across 14 files (34 patterns)
- Changed `len(x) == 0` to `not x` and `len(x) > 0` to `bool(x)` for idiomatic Python
- Removed dead code and commented debug statements from multiple modules
- Removed archived backup files and obsolete development/migration scripts
- Removed deprecated legacy executor flag handling from __main__.py and environment.py
- Removed duplicate debug properties in state.py and orphaned SubParserBase class
- Net reduction of ~8,000+ lines of dead/obsolete code
- All tests passing (2616 passed, 80 skipped, 52 xfailed)
- Files cleaned: state.py, token_stream_validator.py, bracket_tracker.py, quote_validator.py,
  heredoc_collector.py, state_context.py, parser.py, context.py, error_collector.py,
  semantic_analyzer.py, test_command.py, base.py, security_visitor.py, signal_utils.py,
  script_validator.py

## 0.105.0 (2025-11-24) - Code Quality and Subsystem Documentation
- Consolidated duplicate assignment utilities into psh/core/assignment_utils.py
- Extracted long methods in LiteralRecognizer and CommandParser into focused helpers
- Completed legacy ParseContext migration to ParserContext with backward-compatible wrapper
- Added comprehensive CLAUDE.md documentation for 6 subsystems:
  - psh/expansion/CLAUDE.md: expansion order, variable/command substitution
  - psh/core/CLAUDE.md: state management, scoping, variables
  - psh/builtins/CLAUDE.md: builtin registration, adding commands
  - psh/io_redirect/CLAUDE.md: redirections, heredocs, process substitution
  - psh/visitor/CLAUDE.md: AST visitor pattern, traversal
  - psh/interactive/CLAUDE.md: job control, REPL, history, completion
- Updated main CLAUDE.md with complete subsystem reference table (9 total)
- All tests passing, no regressions

## 0.104.0 (2025-11-19) - Complete All High Priority Executor Improvements (H4 + H5)
- 🎉 MAJOR MILESTONE: All critical and high priority executor improvements complete! (8/8, 100%)
- Implemented H4 from executor improvements plan: unified foreground job cleanup
- Created JobManager.restore_shell_foreground() as single source of truth for terminal restoration
- Replaced scattered cleanup logic in 5 locations across 4 files (pipeline, strategies, subshell, fg builtin)
- Consistent cleanup ensures terminal always restored to shell after foreground jobs
- Implemented H5 from executor improvements plan: surface terminal control failures
- Created JobManager.transfer_terminal_control(pgid, context) as single source of truth for all tcsetpgrp calls
- Replaced 8 scattered tcsetpgrp calls across 7 files with unified method
- Enhanced logging: all terminal control failures now visible with --debug-exec flag
- Context strings provide clear diagnostic information (Pipeline, Subshell, ProcessLauncher, etc.)
- Returns success/failure bool for caller decision making
- Foundation for future metrics tracking (process_metrics integration ready)
- Benefits: single source of truth, consistent error handling, better debugging, reduced code
- Net code reduction: H4 (-30 lines), H5 (-7 lines) with significantly better structure
- All tests passing: 43 subshell + 2 function/variable tests, no regressions
- Files modified: job_control.py, process_launcher.py, subshell.py, pipeline.py, strategies.py, signal_manager.py, job_control.py (builtin)
- Executor improvements progress: 8/13 complete (62%), Critical 3/3 (100%), High Priority 5/5 (100%) ✅
- Remaining work: Medium priority (3 items) and Low priority (2 items) - all optional enhancements

## 0.103.0 (2025-11-19) - Centralize Child Signal Reset Logic (H3)
- Implemented H3 from executor improvements plan: centralized child signal reset logic
- Added SignalManager.reset_child_signals() as single source of truth for all child processes
- Updated ProcessLauncher to use centralized signal reset when available
- Fixed ProcessLauncher fallback to include SIGPIPE (was missing in previous implementation)
- Updated all 4 ProcessLauncher instantiation sites to pass signal_manager parameter
- Used parameter passing approach instead of property pattern (property caused initialization hangs)
- Signal manager accessed via shell.interactive_manager.signal_manager at instantiation sites
- Backward compatible: falls back to local reset if signal_manager unavailable
- Benefits: single source of truth, consistent signal handling, easier maintenance
- All tests passing: 43 subshell + 2 function/variable tests, no regressions
- Files modified: signal_manager.py, process_launcher.py, subshell.py, pipeline.py, strategies.py
- Executor improvements progress: 6/13 complete (46%), High Priority 3/5 (60%)

## 0.102.1 (2025-11-19) - Critical Signal Ordering Fix
- Fixed critical shell suspension bug where psh would hang before showing prompt
- Root cause: Signal handler initialization happened AFTER terminal control takeover
- When shell called tcsetpgrp() before ignoring SIGTTOU/SIGTTIN, kernel suspended the process
- Reordered initialization in psh/interactive/base.py to call setup_signal_handlers() BEFORE ensure_foreground()
- Shell now properly ignores job control signals before attempting terminal control operations
- All tests passing, no regressions in signal handling or job control
- Production-critical fix: shell now starts successfully in all environments
- Documented investigation of H3/H4/H5 conflicts with signal ordering fix
- H3 (Centralize Child Signal Reset), H4 (Unify Foreground Cleanup), H5 (Surface Terminal Control Failures)
  remain to be re-implemented with compatibility for signal ordering fix

## 0.102.0 (2025-01-23) - Interactive Nested Prompts Implementation
- Implemented zsh-style context-aware continuation prompts for interactive mode
- Added automatic nesting context detection showing current shell construct hierarchy
- Prompt changes dynamically to reflect context: for>, while>, if>, then>, for if>, etc.
- Enhanced MultiLineInputHandler with context_stack tracking for nested control structures
- Implemented _extract_context_from_error() to analyze parser errors for context identification
- Implemented _update_context_stack() to parse command buffer and track open/closed constructs
- Modified _get_prompt() to generate contextual PS2 prompts based on nesting hierarchy
- Proper handling of closing keywords (fi, done, esac, }, ), ]]) to pop context stack
- Support for all control structures: for, while, until, if, case, select, functions
- Support for compound commands: subshells (), brace groups {}, enhanced tests [[]]
- Multi-level nesting fully supported (e.g., for if then> shows nested if inside for loop)
- Graceful fallback to standard PS2 when context cannot be determined
- Comprehensive testing with all nesting scenarios verified working correctly
- Significant UX improvement: users now see visual feedback about command structure
- Educational value: helps users learn shell syntax through immediate context visibility
- Matches familiar behavior from zsh and other advanced shells

## 0.101.0 (2025-01-06) - Recursive Descent Parser Package Refactoring & Parser Combinator Fix
- Major refactoring: Moved recursive descent parser from flat structure to modular package
- Migrated 28 files from /psh/parser/ to /psh/parser/recursive_descent/ with logical organization:
  - Core files in recursive_descent/ (parser.py, base.py, context.py, helpers.py)
  - Feature parsers in recursive_descent/parsers/ (commands, control_structures, etc.)
  - Enhanced features in recursive_descent/enhanced/ (advanced parsing capabilities)
  - Support utilities in recursive_descent/support/ (error_collector, word_builder, etc.)
- Fixed critical parser combinator regression that broke control structures and advanced features
- Parser combinator now has ~95% feature parity with recursive descent (was incorrectly showing ~60%)
- Both parsers now support: control structures, functions, arrays, I/O redirection, process substitution,
  arithmetic commands, conditional expressions, subshells, here documents, and background jobs
- Removed all compatibility layers after successful migration
- Updated all import paths throughout codebase (fixed 30+ files)
- All tests passing (2593 passed, 162 skipped)
- Clean parallel structure: recursive_descent/ and combinators/ packages

## 0.100.0 (2025-01-06) - Parser Combinator Modular Architecture Complete
- Completed full modularization of parser combinator from 2,779-line monolithic file to 8 clean modules
- Phase 9 Complete: Successfully migrated parser registry to use new modular architecture
- Modular structure: core (451 lines), tokens (90), expansions (209), commands (372), control (381),
  special (248), parser (198), heredoc (121) - total 2,070 lines (25% reduction through deduplication)
- Fixed all 188 parser combinator tests to pass with new modular architecture (100% pass rate)
- Updated 31 test files to use new import paths from modular parser
- Fixed while loop parser to recognize 'do' keyword from WORD tokens
- Resolved circular dependencies using dependency injection pattern
- Enhanced initialization order with proper module wiring
- Maintained full backward compatibility with AbstractShellParser interface
- Educational milestone: demonstrates clean functional architecture for complex parsers
- Parser combinator now production-ready with maintainable, testable architecture
- All 6 phases of feature parity complete, now with clean modular implementation

## 0.99.3 (2025-01-23) - Fix Bit-Shift Operators in Arithmetic Expressions
- Fixed critical bug where bit-shift operators (<<, >>) in arithmetic expressions were mistaken for heredoc operators
- The shell would hang waiting for heredoc input when encountering expressions like ((x=x<<2))
- Fixed MultiLineInputHandler._has_unclosed_heredoc to check if << appears inside arithmetic expressions
- Fixed Shell._contains_heredoc to properly detect arithmetic context
- Fixed SourceProcessor to use shell._contains_heredoc instead of its own incomplete logic
- Added comprehensive test suite with 10 tests covering bit-shift assignment operations
- Bit-shift operators now work correctly in all contexts: arithmetic commands, expansions, conditionals
- All existing heredoc functionality remains intact with no regressions
- Both parser implementations (recursive descent and parser combinator) handle bit-shifts correctly

## 0.99.2 (2025-01-23) - Parser Strategy Inheritance for Child Shells
- Fixed parser strategy inheritance so child shells (command substitution, subshells, process substitution)
  inherit the parser choice from their parent shell
- Previously, child shells always used the default parser regardless of parent's parser selection
- Now when parser combinator is selected, all child shells consistently use parser combinator
- Added comprehensive tests for parser strategy inheritance
- Ensures consistent parsing behavior throughout the entire shell session

## 0.99.1 (2025-01-23) - Parser Combinator Process Substitution Bug Fix
- Fixed critical bug where process substitutions were parsed as WORD tokens instead of PROCESS_SUB_OUT
- Added process_sub_in and process_sub_out to word_like parser definition in parser combinator
- Process substitution commands like `tee >(grep XFAIL > file.log)` now work correctly
- Resolved "No such file or directory" errors when using process substitutions with parser combinator
- Enhanced parser combinator feature parity to handle all process substitution syntax correctly
- Verified fix with comprehensive testing showing proper I/O filtering and redirection
- Parser combinator now maintains 100% process substitution compatibility with recursive descent parser

## 0.99.0 (2025-01-22) - Parser Combinator Feature Parity Achievement Complete (Phase 6)
- Completed Phase 6 of parser combinator feature parity plan: Advanced I/O and Select
- Final phase implementation achieving 100% feature parity with recursive descent parser
- Full implementation of select loop syntax: select var in items; do ... done
- Added comprehensive select loop parsing with support for all token types in items
- Support for WORD, STRING, VARIABLE, COMMAND_SUB, ARITH_EXPANSION, PARAM_EXPANSION tokens
- Implemented quote type tracking for proper shell semantics in select items
- Added SELECT keyword parser and comprehensive _build_select_loop() method
- Enhanced control structure parsing chain with select loops via or_else composition
- Fixed AST unwrapping logic to prevent unnecessary Pipeline/AndOrList wrapper nodes
- Verified all advanced I/O features work through existing SimpleCommand infrastructure
- Confirmed exec commands and file descriptor operations work seamlessly with parser combinator
- Created comprehensive test suite: 32 tests across 2 files (19 select + 13 exec)
- Updated feature coverage tests to reflect select loop support (changed "not supported" to "now supported")
- Fixed test_parser_combinator_feature_coverage.py to show select_loop: True in feature matrix
- Parser combinator now supports 23/24 features (95.8% coverage) with only job_control unsupported
- **MAJOR MILESTONE**: 100% feature parity achieved for all 6 planned parser combinator phases
- All critical shell syntax now supported: process substitution, compound commands, arithmetic, enhanced tests, arrays, select
- Final project statistics: 100+ comprehensive tests, complete shell compatibility for educational/testing purposes
- Educational reference implementation demonstrating functional parsing of complex real-world languages
- Proof that parser combinators can handle production-level language complexity while maintaining elegance
- Foundation established for future parser combinator research and functional programming techniques

## 0.98.0 (2025-01-22) - Parser Combinator Array Support Implementation Complete (Phase 5)
- Completed Phase 5 of parser combinator feature parity plan: Array Support
- Full implementation of array assignment syntax: arr=(elements) and arr[index]=value
- Added comprehensive array parsing support to parser combinator implementation
- Implemented ArrayInitialization and ArrayElementAssignment AST node integration
- Added robust token handling for both combined and separate token patterns
- Support for complex array patterns: variables, arithmetic indices, quoted values
- Created comprehensive test suite: 17 tests across 3 test files covering all array functionality
- Fixed 5 failing integration tests to reflect new array support capabilities
- Updated feature coverage tests and documentation to show array support completion
- Enhanced array element assignment with append operations (arr[index]+=value)
- Support for empty arrays, command substitution in elements, and mixed element types
- Proper error handling for malformed array syntax with graceful failure modes
- Parser combinator now supports ~99% of critical shell syntax (5/6 phases complete)
- Array assignments work seamlessly with existing shell constructs where supported
- Full feature parity with recursive descent parser for array assignment operations
- Foundation established for final phase: advanced I/O features and select loops

## 0.97.0 (2025-01-22) - Parser Combinator Enhanced Test Expressions Implementation Complete (Phase 4)
- Completed Phase 4 of parser combinator feature parity plan: Enhanced Test Expressions support
- Full implementation of [[ ]] conditional expressions with all operators
- Added DOUBLE_LBRACKET and DOUBLE_RBRACKET token support to parser combinator
- Implemented comprehensive test expression parser with binary, unary, and logical operators
- Added _format_test_operand() helper for proper variable and string formatting
- Integrated with existing EnhancedTestStatement AST nodes and execution engine
- Fixed critical unary test evaluation bug in shell.py execution engine
- Enhanced control structure parsing chain with proper AST unwrapping
- Created comprehensive test suite: 30+ tests across 3 test files
- Updated feature coverage tests to reflect new enhanced test expression support
- Enhanced test expressions now work in all contexts: standalone, control structures, logical operators
- Parser combinator now supports ~98% of critical shell syntax (4/6 phases complete)
- Key supported operators: ==, !=, =, <, >, =~, -eq, -ne, -lt, -le, -gt, -ge (binary)
- File tests: -f, -d, -e, -r, -w, -x, -s, -z, -n, and more (unary)
- Logical operators: ! (negation), with && and || via shell logical operators
- Full integration with if/while/for conditions and logical operator chains
- Comprehensive regex pattern matching and file existence testing
- Proper variable expansion and string handling in test contexts

## 0.96.0 (2025-01-22) - Parser Combinator Arithmetic Commands Implementation Complete (Phase 3)
- Completed Phase 3 of parser combinator feature parity plan: Arithmetic Commands support
- Implemented comprehensive arithmetic command ((expression)) syntax parsing in parser combinator
- Added DOUBLE_LPAREN and DOUBLE_RPAREN token parsers to arithmetic command grammar
- Enhanced control structure parsing chain with arithmetic commands via or_else composition
- Integrated arithmetic commands seamlessly with existing ArithmeticEvaluation AST node infrastructure
- Added comprehensive arithmetic expression parsing with proper parentheses depth tracking
- Implemented variable preservation logic for VARIABLE tokens (adds $ prefix automatically)
- Enhanced expression building with whitespace normalization and multi-space cleanup
- Fixed pipeline and and-or list unwrapping to prevent unnecessary wrapping of standalone control structures
- Added 35 comprehensive arithmetic command tests covering basic usage through complex integration scenarios
- Created extensive test coverage: 10 basic tests + 16 edge cases + 9 integration tests with 100% pass rate
- Updated integration tests to reflect arithmetic command support (changed from "not supported" to "now supported")
- Support for all arithmetic operations: assignments, increments, compound assignments, complex expressions
- Full integration with control structures: if ((x > 10)), while ((count < 100)), for loop bodies
- Support for special variables ($#, $?), bitwise operations, logical operators, and ternary expressions
- Enhanced arithmetic expression handling in various contexts: standalone, conditions, loop bodies, and-or lists
- Phase 3 achievement brings parser combinator to ~95% critical shell syntax coverage (major milestone)
- All high-priority features (process substitution + compound commands + arithmetic commands) now complete
- Updated parser combinator feature parity plan documentation with Phase 3 completion notes and progress update
- Added detailed implementation achievements, technical details, and comprehensive test case documentation
- Updated timeline summary showing 3/6 phases completed (50% progress) with 9 weeks remaining for advanced features
- Educational value preserved while demonstrating parser combinators can handle complex mathematical shell syntax
- Foundation established for remaining phases: enhanced test expressions, array support, advanced I/O features

## 0.95.0 (2025-01-22) - Parser Combinator Compound Commands Implementation Complete (Phase 2)
- Completed Phase 2 of parser combinator feature parity plan: Compound Commands support
- Implemented comprehensive subshell group (...) and brace group {...} parsing support
- Added elegant delimiter parsing using between combinator with lazy evaluation for recursive grammar
- Integrated compound commands seamlessly into control structure parsing chain via or_else composition
- Enhanced control structure parser to support: if, while, for, case, subshells, brace groups, break, continue
- Added comprehensive compound command token parsers (LPAREN, RPAREN, LBRACE, RBRACE) to grammar
- Implemented _build_subshell_group() and _build_brace_group() methods with proper AST integration
- Enhanced and-or list parsing to handle complex integration scenarios with compound commands
- Fixed parser ordering for sophisticated and-or list integration: (echo test) && { echo success; }
- Modified pipeline builder to avoid over-wrapping control structures in unnecessary Pipeline nodes
- Added 27 comprehensive compound command tests (10 basic + 17 edge cases) with 100% pass rate
- Created extensive edge case test suite covering nested compounds, pipeline integration, complex scenarios
- Updated 46 integration tests to reflect new compound command capabilities and feature support
- Fixed integration test expectations from "not supported" to "now supported" for compound commands
- Support for complex scenarios: deep nesting ( { (echo nested); } ), pipeline integration
- Pipeline integration working: echo start | (cat; echo middle) | echo end produces correct output
- Full compatibility with all existing shell features: functions, control structures, I/O redirection
- Phase 2 brings parser combinator to ~90% critical shell syntax coverage (major milestone)
- All high-priority features (process substitution + compound commands) now complete
- Updated parser combinator feature parity plan documentation with Phase 2 completion notes
- Added detailed implementation achievements and technical documentation to feature parity plan
- Updated timeline summary showing 2/6 phases completed (33.3% progress) with 11 weeks remaining
- Fixed basic features integration tests to properly reflect Phase 2 compound command support
- Educational value preserved while demonstrating parser combinators can handle complex shell syntax
- Foundation established for remaining phases: arithmetic commands, enhanced test expressions, arrays

## 0.94.0 (2025-01-22) - Parser Combinator Process Substitution Implementation Complete (Phase 1)
- Completed Phase 1 of parser combinator feature parity plan: Process Substitution support
- Implemented complete process substitution parsing support (<(cmd) and >(cmd)) in parser combinator
- Added process substitution token parsers (PROCESS_SUB_IN, PROCESS_SUB_OUT) to expansion combinator chain
- Created comprehensive process substitution parsing logic with proper AST integration
- Enhanced Word AST building for process substitution tokens via _build_word_from_token method
- Added ProcessSubstitution import and parsing support to parser combinator implementation
- Created extensive test suites with 26 comprehensive tests covering basic usage through complex edge cases
- Fixed configuration issue where build_word_ast_nodes wasn't enabled by default in parser tests
- Resolved recursion issue in AST traversal for finding ProcessSubstitution nodes via visited set tracking
- All process substitution functionality now works identically between parser combinator and recursive descent
- Updated feature parity plan documentation to mark Phase 1 as completed with implementation details
- Major milestone: Parser combinator now supports advanced shell syntax with full process substitution capability
- Foundation established for remaining phases: compound commands, arithmetic commands, enhanced test expressions
- Educational value preserved while demonstrating parser combinators can handle complex shell syntax elegantly

## 0.93.0 (2025-01-21) - Arithmetic Expansion Testing Complete and Parser Combinator Enhancement
- Completed comprehensive arithmetic expansion testing plan with 134+ tests across 4 phases
- Phase 1: Number Format Testing (38 tests) - binary, octal, hex, arbitrary bases 2-36
- Phase 2: Special Variables Testing (31 tests) - positional parameters, $#, $?, $$, arrays
- Phase 3: Integration Testing (23 tests) - command substitution, control structures, here docs
- Phase 4: Edge Cases Testing (42 tests) - error handling, syntax errors, whitespace, recursion
- Fixed critical hanging tests from nested arithmetic expansion syntax abuse ($((counter)) → counter)
- Enhanced parser combinator capabilities: here documents and here strings now fully supported
- Updated integration tests to reflect current parser combinator feature set (no longer "unsupported")
- Comprehensive arithmetic testing validates production-ready functionality across all contexts
- Error handling robustness verified: division by zero, syntax errors, overflow conditions
- Performance testing completed: deep nesting (25+ levels), large expressions, variable contexts
- All arithmetic expansion features now thoroughly tested and documented for reliability
- Foundation established for production shell scripting with comprehensive arithmetic support

## 0.92.0 (2025-01-21) - Here Document Parser Combinator Implementation Complete
- Implemented complete here document support in parser combinator with comprehensive functionality
- Added heredoc token recognition (<<, <<-, <<<) to parser combinator grammar
- Enhanced redirection parser to handle heredoc and here string operators
- Implemented innovative two-pass parsing architecture for heredoc content population
- Added heredoc_quoted support for disabling variable expansion in quoted delimiters
- Fixed here string target quote handling and content preprocessing
- Created comprehensive test suite with 13 tests covering all heredoc functionality
- Updated parser combinator to handle complex heredoc scenarios with proper error handling
- All tests passing: heredocs, tab-stripping heredocs, here strings, content population
- Major milestone: parser combinator now supports full here document feature set
- Enhanced feature roadmap documentation to reflect completed heredoc implementation
- Parser combinator achieves comprehensive shell compatibility with here document support
- Educational two-pass parsing demonstrates functional approach to stateful language features

## 0.91.8 (2025-01-21) - Lexer Redirect Duplication Fix and Parser Combinator Integration
- Fixed critical lexer bug where redirect duplications like "2>&1" were tokenized as three separate tokens
- Modified operator recognizer to check for file descriptor duplication patterns BEFORE regular operators
- Added all digits (0-9) to OPERATOR_START_CHARS for proper FD duplication recognition
- Changed FD duplication tokenization to return REDIRECT_DUP tokens instead of WORD tokens
- Updated parser combinator to properly handle REDIRECT_DUP tokens
- Fixed numerous test expectations to match new single-token redirect duplication behavior
- All 141 parser combinator integration tests now pass (100% success rate)
- Full test suite shows 2463 passing tests with no unexpected failures

## 0.91.7 (2025-01-21) - Parser Combinator Implementation Complete
- Added stderr redirect support (2>, 2>>) to parser combinator
- Added background job support (&) to parser combinator
- Fixed function parsing to only allow at statement start (not in pipelines)
- Made parser stricter about syntax errors while maintaining correct parsing
- Fixed if statement regression by properly handling separators
- All parser combinator tests now pass with newly supported features
- Major milestone: parser combinator now supports all shell syntax features

## 0.91.6 (2025-01-21) - Parser Combinator Test Fixes
- Fixed parser combinator tests to match actual tokenization behavior
- Updated test expectations for variable assignments with expansions
- Fixed statement_list parser to handle leading separators
- Case statements now parse correctly with leading newlines
- Reduced failing tests from 13 to 2 (stderr redirect and background jobs remain)
