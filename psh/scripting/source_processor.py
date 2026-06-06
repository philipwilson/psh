"""Source file and command buffer processing."""
import sys
from typing import Optional

from ..ast_nodes import TopLevel
from ..lexer import LexerError, tokenize
from ..parser import ParseError
from ..utils import (
    HEREDOC_MARKER_RE,
    contains_heredoc,
    has_unclosed_heredoc,
    is_inside_expansion,
)
from .base import ScriptComponent


class SourceProcessor(ScriptComponent):
    """Processes input from various sources (files, strings, stdin)."""

    def execute_from_source(self, input_source, add_to_history: bool = True) -> int:
        """Execute commands from an input source with enhanced processing."""
        exit_code = 0
        command_buffer = ""
        command_start_line = 0

        # For validation mode, collect all issues across the entire script
        if self.shell.validate_only:
            from ..visitor import EnhancedValidatorVisitor
            self.validation_visitor = EnhancedValidatorVisitor()
        else:
            self.validation_visitor = None

        while True:
            line = input_source.read_line()
            if self.state.options.get('debug-exec', False):
                print(f"DEBUG source_processor: read line: {repr(line)}", file=sys.stderr)
            if line is None:  # EOF
                # Execute any remaining command in buffer
                if command_buffer.strip():
                    exit_code = self._execute_buffered_command(
                        command_buffer, input_source, command_start_line, add_to_history
                    )
                    # In non-interactive mode with errexit, exit on error
                    if exit_code != 0 and not input_source.is_interactive() and self.state.options.get('errexit', False):
                        if self.state.options.get('debug-exec', False):
                            print(f"DEBUG: Exiting due to errexit with code {exit_code}", file=sys.stderr)
                        return exit_code
                # In validation mode, show final summary at end
                if self.validation_visitor:
                    print(self.validation_visitor.get_summary())
                    # Return exit code based on errors
                    error_count = sum(1 for i in self.validation_visitor.issues
                                    if i.severity.value == 'error')
                    exit_code = 1 if error_count > 0 else 0
                break

            # Skip empty lines when no command is being built
            if not command_buffer and not line.strip():
                continue

            # Skip comment lines when no command is being built
            if not command_buffer and line.strip().startswith('#'):
                continue

            # Note: Line continuation handling is now done in preprocessing

            # Add current line to buffer
            if not command_buffer:
                command_start_line = input_source.get_line_number()
            # Add line to buffer with proper spacing
            if command_buffer and not command_buffer.endswith('\n'):
                command_buffer += '\n'
            command_buffer += line

            # Try to parse and execute the command
            if command_buffer.strip():
                # Process line continuations and history expansion before testing completeness
                test_command = command_buffer
                from ..input_preprocessing import process_line_continuations
                test_command = process_line_continuations(test_command)

                # Apply history expansion for completeness testing (don't print)
                if (not self.state.is_script_mode and
                        hasattr(self.shell, 'history_expander')):
                    expanded_test = self.shell.history_expander.expand_history(
                        test_command,
                        print_expansion=False,
                        report_errors=False,
                    )
                    if expanded_test is not None:
                        test_command = expanded_test

                # Check for unclosed heredocs and collect content if needed
                # Use the shell's method which properly handles arithmetic expressions
                if contains_heredoc(test_command) and self._has_unclosed_heredoc(test_command):
                    # Continue reading lines to complete heredocs
                    command_buffer = self._collect_heredoc_content(command_buffer, input_source)
                    if command_buffer is None:  # EOF while reading heredoc
                        break
                    # Re-process the complete command
                    test_command = command_buffer
                    test_command = process_line_continuations(test_command)
                    if (not self.state.is_script_mode and
                            hasattr(self.shell, 'history_expander')):
                        expanded_test = self.shell.history_expander.expand_history(
                            test_command,
                            print_expansion=False,
                            report_errors=False,
                        )
                        if expanded_test is not None:
                            test_command = expanded_test

                # Check if command contains history expansion - if so, treat as complete
                from ..history_expansion import contains_history_reference
                if contains_history_reference(test_command):
                    # Skip parse testing for history expansions - let execution handle them
                    exit_code = self._execute_buffered_command(
                        command_buffer.rstrip('\n'), input_source, command_start_line, add_to_history
                    )
                    # Reset buffer for next command
                    command_buffer = ""
                    command_start_line = 0
                    # In non-interactive mode with errexit, exit on error
                    if exit_code != 0 and not input_source.is_interactive() and self.state.options.get('errexit', False):
                        if self.state.options.get('debug-exec', False):
                            print(f"DEBUG: Exiting due to errexit with code {exit_code}", file=sys.stderr)
                        return exit_code
                else:
                    # Check if command is complete by trying to parse it
                    try:
                        tokens = tokenize(test_command, shell_options=self.state.options)
                        # Try parsing to see if command is complete
                        from ..parser import Parser
                        parser = Parser(tokens, source_text=test_command)
                        parser.parse()
                        # If parsing succeeds, execute the command
                        exit_code = self._execute_buffered_command(
                            command_buffer.rstrip('\n'), input_source, command_start_line, add_to_history
                        )
                        # Reset buffer for next command
                        command_buffer = ""
                        command_start_line = 0
                        # In non-interactive mode with errexit, exit on error
                        if exit_code != 0 and not input_source.is_interactive() and self.state.options.get('errexit', False):
                            if self.state.options.get('debug-exec', False):
                                print(f"DEBUG: Exiting due to errexit with code {exit_code}", file=sys.stderr)
                            return exit_code
                    except (ParseError, LexerError, SyntaxError) as e:
                        # Check if this is an incomplete command
                        if self._is_incomplete_command(e):
                            # Command is incomplete, continue reading
                            continue
                        else:
                            # It's a real parse error, report it and reset
                            filename = input_source.get_name() if hasattr(input_source, 'get_name') else 'stdin'
                            print(f"{filename}:{command_start_line}: {e}", file=sys.stderr)
                            command_buffer = ""
                            command_start_line = 0
                            exit_code = 2  # Bash uses exit code 2 for syntax errors
                            self.state.last_exit_code = 2

                            # In non-interactive mode, exit immediately on parse errors
                            if not input_source.is_interactive():
                                return exit_code

        return exit_code

    def _is_incomplete_command(self, error) -> bool:
        """Check if a parse or lexer error indicates an incomplete command."""
        error_msg = str(error)

        # Handle lexer errors from incomplete constructs
        lexer_incomplete_patterns = [
            "Unclosed parenthesis",
            "Unclosed double parentheses",
            "Unclosed arithmetic expansion",
            "Unclosed brace",
            "Unclosed quote",
            "Unclosed single quote",
            "Unclosed double quote",
            "Unclosed \" quote at position",
            "Unclosed ' quote at position"
        ]

        for pattern in lexer_incomplete_patterns:
            if pattern in error_msg:
                return True

        # Handle parser errors - updated patterns to match the new human-readable error messages
        incomplete_patterns = [
            # Control structure keywords
            ("Expected 'do'", "got end of input"),
            ("Expected 'done'", "got end of input"),
            ("Expected 'fi'", "got end of input"),
            ("Expected 'then'", "got end of input"),
            ("Expected 'in'", "got end of input"),
            ("Expected 'esac'", "got end of input"),
            ("Expected 'else'", "got end of input"),
            ("Expected 'elif'", "got end of input"),

            # Function and compound commands
            ("Expected '{'", "got end of input"),
            ("Expected '}'", "got end of input"),
            ("Expected '}' to end compound command", None),

            # Parentheses and brackets
            ("Expected ')'", "got end of input"),
            ("Expected ']]'", "got end of input"),
            ("Expected '('", "got end of input"),
            ("Expected '[['", "got end of input"),

            # Test expressions
            ("Expected test operand", "got end of input"),
            ("Expected test operand", None),

            # Redirections
            ("Expected delimiter after here document", "got end of input"),
            ("Expected string after here string", "got end of input"),

            # Commands
            ("Expected command", "got end of input"),

            # Case patterns
            ("Expected pattern in case statement", "got end of input"),
            ("Expected pattern in case statement", None),  # When no "got" part

            # New TokenType-based patterns from ParserContext (case sensitive)
            ("Expected TokenType.DO", "got TokenType.EOF"),
            ("Expected TokenType.DONE", "got TokenType.EOF"),
            ("Expected TokenType.FI", "got TokenType.EOF"),
            ("Expected TokenType.THEN", "got TokenType.EOF"),
            ("Expected TokenType.IN", "got TokenType.EOF"),
            ("Expected TokenType.ESAC", "got TokenType.EOF"),
            ("Expected TokenType.RPAREN", "got TokenType.EOF"),
            ("Expected TokenType.DOUBLE_RBRACKET", "got TokenType.EOF"),
            ("Expected TokenType.LBRACE", "got TokenType.EOF"),
            ("Expected TokenType.RBRACE", "got TokenType.EOF"),
            ("Expected TokenType.LPAREN", "got TokenType.EOF"),
            ("Expected TokenType.ELSE", "got TokenType.EOF"),
            ("Expected TokenType.ELIF", "got TokenType.EOF"),

        ]

        for expected, got in incomplete_patterns:
            if expected in error_msg:
                if got is None or got in error_msg:
                    return True

        return False

    def _execute_buffered_command(self, command_string: str, input_source,
                                  start_line: int, add_to_history: bool) -> int:
        """Execute a buffered command with enhanced error reporting."""
        # Skip empty commands and comments
        if not command_string.strip() or command_string.strip().startswith('#'):
            return 0

        # Update LINENO special variable with current line number
        if start_line > 0:
            self.shell.state.scope_manager.set_current_line_number(start_line)

        # Verbose mode: echo input lines as they are read
        if self.state.options.get('verbose', False):
            # Echo the command to stderr before execution
            print(command_string, file=sys.stderr)

        try:
            # Process line continuations first
            from ..input_preprocessing import process_line_continuations
            command_string = process_line_continuations(command_string)

            # Perform history expansion before tokenization
            if (not self.state.is_script_mode and
                    hasattr(self.shell, 'history_expander')):
                expanded_command = self.shell.history_expander.expand_history(command_string)
                if expanded_command is None:
                    # History expansion failed - this is the proper error path
                    self.state.last_exit_code = 1
                    return 1
                command_string = expanded_command

            tokens = tokenize(command_string, shell_options=self.state.options)

            # Debug: Print tokens if requested
            if self.state.debug_tokens:
                print("=== Token Debug Output ===", file=sys.stderr)
                from ..utils.token_formatter import TokenFormatter
                print(TokenFormatter.format(tokens), file=sys.stderr)
                print("========================", file=sys.stderr)

            # Note: Alias expansion now happens during execution phase for proper precedence

            # Check if command contains heredocs and parse accordingly
            if contains_heredoc(command_string):
                # Use the new lexer with heredoc support
                from ..lexer import tokenize_with_heredocs
                tokens, heredoc_map = tokenize_with_heredocs(command_string, strict=self.state.options.get('posix', False),
                                                              shell_options=self.state.options)
                # Parse with heredoc map
                from ..parser import parse_with_heredocs
                ast = parse_with_heredocs(tokens, heredoc_map)
            else:
                # Parse with source text for better error messages and shell configuration
                from ..parser import create_parser
                parser = create_parser(
                    tokens,
                    active_parser=self.shell.active_parser,
                    trace_parsing=self.state.options.get('debug-parser', False),
                    source_text=command_string,
                )
                ast = parser.parse()

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

            # Add to history if requested (for interactive or testing)
            # Don't add history expansion commands to history
            if add_to_history and command_string.strip():
                from ..history_expansion import contains_history_reference
                if not contains_history_reference(command_string):
                    self.shell.add_history(command_string.strip())

            # Increment command number for successful parse
            self.state.command_number += 1

            # Handle TopLevel AST node (functions + commands)
            if isinstance(ast, TopLevel):
                return self.shell.execute_toplevel(ast)
            else:
                from ..core import LoopBreak, LoopContinue
                try:
                    # Heredoc content is now pre-populated during parsing
                    exit_code = self.shell.execute_command_list(ast)
                    return exit_code
                except (LoopBreak, LoopContinue) as e:
                    # Break/continue outside of any loop is an error. Catch only
                    # these — any other exception propagates to its own handler.
                    stmt_name = "break" if isinstance(e, LoopBreak) else "continue"
                    print(f"{stmt_name}: only meaningful in a `for' or `while' loop",
                          file=sys.stderr)
                    return 1
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
        except Exception as e:
            # Last-resort guard so an internal defect doesn't kill an
            # interactive session. Surface the full traceback under --debug-exec
            # so the bug is not hidden behind the generic message.
            location = f"{input_source.get_name()}:{start_line}" if start_line > 0 else "command"
            if self.state.options.get('debug-exec'):
                import traceback
                traceback.print_exc(file=sys.stderr)
            print(f"psh: {location}: unexpected error: {e}", file=sys.stderr)
            self.state.last_exit_code = 1
            return 1

    def _has_unclosed_heredoc(self, command: str) -> bool:
        """Check if command has an unclosed heredoc (shared detector)."""
        return has_unclosed_heredoc(command)

    def _collect_heredoc_content(self, command_buffer: str, input_source) -> Optional[str]:
        """Collect heredoc content from input source until all delimiters are satisfied."""
        # Find heredoc markers already present in the buffer and which of them
        # are closed, using the shared marker regex / expansion exclusion.
        lines = command_buffer.split('\n')
        heredoc_delimiters = []

        for line in lines:
            # If there are open heredocs, this line is heredoc content
            if any(d for d in heredoc_delimiters if not d['closed']):
                # Check if this line closes an open heredoc
                for delimiter in heredoc_delimiters:
                    if not delimiter['closed']:
                        check_line = line.lstrip('\t') if delimiter['strip_tabs'] else line
                        if check_line.rstrip() == delimiter['word']:
                            delimiter['closed'] = True
                            break
            else:
                # Look for new heredoc markers
                for match in HEREDOC_MARKER_RE.finditer(line):
                    if is_inside_expansion(line, match.start()):
                        continue
                    strip_tabs = bool(match.group(1))
                    quoted = bool(match.group(2))
                    has_backslash = bool(match.group(3))
                    word = match.group(4)
                    heredoc_delimiters.append({
                        'word': word,
                        'strip_tabs': strip_tabs,
                        'quoted': quoted,
                        'closed': False,
                        'escaped': has_backslash
                    })

        # If no unclosed heredocs, return current buffer
        if not heredoc_delimiters or all(d['closed'] for d in heredoc_delimiters):
            return command_buffer

        # Continue reading lines until all heredocs are closed
        result_buffer = command_buffer

        while True:
            # Check if all heredocs are closed
            if all(d['closed'] for d in heredoc_delimiters):
                break

            # Read next line
            line = input_source.read_line()
            if line is None:  # EOF
                return None

            # Add line to buffer
            if not result_buffer.endswith('\n'):
                result_buffer += '\n'
            result_buffer += line

            # Check if this line closes any open heredocs
            for delimiter in heredoc_delimiters:
                if not delimiter['closed']:
                    check_line = line.lstrip('\t') if delimiter['strip_tabs'] else line
                    if check_line.rstrip() == delimiter['word']:
                        delimiter['closed'] = True
                        break

        return result_buffer

