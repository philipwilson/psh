"""Source file and command buffer processing.

The line-gathering loop here drives the shared completeness oracle
(`command_accumulator.CommandAccumulator`): each physical line is fed to
the accumulator, which answers NeedMore (keep reading — inside a heredoc
body, an unclosed quote, an open `if`, ...) or Complete (execute). The
accumulator already trial-parsed the command, so when the recursive-descent
parser is active the execution path reuses its AST instead of parsing the
same text twice.
"""
import dataclasses
import sys
from typing import TYPE_CHECKING, Any, Optional, cast

from ..ast_nodes import ASTNode, StatementList, TopLevel
from ..lexer import UnclosedQuoteError, tokenize
from ..parser import ParseError
from ..utils import contains_heredoc
from .base import ScriptComponent
from .command_accumulator import CommandAccumulator, Complete, NeedMore

if TYPE_CHECKING:
    from ..visitor import EnhancedValidatorVisitor


def _offset_line_numbers(obj: Any, delta: int) -> None:
    """Add *delta* to every stamped ``.line`` in an AST subtree, in place.

    The parser stamps statement nodes with buffer-relative lines; this
    converts them to absolute source lines (offset by where the buffer
    began) once, before execution — so a function body bakes in its
    definition-site lines rather than its call-site line. Recurses through
    ASTNode dataclass fields and list/tuple containers (e.g.
    ``IfConditional.elif_parts``, a list of StatementList tuples). See
    ``ASTNode.line``.
    """
    if isinstance(obj, ASTNode):
        if obj.line is not None:
            obj.line += delta
        if dataclasses.is_dataclass(obj):
            for field in dataclasses.fields(obj):
                _offset_line_numbers(getattr(obj, field.name, None), delta)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _offset_line_numbers(item, delta)


class SourceProcessor(ScriptComponent):
    """Processes input from various sources (files, strings, stdin)."""

    def execute_as_main(self, input_source, add_to_history: bool = True) -> int:
        """Run an input source as the TOP-LEVEL shell input, firing the EXIT trap.

        This is the single chokepoint for every non-interactive whole-shell run
        (`-c`, a script file, piped stdin). The EXIT trap must fire exactly once
        when the shell finishes, no matter HOW it finishes:

        * normal end-of-input — ``execute_from_source`` returns and we fire here;
        * ``set -e`` abort — the executor raises ``SystemExit`` (script mode), so
          we recover the status and still fire here;
        * explicit ``exit`` — the ``exit`` builtin already fired the trap, then
          raised ``SystemExit``; ``execute_exit_trap`` is idempotent so this is a
          no-op, and we recover the status.

        Firing happens AFTER recovering ``exit_code`` but is NOT swallowed: if the
        trap body itself runs ``exit N``, that ``SystemExit`` propagates and
        overrides the status (bash). The trap runs while the run's state ($?, $0,
        positionals) is still in place.
        """
        try:
            exit_code = self.execute_from_source(
                input_source, add_to_history=add_to_history)
        except SystemExit as exc:
            code = exc.code
            exit_code = code if isinstance(code, int) else (0 if code is None else 1)
        self.shell.trap_manager.execute_exit_trap()
        return exit_code

    def execute_from_source(self, input_source, add_to_history: bool = True,
                            base_line: int = 1) -> int:
        """Execute commands from an input source with enhanced processing.

        ``base_line`` offsets the source's own line numbers onto absolute
        lines for ``$LINENO`` (default 1 = no shift). It is >1 only for nested
        executions anchored at an invoking command's line (eval, trap actions);
        see Shell.run_command.
        """
        exit_code = 0
        command_start_line = 0
        accumulator = CommandAccumulator(self.shell)

        # For validation mode, collect all issues across the entire script
        self.validation_visitor: Optional["EnhancedValidatorVisitor"] = None
        if self.shell.validate_only:
            from ..visitor import EnhancedValidatorVisitor
            self.validation_visitor = EnhancedValidatorVisitor()

        while True:
            line = input_source.read_line()
            if self.state.options.get('debug-exec', False):
                print(f"DEBUG source_processor: read line: {repr(line)}", file=sys.stderr)
            if line is None:  # EOF
                # End of input inside a heredoc body: the command never got
                # its delimiter, so it is dropped (no execution, and in
                # validation mode no summary either).
                if accumulator.pending_heredoc:
                    return exit_code
                # Execute any remaining buffered command (a truncated
                # construct parses to "unexpected end of input" here).
                if not accumulator.is_empty:
                    exit_code = self._execute_buffered_command(
                        accumulator.flush(), input_source, command_start_line,
                        add_to_history)
                    if self._should_exit_on_error(exit_code, input_source):
                        return exit_code
                # In validation mode, show final summary at end
                if self.validation_visitor:
                    print(self.validation_visitor.get_summary())
                    # Return exit code based on errors
                    error_count = sum(1 for i in self.validation_visitor.issues
                                    if i.severity.value == 'error')
                    exit_code = 1 if error_count > 0 else 0
                break

            if accumulator.is_empty:
                # Skip empty lines when no command is being built
                if not line.strip():
                    continue
                # Skip comment lines when no command is being built. Only
                # for single-line chunks: a multi-line string (e.g. from
                # run_command(), where StringInput yields the whole string
                # as one "line") may start with a comment yet contain
                # commands — the lexer strips embedded comments during
                # tokenization.
                if line.strip().startswith('#') and '\n' not in line.strip():
                    continue
                # Offset the source's own line number onto an absolute line
                # for $LINENO. base_line is 1 for normal sources (no shift);
                # for eval / trap actions it is the invoking command's line.
                command_start_line = base_line + input_source.get_line_number() - 1

            result = accumulator.feed(line)
            if isinstance(result, NeedMore):
                continue

            if result.error is not None:
                # A real syntax error (not incomplete input): report it
                # against where the command started and reset.
                filename = input_source.get_name() if hasattr(input_source, 'get_name') else 'stdin'
                print(f"{filename}:{command_start_line}: {result.error}", file=sys.stderr)
                command_start_line = 0
                exit_code = 2  # Bash uses exit code 2 for syntax errors
                self.state.last_exit_code = 2
                # In non-interactive mode, exit immediately on parse errors
                if not input_source.is_interactive():
                    return exit_code
                continue

            exit_code = self._execute_buffered_command(
                result, input_source, command_start_line, add_to_history)
            command_start_line = 0
            if self._should_exit_on_error(exit_code, input_source):
                return exit_code

        return exit_code

    def _should_exit_on_error(self, exit_code: int, input_source) -> bool:
        """Whether errexit (`set -e`) aborts the whole source now.

        True when the command failed in a non-interactive source with
        errexit set and the failure context is errexit-eligible (not a
        condition, not negated, ...).
        """
        should_exit = (exit_code != 0 and not input_source.is_interactive()
                       and self.state.options.get('errexit', False)
                       and self.state.errexit_eligible)
        if should_exit and self.state.options.get('debug-exec', False):
            print(f"DEBUG: Exiting due to errexit with code {exit_code}", file=sys.stderr)
        return should_exit

    def _execute_buffered_command(self, complete: Complete, input_source,
                                  start_line: int, add_to_history: bool) -> int:
        """Execute a complete buffered command with enhanced error reporting."""
        command_string = complete.text
        # Skip empty commands and pure single-line comments (a multi-line
        # buffer starting with a comment still contains commands; the lexer
        # strips the comment).
        stripped = command_string.strip()
        if not stripped or (stripped.startswith('#') and '\n' not in stripped):
            return 0

        # Update LINENO special variable with current line number
        if start_line > 0:
            self.shell.state.scope_manager.set_current_line_number(start_line)

        # Verbose mode: echo input lines as they are read
        if self.state.options.get('verbose', False):
            # Echo the command to stderr before execution
            print(command_string, file=sys.stderr)

        # Nested execution (eval, source, trap action) runs inside an outer
        # ExecutorVisitor: control-flow exceptions (break/continue/return)
        # must propagate to the enclosing loop/function instead of being
        # reported as errors here.
        nested = getattr(self.shell, '_current_executor', None) is not None

        try:
            # Process line continuations first
            from .input_preprocessing import process_line_continuations
            command_string = process_line_continuations(command_string)

            # Perform history expansion before tokenization. The accumulator
            # already expanded silently for the completeness trial; this
            # pass is the REPORTING one — it echoes the expansion like bash
            # and prints "event not found" errors.
            if (not self.state.is_script_mode and
                    hasattr(self.shell, 'history_expander')):
                expanded_command = self.shell.history_expander.expand_history(command_string)
                if expanded_command is None:
                    # History expansion failed - this is the proper error path
                    self.state.last_exit_code = 1
                    return 1
                command_string = expanded_command

            # Record in history (interactive use). This is the ONE history
            # writer: it sees the complete logical command, so multi-line
            # constructs land as a single joined entry (bash cmdhist).
            # Done before parsing so that, like bash, commands with syntax
            # errors are still recallable for editing.
            if add_to_history and command_string.strip():
                from ..interactive.history_expansion import contains_history_reference
                if not contains_history_reference(command_string):
                    self.shell.add_history(command_string.strip())

            # Alias expansion is a token-stream transform applied at the
            # lex->parse seam (see the expand_aliases calls below and in
            # command_accumulator._trial_parse), not a runtime strategy.

            # Reuse the accumulator's trial parse when it matches what we
            # are about to execute (recursive-descent parser active and the
            # reporting preprocessing reproduced the trial's source text);
            # otherwise tokenize and parse here — exactly once either way.
            if complete.ast is not None and command_string == complete.source:
                self._debug_print_tokens(complete.tokens)
                ast = complete.ast
            elif contains_heredoc(command_string):
                # Use the lexer with heredoc support
                from ..lexer import tokenize_with_heredocs
                tokens, heredoc_map = tokenize_with_heredocs(command_string, strict=self.state.options.get('posix', False),
                                                              shell_options=self.state.options)
                # Alias expansion is a token-stream transform at the
                # lex→parse boundary (see AliasManager.expand_aliases).
                tokens = self.shell.alias_manager.expand_aliases(tokens)
                self._debug_print_tokens(tokens)
                # Parse with heredoc map, honoring the active parser
                from ..parser import parse_with_heredocs
                ast = parse_with_heredocs(tokens, heredoc_map,
                                          active_parser=self.shell.active_parser)
            else:
                tokens = tokenize(command_string, shell_options=self.state.options)
                tokens = self.shell.alias_manager.expand_aliases(tokens)
                self._debug_print_tokens(tokens)
                # Parse with source text for better error messages and shell configuration
                from ..parser import create_parser
                parser = create_parser(
                    tokens,
                    active_parser=self.shell.active_parser,
                    source_text=command_string,
                )
                ast = parser.parse()

            # Convert the parser's buffer-relative $LINENO stamps to absolute
            # source lines (offset by where this buffer began). Done once here
            # so a function body bakes in its definition-site lines. See
            # ASTNode.line and _offset_line_numbers.
            if start_line > 1:
                _offset_line_numbers(ast, start_line - 1)

            # Debug: Print AST if requested
            if self.state.debug_ast:
                from ..utils.ast_debug import print_ast_debug
                print_ast_debug(ast, self.shell.ast_format, self.shell)

            # Validation mode - analyze AST without executing
            if self.shell.validate_only:
                # Use the shared validator instance
                if self.validation_visitor:
                    self.validation_visitor.visit(ast)
                else:
                    # Fallback for single command validation
                    from ..visitor import EnhancedValidatorVisitor
                    validator = EnhancedValidatorVisitor()
                    validator.visit(ast)
                    print(validator.get_summary())
                    error_count = sum(1 for i in validator.issues
                                    if i.severity.value == 'error')
                    return 1 if error_count > 0 else 0

                # Don't execute in validation mode
                return 0

            # NoExec mode - parse and validate but don't execute
            if self.state.options.get('noexec', False):
                # Successfully parsed, so syntax is valid
                return 0

            # Increment command number for successful parse
            self.state.command_number += 1

            from ..core import FunctionReturn, LoopBreak, LoopContinue, TopLevelAbort
            try:
                # Handle TopLevel AST node (functions + commands)
                if isinstance(ast, TopLevel):
                    return self.shell.execute_toplevel(ast)
                else:
                    try:
                        # Heredoc content is now pre-populated during parsing.
                        # The parser returns a StatementList here (TopLevel
                        # handled above); the cast records that invariant.
                        exit_code = self.shell.execute_command_list(cast(StatementList, ast))
                        return exit_code
                    except (LoopBreak, LoopContinue) as e:
                        # Break/continue outside of any loop is an error. Catch
                        # only these — any other exception propagates to its own
                        # handler.
                        if nested:
                            # e.g. `eval break` inside a loop — let the loop handle it
                            raise
                        stmt_name = "break" if isinstance(e, LoopBreak) else "continue"
                        print(f"{stmt_name}: only meaningful in a `for' or `while' loop",
                              file=sys.stderr)
                        return 1
            except TopLevelAbort as e:
                # A fatal assignment error (readonly/nameref-cycle) unwound the
                # whole current top-level command (the rest of the command list
                # and any enclosing if/loop/function on the same input). The
                # error was already printed at the raise site; resume at the next
                # top-level command (bash). When nested (eval) let it keep
                # unwinding to the real top-level command boundary.
                if nested:
                    raise
                self.state.last_exit_code = e.status
                return e.status
            except FunctionReturn as e:
                # `return` reaching a NON-nested top level only happens in a
                # subshell-style child that inherited a function/sourced-file
                # context (ShellState.adopt copies function_stack and
                # source_depth): the child's input stops with that status,
                # like end-of-sourced-file (bash: x=$(return 3; echo x)
                # leaves x empty, $? = 3). Nested (eval, trap action) it
                # propagates to the enclosing function/source handler.
                if nested:
                    raise
                self.state.last_exit_code = e.exit_code
                return e.exit_code
        except ParseError as e:
            # Check if error already has context, otherwise add location
            if e.error_context and e.error_context.source_line:
                # Error already has full context, just print it
                print(f"psh: {str(e)}", file=sys.stderr)
            else:
                # Add location prefix to error
                location = f"{input_source.get_name()}:{start_line}" if start_line > 0 else "command"
                print(f"psh: {location}: {e.message}", file=sys.stderr)
            self.state.last_exit_code = 2  # Bash uses exit code 2 for syntax errors
            return 2
        except UnclosedQuoteError as e:
            # An unterminated quote that survived line-gathering (e.g. an
            # EOF-flushed buffer like `-c "echo 'abc"`). This is a syntax
            # error, exactly like the unterminated $((/$( /${ constructs the
            # parser reports as ParseError above — route it to the same
            # exit-2 path instead of the "unexpected error" defect handler.
            location = f"{input_source.get_name()}:{start_line}" if start_line > 0 else "command"
            print(f"psh: {location}: syntax error: {e}", file=sys.stderr)
            self.state.last_exit_code = 2
            return 2
        except Exception as e:
            # Control-flow exceptions from nested execution propagate to
            # their enclosing loop/function handlers.
            from ..builtins import FunctionReturn
            from ..core import LoopBreak, LoopContinue
            if nested and isinstance(e, (LoopBreak, LoopContinue, FunctionReturn)):
                raise
            # Last-resort guard so an internal defect doesn't kill an
            # interactive session (or re-raise under strict-errors so a test
            # harness surfaces it) — see report_internal_defect for the policy.
            from ..core import report_internal_defect
            location = f"{input_source.get_name()}:{start_line}" if start_line > 0 else "command"
            rc = report_internal_defect(
                self.state, e, prefix=f"{location}: unexpected error: ",
                stream=sys.stderr)
            self.state.last_exit_code = rc
            return rc

    def _debug_print_tokens(self, tokens) -> None:
        """Print the token stream when --debug-tokens is enabled."""
        if self.state.debug_tokens:
            print("=== Token Debug Output ===", file=sys.stderr)
            from ..utils.token_formatter import TokenFormatter
            print(TokenFormatter.format(tokens), file=sys.stderr)
            print("========================", file=sys.stderr)
