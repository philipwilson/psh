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
from typing import Any, Optional, cast

from ..ast_nodes import ASTNode, Program
from ..core import (
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    SpecialBuiltinUsageError,
    TopLevelAbort,
    report_internal_defect,
)
from ..lexer import UnclosedQuoteError
from ..lexer.token_formatter import TokenFormatter
from ..parser import ParseError
from ..utils.ast_debug import print_ast_debug
from .base import ScriptComponent
from .command_accumulator import CommandAccumulator, Complete, NeedMore


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
            # Fire any signal trap queued by the FINAL statement but not yet
            # run at a command boundary — e.g. a script whose last statement
            # is `kill -TERM $$` with a TERM trap installed. The statement
            # loop runs pending traps at the START of each item, so a trap
            # queued by the last item has no later boundary to fire at; bash
            # runs it before the shell exits (and before the EXIT trap). A
            # trap action that itself runs `exit N` raises SystemExit here,
            # caught below so N becomes the status (bash).
            self.shell.trap_manager.run_pending_traps()
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

        A NESTED run (eval / dot / trap action — an enclosing executor is
        active) raises the POSIX suppressible-exit FLOOR to the entry-time
        suppression depth for the duration of this source: bash's
        posix-mode suppression of the invalid-option/return exit class does
        NOT reach across an eval/dot boundary (``eval 'set -q' || x`` still
        exits; a guard INSIDE the eval'd text suppresses again) — see
        ``ExecutionContext.special_exit_floor``.
        """
        executor = getattr(self.shell, '_current_executor', None)
        if executor is None:
            return self._run_from_source(input_source, add_to_history,
                                         base_line)
        saved_floor = executor.context.special_exit_floor
        executor.context.special_exit_floor = executor.context.errexit_suppress
        try:
            return self._run_from_source(input_source, add_to_history,
                                         base_line)
        finally:
            executor.context.special_exit_floor = saved_floor

    def _run_from_source(self, input_source, add_to_history: bool = True,
                         base_line: int = 1) -> int:
        """The line-gathering loop of :meth:`execute_from_source`."""
        exit_code = 0
        command_start_line = 0
        accumulator = CommandAccumulator(self.shell)

        while True:
            line = input_source.read_line()
            if self.state.options.get('debug-exec', False):
                print(f"DEBUG source_processor: read line: {repr(line)}", file=sys.stderr)
            if line is None:  # EOF
                # Execute any remaining buffered command (a truncated
                # construct parses to "unexpected end of input" here).
                # End of input inside a heredoc body is NOT special: like
                # bash, the heredoc is "delimited by end-of-file" — the
                # lexer finalizes the gathered lines as the body, prints
                # bash's warning, and the command runs (it used to be
                # silently dropped, rc 0).
                if not accumulator.is_empty:
                    exit_code = self._execute_buffered_command(
                        accumulator.flush(), input_source, command_start_line,
                        add_to_history)
                    if self._should_exit_on_error(exit_code, input_source):
                        return exit_code
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
                # Tell the accumulator where this command starts so its
                # trial-parse errors carry absolute line numbers.
                accumulator.start_line = max(1, command_start_line)

            result = accumulator.feed(line)
            if isinstance(result, NeedMore):
                continue

            if result.error is not None:
                # A real syntax error (not incomplete input): report it
                # against where the command started and reset.
                self._report_syntax_error(result.error, input_source,
                                          command_start_line,
                                          source_text=result.source or result.text)
                command_start_line = 0
                exit_code = 2  # Bash uses exit code 2 for syntax errors
                self.state.last_exit_code = 2
                # In non-interactive mode, exit immediately on parse errors
                if not input_source.is_interactive():
                    self._posix_syntax_abort(input_source)
                    return exit_code
                continue

            exit_code = self._execute_buffered_command(
                result, input_source, command_start_line, add_to_history)
            command_start_line = 0
            if self._should_exit_on_error(exit_code, input_source):
                return exit_code

        return exit_code

    @staticmethod
    def _location(input_source, line: int) -> str:
        """The ``<name>:<line>`` diagnostic prefix for a source error.

        ``<name>`` is the input source's name (``-c``, the script path,
        ``<stdin>`` — ``get_name`` is abstract on ``InputSource``, so every
        concrete source has one). ``line`` is the absolute source line, or
        ``<= 0`` for an input with no meaningful line (a whole ``run_command``
        buffer), where diagnostics fall back to the bare label ``command``.
        """
        return f"{input_source.get_name()}:{line}" if line > 0 else "command"

    def _report_syntax_error(self, error, input_source, start_line: int,
                             source_text: Optional[str] = None) -> None:
        """Print a syntax error in the ONE canonical format.

        Every parse/lex error — the accumulator's trial parse, the execution
        path's own parse, or an unterminated quote surviving line-gathering —
        renders as::

            psh: <source>:<line>: <detailed message>

        For a ParseError the detailed message is the rich caret form
        (source line, ``^`` marker, suggestions, token context) and the
        prefix uses the ERROR's absolute line when known (bash reports the
        line the error is on, not the line the command started on). A lexer
        error (an unterminated quote) has no rich context, so its message is
        ``syntax error: <reason>`` and the prefix falls back to the command's
        start line.

        ``source_text`` back-fills the caret's source line for errors whose
        parser was not given the source (the combinator parser) — the
        token's line is fragment-relative, so it indexes ``source_text``
        directly. The detail form is shared with the analysis renderer via
        ``lex_parse.render_syntax_error_detail``.
        """
        from .lex_parse import render_syntax_error_detail
        line = start_line
        if (isinstance(error, ParseError) and error.error_context
                and error.error_context.line):
            # bash reports the line the error is ON, not where the command began.
            line = error.error_context.line
        detail = render_syntax_error_detail(error, source_text=source_text)
        print(f"psh: {self._location(input_source, line)}: {detail}",
              file=sys.stderr)

    def _posix_syntax_abort(self, input_source) -> None:
        """POSIX-mode fatal SYNTAX error (bash 5.2, probe tmp/posixexit).

        In POSIX mode a non-interactive shell exits with status 2 on a
        syntax error — including inside ``eval`` and a sourced file, which
        otherwise CONTAIN the rc-2 (``set -o posix; eval 'if'; echo x``
        exits before x in bash). Called AFTER the error is reported and
        ``last_exit_code`` set; a no-op (caller returns 2 as before) when:

        - not in POSIX mode, or the shell is interactive/embedded
          (``is_script_mode`` False) — default behavior is untouched;
        - this input is a TRAP ACTION string (``posix_syntax_exit`` False —
          bash does not exit when the action itself fails to parse, while
          an eval nested INSIDE the action, a fresh input, still does);
        - the error is an unclosed quote (bash: ``eval 'echo "x'`` returns
          2 without exiting even in POSIX mode) — those never reach here
          (the UnclosedQuoteError clause doesn't call this).

        NESTED input (eval / sourced file — an enclosing executor exists)
        raises the typed ``SpecialBuiltinUsageError(2)``: it surfaces from
        the eval/./source builtin and resolves at the builtin guard, so a
        ``command eval 'if'`` / ``command . file`` invocation — which
        strips the special property — fails with 2 instead of exiting,
        exactly like bash. The true top level raises SystemExit directly.
        """
        if not (self.state.options.get('posix')
                and self.state.is_script_mode
                and getattr(input_source, 'posix_syntax_exit', True)):
            return
        if getattr(self.shell, '_current_executor', None) is not None:
            raise SpecialBuiltinUsageError(2)
        raise SystemExit(2)

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
        """Execute a complete buffered command with enhanced error reporting.

        This is the ERROR-MODEL skeleton for the buffered-command boundary;
        the three phases it drives live in dedicated helpers so each reads
        cleanly, while the try/except STRUCTURE and clause ORDER stay here
        (they ARE the semantics — see the phase helpers):

        1. ``_preprocess_command`` — line continuations + history
           expansion/recording (may short-circuit on a history-expansion
           failure);
        2. ``_parse_command`` — tokenize and parse to an AST (raises
           ``ParseError``/``UnclosedQuoteError``/lexer ``SyntaxError`` into
           the clauses below);
        3. ``_dispatch_execution`` — run the AST, resolving the control-flow
           signals (``LoopBreak``/``LoopContinue``/``FunctionReturn``) and
           ``TopLevelAbort`` discards.

        Anything that escapes those phases is classified by
        ``_classify_buffered_error`` in the final ``except Exception`` clause
        (fatal expansion, runaway recursion, internal-defect guard). Every
        phase is *called from within* this try, so an exception it raises is
        caught by exactly the same clause the inline code hit.
        """
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
            # Echo the command to stderr before execution. ``command_string``
            # may carry ONE trailing newline that the accumulator kept as a
            # line-continuation "reprieve" for preprocessing (see
            # _strip_trailing_separators): a buffer like ``echo a\<newline>``
            # whose backslash-newline pair runs into EOF. print() supplies the
            # line's own trailing newline, so echoing the reprieve too would add
            # a spurious blank line — bash echoes the raw line just once.
            print(command_string.rstrip('\n'), file=sys.stderr)

        # Nested execution (eval, source, trap action) runs inside an outer
        # ExecutorVisitor: control-flow exceptions (break/continue/return)
        # must propagate to the enclosing loop/function instead of being
        # reported as errors here.
        nested = getattr(self.shell, '_current_executor', None) is not None

        try:
            preprocessed = self._preprocess_command(
                command_string, add_to_history,
                drop_dangling_at_eof=input_source.eof_drops_dangling_continuation)
            if preprocessed is None:
                # History expansion failed - this is the proper error path
                # (the "event not found" message was already printed).
                self.state.last_exit_code = 1
                return 1
            command_string = preprocessed

            ast = self._parse_command(complete, command_string, input_source,
                                      start_line)

            # NoExec mode - parse and validate but don't execute
            if self.state.options.get('noexec', False):
                # Successfully parsed, so syntax is valid
                return 0

            # Increment command number for successful parse
            self.state.command_number += 1

            return self._dispatch_execution(ast, nested)
        except ParseError as e:
            # Same canonical rendering as the trial-parse error path.
            self._report_syntax_error(e, input_source, start_line,
                                      source_text=command_string)
            self.state.last_exit_code = 2  # Bash uses exit code 2 for syntax errors
            self._posix_syntax_abort(input_source)
            return 2
        except UnclosedQuoteError as e:
            # An unterminated quote that survived line-gathering (e.g. an
            # EOF-flushed buffer like `-c "echo 'abc"`). Route it to the SAME
            # canonical renderer and exit-2 path as the parser's ParseError
            # above (instead of the "unexpected error" defect handler); the
            # renderer's lexer-error branch reproduces the `syntax error:
            # <reason>` shape. NOTE: unlike ParseError this does NOT call
            # _posix_syntax_abort — bash returns 2 on an unclosed quote WITHOUT
            # exiting, even in POSIX mode (see _posix_syntax_abort).
            self._report_syntax_error(e, input_source, start_line,
                                      source_text=command_string)
            self.state.last_exit_code = 2
            return 2
        except Exception as e:
            return self._classify_buffered_error(e, input_source, start_line,
                                                 nested)

    def _preprocess_command(self, command_string: str, add_to_history: bool,
                            drop_dangling_at_eof: bool = False) -> Optional[str]:
        """Preprocess a raw buffered command string before parsing.

        Joins line continuations, performs (interactive) history expansion,
        and records the command in history. Returns the preprocessed string,
        or ``None`` when history expansion FAILED — the caller turns that
        ``None`` into exit status 1 without parsing or executing.

        ``drop_dangling_at_eof`` is the input source's stream-vs-string rule
        for a trailing backslash at true end of input (see
        ``InputSource.eof_drops_dangling_continuation``). It is threaded to
        every buffered command, but only the EOF-flushed buffer can actually
        end with a joinable dangling continuation — mid-source, the
        accumulator keeps reading instead of completing such a buffer.
        """
        # Process line continuations first
        from .input_preprocessing import process_line_continuations
        command_string = process_line_continuations(
            command_string, drop_dangling_at_eof=drop_dangling_at_eof)

        # Perform history expansion before tokenization. The accumulator
        # already expanded silently for the completeness trial; this
        # pass is the REPORTING one — it echoes the expansion like bash
        # and prints "event not found" errors.
        if (not self.state.is_script_mode and
                hasattr(self.shell, 'history_expander')):
            expanded_command = self.shell.history_expander.expand_history(command_string)
            if expanded_command is None:
                # History expansion failed - signal the proper error path
                return None
            command_string = expanded_command

        # Record in history (interactive use). This is the ONE history
        # writer: it sees the complete logical command, so multi-line
        # constructs land as a single joined entry (bash cmdhist).
        # Done before parsing so that, like bash, commands with syntax
        # errors are still recallable for editing.
        # The command is passed RAW — bash stores the line verbatim
        # (leading/trailing whitespace included), and the semantic
        # filters inside add_to_history depend on the unmodified text:
        # HISTCONTROL=ignorespace keys on the leading space, and
        # ignoredups/HISTIGNORE compare/match the verbatim line. A
        # pre-strip here made ignorespace a silent no-op on the real
        # entry path (reappraisal #17 H7 privacy leak). Whitespace-only
        # commands are still skipped (deliberate divergence: bash
        # records them).
        if add_to_history and command_string.strip():
            from ..interactive.history_expansion import contains_history_reference
            if not contains_history_reference(command_string):
                self.shell.add_history(command_string)

        # Alias expansion is a token-stream transform applied at the
        # lex->parse seam (see the expand_aliases calls below and in
        # command_accumulator._trial_parse), not a runtime strategy.
        return command_string

    def _parse_command(self, complete: Complete, command_string: str,
                       input_source, start_line: int) -> ASTNode:
        """Tokenize and parse a preprocessed command string into an AST.

        Reuses the accumulator's trial-parse AST when it matches what we
        are about to execute; otherwise tokenizes (with heredoc support
        when needed) and parses here — exactly once either way. Stamps
        absolute ``$LINENO`` lines and honours ``--debug-ast``. Lex/parse
        failures raise (``ParseError``/``UnclosedQuoteError``/lexer
        ``SyntaxError``) for the caller's error-model clauses.
        """
        # Reuse the accumulator's trial parse when it matches what we
        # are about to execute (recursive-descent parser active and the
        # reporting preprocessing reproduced the trial's source text);
        # otherwise lex and parse here — exactly once either way — through
        # the one shared pipeline (scripting/lex_parse.py). The token stream
        # is fetched separately from the parse so it can be printed under
        # ``--debug-tokens`` between the two stages.
        if complete.ast is not None and command_string == complete.source:
            self._debug_print_tokens(complete.tokens)
            ast = complete.ast
        else:
            from .lex_parse import lex_and_expand, parse_tokens
            # source_name locates the buffer for the unterminated-heredoc
            # warning ("delimited by end-of-file"): a script/sourced-file path
            # prefixes it like bash's script name; the -c/stdin/eval
            # pseudo-names map to the "psh" prefix (bash prints "bash:").
            name = input_source.get_name()
            tokens, heredoc_map = lex_and_expand(
                command_string, self.shell,
                source_name=None if name.startswith(('<', '-')) else name,
                base_line=start_line if start_line > 0 else 1,
                lexer_options=self.state.options)
            self._debug_print_tokens(tokens)
            # Honour the active parser; lexer_options threads the shell options
            # so a nested substitution body re-lexes with the same
            # option-sensitive lexing (extglob) as this command; source_text and
            # line_offset improve the plain path's error reporting.
            ast = parse_tokens(
                tokens, heredoc_map, self.shell,
                source_text=command_string,
                line_offset=max(0, start_line - 1),
                lexer_options=self.state.options)

        # Convert the parser's buffer-relative $LINENO stamps to absolute
        # source lines (offset by where this buffer began). Done once here
        # so a function body bakes in its definition-site lines. See
        # ASTNode.line and _offset_line_numbers.
        if start_line > 1:
            _offset_line_numbers(ast, start_line - 1)

        # Debug: Print AST if requested
        if self.state.debug_ast:
            print_ast_debug(ast, self.shell.ast_format, self.shell)

        return ast

    def _dispatch_execution(self, ast: ASTNode, nested: bool) -> int:
        """Execute a parsed AST, resolving control-flow signals at the boundary.

        Both parsers return a ``Program``, so there is no root-type branch: run
        it via ``execute_program`` and translate the control-flow exceptions
        that surface here. An out-of-loop break/continue at the real top level
        is handled inside ``visit_Program`` (loop_depth == 0); one that escapes
        with loop_depth > 0 (``eval break`` inside a loop, a seeded substitution
        child) propagates past here to ``_classify_buffered_error``, which
        re-raises it to the enclosing loop frame. This is the inner try/except
        of the buffered boundary; anything it does NOT handle (a fatal-expansion
        ``ExpansionError``, ``RecursionError`` or internal defect) propagates to
        ``_execute_buffered_command``'s clauses.
        """
        try:
            # Heredoc content is pre-populated during parsing.
            return self.shell.execute_program(cast(Program, ast))
        except TopLevelAbort as e:
            # A fatal error (readonly/nameref-cycle assignment, failed
            # arithmetic/parameter expansion, failglob) unwound the whole
            # current command line (the rest of the command list and any
            # enclosing if/loop/function on the same input). The error was
            # already printed at the raise site; resume at the next
            # buffered command (bash). This containment applies at EVERY
            # buffered-command boundary — including the nested processors
            # run by eval/source/trap actions: bash 5.2 (probe-verified,
            # tmp/probes-r17t2-arith/) CONTAINS the discard there
            # (`eval 'r=2; echo x'; echo after` kills x, runs after with
            # $?=1; a sourced file resumes at its own next line).
            # EXCEPTION: the assignment/subscript arithmetic-error family
            # passes through eval/source to the top-level input loop
            # (contain_nested=False — see arith_assignment_discard).
            if nested and not e.contain_nested:
                raise
            if e.errexit_immune:
                # Expansion-error discards bypass set -e (bash); a
                # readonly/failglob discard keeps its errexit effect.
                self.state.errexit_eligible = False
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

    def _classify_buffered_error(self, e: Exception, input_source,
                                 start_line: int, nested: bool) -> int:
        """Classify an exception escaping parse/execute at the buffered boundary.

        The body of ``_execute_buffered_command``'s final ``except Exception``
        clause: it runs AFTER the ``ParseError``/``UnclosedQuoteError`` clauses
        (they win for those types), so it sees only the residual exceptions.
        Order matters — control-flow signals first, then the fatal-expansion
        family, then runaway recursion, then the internal-defect guard.
        Either returns an exit status or re-raises ``e`` (``raise e`` from here
        propagates the SAME object with its ``__traceback__`` intact — as in
        ``report_internal_defect`` — so the enclosing loop/function/source
        handler catches it exactly as a bare ``raise`` in the clause would).
        """
        # Control-flow exceptions from nested execution propagate to
        # their enclosing loop/function handlers; loop-control signals
        # in a seeded substitution child propagate to run_child_shell
        # (see the LoopBreak/LoopContinue handler in _dispatch_execution).
        from ..builtins import FunctionReturn
        if isinstance(e, (LoopBreak, LoopContinue, FunctionReturn)):
            if nested:
                raise e
            if (isinstance(e, (LoopBreak, LoopContinue))
                    and self.shell._loop_depth_seed > 0):
                raise e
        # A fatal expansion error escaping a non-SimpleCommand context
        # (case subject, for-loop words, array initializer, redirect
        # target of a compound, ...) reaches this boundary directly:
        # apply the same bash model the command path uses. We are AT the
        # buffered-command boundary, so the discard-line family is
        # already complete (returning the status IS the discard); the
        # shell-exit family (:?/badsub/set -u) raises SystemExit for a
        # non-interactive shell. Messages were printed at the raise
        # site, except set -u which prints here.
        from ..core import (
            ExpansionError,
            UnboundVariableError,
            fatal_expansion_status,
        )
        if isinstance(e, (ExpansionError, UnboundVariableError)):
            if isinstance(e, UnboundVariableError):
                # Fallback set -u boundary report (the primary path is
                # report_unbound_variable, which is already location-prefixed);
                # match it so an UnboundVariableError reaching here directly is
                # prefixed too: `<$0>: line N: NAME: unbound variable`.
                print(f"{self.state.error_location_prefix()}{e}", file=sys.stderr)
            rc = fatal_expansion_status(self.state, e, at_boundary=True)
            self.state.last_exit_code = rc
            return rc
        if isinstance(e, RecursionError):
            if nested:
                # Runaway recursion inside a nested source (eval/trap body):
                # keep unwinding so the nearest enclosing function-call
                # boundary can convert it to the FUNCNEST diagnostic.
                raise e
            # At the REAL top level this is a function-less runaway — an
            # infinite `source` chain, a deep `eval` chain, or a deeply
            # nested compound at execution time. bash SEGFAULTS here (rc 139),
            # so there is no message to match; psh degrades with a
            # resource-limit diagnostic and rc 1. RecursionError is an
            # EXPECTED shell error (psh's implicit FUNCNEST ceiling), so
            # report it as a limit rather than through the internal-defect
            # guard's "unexpected error:" prefix, which reads like a psh bug.
            location = self._location(input_source, start_line)
            print(f"psh: {location}: maximum recursion depth exceeded",
                  file=sys.stderr)
            self.state.last_exit_code = 1
            return 1
        # Last-resort guard so an internal defect doesn't kill an
        # interactive session (or re-raise under strict-errors so a test
        # harness surfaces it) — see report_internal_defect for the policy.
        location = self._location(input_source, start_line)
        rc = report_internal_defect(
            self.state, e, prefix=f"{location}: unexpected error: ",
            stream=sys.stderr)
        self.state.last_exit_code = rc
        return rc

    def _debug_print_tokens(self, tokens) -> None:
        """Print the token stream when --debug-tokens is enabled."""
        if self.state.debug_tokens:
            print("=== Token Debug Output ===", file=sys.stderr)
            print(TokenFormatter.format(tokens), file=sys.stderr)
            print("========================", file=sys.stderr)
